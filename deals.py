"""Daily game deals builder.

Pulls free giveaways (GamerPower + CheapShark $0 deals) and discounted games
(CheapShark), tags each with Steam genres, writes the website to docs/, and
emails a digest of anything new.

Standard library only - no pip installs needed.
"""

import json
import os
import re
import smtplib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"
GENRE_CACHE_FILE = DATA / "genre_cache.json"
STATE_FILE = DATA / "state.json"
TEMPLATE_FILE = ROOT / "template.html"

USER_AGENT = "Mozilla/5.0 (compatible; GameDealsDaily/1.0)"
DEAL_PAGES = 2            # 60 deals per page
MAX_GENRE_LOOKUPS = 150   # new Steam lookups per run (Steam allows ~200 per 5 min)

# When a game has several Steam genres, the first match here decides its section.
GENRE_PRIORITY = [
    "RPG", "Strategy", "Simulation", "Racing", "Sports", "Massively Multiplayer",
    "Action", "Adventure", "Casual", "Indie", "Free To Play", "Early Access",
]
NON_GAME_GENRES = {
    "Utilities", "Design & Illustration", "Animation & Modeling", "Video Production",
    "Audio Production", "Photo Editing", "Software Training", "Web Publishing",
    "Education", "Game Development", "Accounting",
}


# ---------- helpers ----------

def get_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - network errors vary widely
            if attempt == retries - 1:
                print(f"  ! failed {url}: {e}")
                return None
            time.sleep(3 * (attempt + 1))


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False), encoding="utf-8")


