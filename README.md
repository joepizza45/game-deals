# Loot Drop — Daily Game Deals

A website that lists free game giveaways and the best PC game deals, sorted by genre.
It rebuilds itself every day and emails you a digest of anything new.

**Where the data comes from**
- **Free games:** [GamerPower](https://www.gamerpower.com) (Epic, Steam, GOG, Prime Gaming, etc.) plus $0 deals on [CheapShark](https://www.cheapshark.com)
- **Deals:** CheapShark, which tracks legit key stores: Steam, GOG, Humble, Fanatical, Green Man Gaming, GamersGate, IndieGala, WinGameStore and others
- **Genres:** the Steam store

Everything is free. No API keys and no paid hosting.

## Setup (about 10 minutes, one time)

### 1. Put the files on GitHub
1. Create a free account at https://github.com if you don't have one.
2. Click **New repository**, name it something like `game-deals`, make it **Public**, and create it.
3. On the new repo page click **uploading an existing file** and drag in everything from this folder
   (`deals.py`, `template.html`, `README.md`, the `data` folder and the `.github` folder). Click **Commit changes**.
   The `data` folder holds genres already looked up, which makes the first run faster.
   > If the `.github` folder doesn't upload by dragging, use **Add file → Create new file**, type
   > `.github/workflows/daily.yml` as the name, and paste in the contents of that file.

### 2. Set up email (Gmail)
1. Turn on 2-Step Verification on your Google account, then go to https://myaccount.google.com/apppasswords
   and create an app password named "Game Deals". Copy the 16-character password.
2. In your GitHub repo go to **Settings → Secrets and variables → Actions → New repository secret** and add:
   | Name | Value |
   |---|---|
   | `SMTP_USER` | your Gmail address |
   | `SMTP_PASSWORD` | the 16-character app password |
   | `EMAIL_TO` | where to send the emails (comma-separate for more than one) |

   Not using Gmail? Also add `SMTP_HOST` and `SMTP_PORT` secrets for your provider and add them to the
   `env:` block in `.github/workflows/daily.yml`.

### 3. Run it the first time
1. Go to the **Actions** tab and enable workflows if GitHub asks.
2. Click **Daily deals update → Run workflow**. It takes 3–5 minutes on the first run while it looks up genres.
   You should get your first email when it finishes.

### 4. Turn on the website
1. **Settings → Pages**, set Source to **Deploy from a branch**, branch `main`, folder `/docs`, and save.
2. A minute later your site is live at `https://YOUR-USERNAME.github.io/game-deals/`.

After this it runs every day at 14:00 UTC by itself. To change the time, edit the `cron` line in
`.github/workflows/daily.yml` ([cron helper](https://crontab.guru)).

## How it decides what to email
The script remembers every giveaway and deal it has shown you (`data/state.json`). Each day it emails
only the **new** free games and the top new deals. If nothing changed, it doesn't send an email.

## Tweaks
- More or fewer deals: change `DEAL_PAGES` in `deals.py` (60 deals per page).
- Which section a game goes in: games often have several Steam genres. The first one found in
  `GENRE_PRIORITY` decides its section. Clicking a genre chip shows every game with that genre.
- Run locally: `python deals.py --no-email`, then open `docs/index.html`.

## Why not CDKeys / G2A / Kinguin?
Those are key resellers ("grey market") with no public price data, and their terms forbid scraping.
This site sticks to stores CheapShark tracks. You can still check those resellers yourself for a game you find here.