def normalize(title):
    t = title.lower()
    t = re.sub(r"['’]", "", t)                # stores often drop apostrophes: "Assassins Creed"
    t = re.sub(r"\(.*?\)", " ", t)            # "(Epic Games)", "(Steam)"
    t = re.sub(r"\bgiveaway\b|\bkey\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


EDITION_WORDS = re.compile(
    r"\b(digital |game of the year |goty |complete |definitive |deluxe |ultimate |gold |premium |"
    r"standard |special |collector s |enhanced |legendary |anniversary )?"
    r"(edition|bundle|anthology|collection)\b.*$"
    r"|\b(goty|remastered|director s cut)\b.*$"
)


def base_title(title):
    """'The Quarry Deluxe Edition' -> 'the quarry', for matching against Steam."""
    t = EDITION_WORDS.sub("", normalize(title))
    return " ".join(t.split()) or normalize(title)


def clean_giveaway_title(title):
    t = re.sub(r"\s*\(.*?\)\s*", " ", title)
    t = re.sub(r"\s*giveaway\s*$", "", t.strip(), flags=re.I)
    return t.strip()


# ---------- genres (via Steam) ----------

class Genres:
    def __init__(self):
        self.cache = load_json(GENRE_CACHE_FILE, {})
        self.lookups = 0

    def _budget(self):
        if self.lookups >= MAX_GENRE_LOOKUPS:
            return False
        self.lookups += 1
        time.sleep(1.2)
        return True

    def by_appid(self, appid):
        key = f"steam:{appid}"
        if key in self.cache:
            return self.cache[key]
        if not self._budget():
            return []
        data = get_json(f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=genres")
        genres = []
        entry = (data or {}).get(str(appid)) or {}
        details = entry.get("data") if entry.get("success") else None
        if isinstance(details, dict):  # Steam sends [] when there is nothing to show
            genres = [g["description"] for g in details.get("genres", [])]
        if data is not None:  # don't cache network failures
            self.cache[key] = genres
        return genres

    def by_title(self, title):
        key = f"title:{normalize(title)}"
        if key in self.cache:
            return self.cache[key]
        base = base_title(title)
        want = normalize(title)
        words = base.split()
        match = None
        # Steam search finds nothing if there are extra words ("For Honor Year 8"),
        # so retry with shorter queries.
        for n in range(len(words), max(len(words) - 3, 0), -1):
            query = " ".join(words[:n])
            if len(query) < 5:
                break
            if not self._budget():
                return []
            data = get_json("https://store.steampowered.com/api/storesearch/?term="
                            f"{urllib.parse.quote(query)}&l=english&cc=US")
            if data is None:
                return []
            items = [i for i in data.get("items", []) if i.get("type") == "app"]  # skip bundles
            # "For Honor Year 8 Ultimate Edition" -> longest Steam name it starts with ("For Honor")
            prefixes = [i for i in items
                        if len(normalize(i["name"])) >= 5 and (want + " ").startswith(normalize(i["name"]) + " ")]
            match = (
                next((i for i in items if normalize(i["name"]) in (want, base)), None)
                or next((i for i in items if base_title(i["name"]) == base), None)
                or max(prefixes, key=lambda i: len(i["name"]), default=None)
            )
            if match:
                break
        genres = self.by_appid(match["id"]) if match else []
        if not match or f"steam:{match['id']}" in self.cache:  # skip caching if the lookup was cut short
            self.cache[key] = genres
        return genres

    def save(self):
        save_json(GENRE_CACHE_FILE, self.cache)


def primary_genre(genres):
    for g in GENRE_PRIORITY:
        if g in genres:
            return g
    game_genres = [g for g in genres if g not in NON_GAME_GENRES]
    return game_genres[0] if game_genres else "Other"


def tidy_genres(genres):
    return [g for g in genres if g not in NON_GAME_GENRES] or ["Other"]


# ---------- sources ----------

def fetch_stores():
    stores = get_json("https://www.cheapshark.com/api/1.0/stores") or []
    return {
        s["storeID"]: {
            "name": s["storeName"],
            "icon": "https://www.cheapshark.com" + s["images"]["icon"],
        }
        for s in stores
    }


def deal_link(deal_id):
    # CheapShark asks that deals link through their redirect.
    return f"https://www.cheapshark.com/redirect?dealID={deal_id}"


def fetch_giveaways(genres):
    items = get_json("https://www.gamerpower.com/api/giveaways?type=game&sort-by=date") or []
    out = []
    for g in items:
        if g.get("status") != "Active":
            continue
        tags = tidy_genres(genres.by_title(g["title"]))
        out.append({
            "id": f"gp-{g['id']}",
            "title": clean_giveaway_title(g["title"]),
            "worth": g.get("worth") if g.get("worth") not in (None, "N/A") else "",
            "image": g.get("image") or g.get("thumbnail"),
            "fallback": g.get("thumbnail"),
            "url": g.get("open_giveaway_url") or g.get("gamerpower_url"),
            "platforms": g.get("platforms", ""),
            "ends": "" if g.get("end_date") in (None, "N/A") else g["end_date"][:10],
            "description": g.get("description", ""),
            "genres": tags,
            "genre": primary_genre(tags),
        })
    return out


def fetch_deals(stores, genres):
    raw = []
    for page in range(DEAL_PAGES):
        batch = get_json(
            "https://www.cheapshark.com/api/1.0/deals?"
            f"sortBy=Deal%20Rating&pageSize=60&pageNumber={page}&onSale=1&AAA=0"
        ) or []
        raw.extend(batch)
        time.sleep(1)
    free_on_store = get_json("https://www.cheapshark.com/api/1.0/deals?upperPrice=0&pageSize=60") or []

    # keep the cheapest deal per game
    best = {}
    for d in raw + free_on_store:
        cur = best.get(d["gameID"])
        if cur is None or float(d["salePrice"]) < float(cur["salePrice"]):
            best[d["gameID"]] = d

    deals, free = [], []
    for d in best.values():
        found = genres.by_appid(d["steamAppID"]) if d.get("steamAppID") else []
        tags = tidy_genres(found or genres.by_title(d["title"]))  # bundles have no Steam genres
        store = stores.get(d["storeID"], {"name": "Store", "icon": ""})
        item = {
            "id": f"cs-{d['dealID']}",
            "title": d["title"],
            "price": float(d["salePrice"]),
            "normal": float(d["normalPrice"]),
            "savings": round(float(d["savings"])),
            "store": store["name"],
            "storeIcon": store["icon"],
            "rating": int(d.get("steamRatingPercent") or 0),
            "ratingText": d.get("steamRatingText") or "",
            "metacritic": int(d.get("metacriticScore") or 0),
            "image": (
                f"https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{d['steamAppID']}/header.jpg"
                if d.get("steamAppID") else d.get("thumb")
            ),
            "fallback": d.get("thumb"),
            "url": deal_link(d["dealID"]),
            "dealRating": float(d.get("dealRating") or 0),
            "genres": tags,
            "genre": primary_genre(tags),
        }
        if item["price"] == 0 and item["normal"] > 0:
            free.append({
                "id": item["id"], "title": item["title"],
                "worth": f"${item['normal']:.2f}", "image": item["image"],
                "fallback": item["fallback"], "url": item["url"],
                "platforms": item["store"], "ends": "", "description": "",
                "genres": tags, "genre": item["genre"],
            })
        elif item["price"] > 0:
            deals.append(item)
    deals.sort(key=lambda x: (-x["dealRating"], -x["savings"]))
    return deals, free


# ---------- output ----------

def build_site(payload):
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "index.html").write_text(template.replace("__DATA__", blob), encoding="utf-8")
    save_json(DOCS / "data.json", payload)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


def email_digest(new_free, new_deals, updated):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    to = [a.strip() for a in os.environ.get("EMAIL_TO", user or "").split(",") if a.strip()]
    site = os.environ.get("SITE_URL", "")

    if not (user and password and to):
        print("Email not configured (SMTP_USER / SMTP_PASSWORD / EMAIL_TO) - skipping.")
        return

    def row(g, right):
        return (
            f'<tr><td style="padding:6px 0"><a href="{escape(g["url"])}" style="color:#1a73e8;'
            f'text-decoration:none;font-weight:600">{escape(g["title"])}</a>'
            f'<div style="color:#777;font-size:12px">{escape(g["genre"])}</div></td>'
            f'<td style="padding:6px 0;text-align:right;white-space:nowrap">{right}</td></tr>'
        )

    parts = ['<!doctype html><html><head><meta charset="utf-8"></head><body>'
             '<div style="font-family:Arial,sans-serif;max-width:600px;color:#222">'
             '<div style="background:linear-gradient(90deg,#24135f,#0b3a52);background-color:#1a1440;'
             'color:#fff;padding:16px 20px;border-radius:10px;margin-bottom:16px">'
             '<div style="font-size:22px;font-weight:bold;letter-spacing:1px">🎮 LOOT DROP</div>'
             f'<div style="color:#b9c0ff;font-size:13px">Updated {updated}</div></div>']
    if new_free:
        parts.append(f'<h3 style="color:#0a8a3a">🎁 {len(new_free)} new free game(s)</h3><table width="100%">')
        parts += [row(g, f'<b style="color:#0a8a3a">FREE</b> <s style="color:#999">{escape(g["worth"])}</s>')
                  for g in new_free]
        parts.append("</table>")
    if new_deals:
        top = new_deals[:15]
        parts.append(f'<h3>🔥 {len(new_deals)} new deal(s) - top {len(top)}</h3><table width="100%">')
        parts += [row(d, f'<b>${d["price"]:.2f}</b> <span style="color:#c62828">-{d["savings"]}%</span> '
                         f'<span style="color:#999;font-size:12px">{escape(d["store"])}</span>')
                  for d in top]
        parts.append("</table>")
    if site:
        parts.append(f'<p style="margin-top:20px"><a href="{escape(site)}" style="background:#1a73e8;color:#fff;'
                     f'padding:10px 16px;border-radius:6px;text-decoration:none">See everything by genre</a></p>')
    parts.append("</div></body></html>")

    subject = "Loot Drop: "
    subject += f"{len(new_free)} free game(s), " if new_free else ""
    subject += f"{len(new_deals)} new deal(s)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText("".join(parts), "html", "utf-8"))

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context()) as s:
        s.login(user, password)
        s.sendmail(user, to, msg.as_string())
    print(f"Emailed {', '.join(to)}")


def main():
    genres = Genres()
    print("Fetching stores...")
    stores = fetch_stores()
    print("Fetching giveaways...")
    free = fetch_giveaways(genres)
    print("Fetching deals...")
    deals, free_on_store = fetch_deals(stores, genres)
    genres.save()

    # if a source is down, keep yesterday's listings instead of publishing an empty site
    previous = load_json(DOCS / "data.json", {})
    if not deals and previous.get("deals"):
        print("  ! no deals fetched - keeping previous deals")
        deals = previous["deals"]
    if not free and not free_on_store and previous.get("free"):
        print("  ! no giveaways fetched - keeping previous free games")
        free = previous["free"]

    seen_titles = {normalize(g["title"]) for g in free}
    free += [g for g in free_on_store if normalize(g["title"]) not in seen_titles]

    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_genres = sorted({g for x in free + deals for g in x["genres"]},
                        key=lambda g: (GENRE_PRIORITY.index(g) if g in GENRE_PRIORITY else 99, g))
    build_site({"updated": updated, "free": free, "deals": deals, "genres": all_genres})
    print(f"Built site: {len(free)} free, {len(deals)} deals, {len(all_genres)} genres, "
          f"{genres.lookups} new genre lookups")

    state = load_json(STATE_FILE, {"seen": []})
    seen = set(state["seen"])
    new_free = [g for g in free if g["id"] not in seen]
    new_deals = [d for d in deals if d["id"] not in seen]
    if new_free or new_deals:
        if "--no-email" in sys.argv:
            print(f"(--no-email) would email {len(new_free)} free, {len(new_deals)} deals")
        else:
            email_digest(new_free, new_deals, updated)
    else:
        print("Nothing new - no email.")
    save_json(STATE_FILE, {"seen": sorted(seen | {x["id"] for x in free + deals})})


if __name__ == "__main__":
    main()
