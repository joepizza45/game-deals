# Loot Drop — Daily Game Deals

Free game giveaways and the best PC game deals, sorted by genre.
Live site: https://joepizza45.github.io/game-deals/

**Where the data comes from**
- **Free games:** [GamerPower](https://www.gamerpower.com) (Epic, Steam, GOG, Prime Gaming, etc.) plus $0 deals on [CheapShark](https://www.cheapshark.com)
- **Deals:** CheapShark, which tracks legit key stores: Steam, GOG, Humble, Fanatical, Green Man Gaming, GamersGate, IndieGala, WinGameStore and others
- **Genres:** the Steam store

## How it updates
A Windows scheduled task, **Loot Drop daily update**, runs `update.ps1` every day at 10:00 AM. It:
1. runs `deals.py`, which fetches everything and rebuilds `docs/`
2. commits `docs/` and `data/` and pushes them to GitHub, and GitHub Pages serves `docs/`

It runs on this PC instead of GitHub's servers because CheapShark blocks requests from GitHub's servers.
If the PC is off at 10 AM, the task runs the next time you log in.
If a data source is down, the site keeps the previous day's listings.

- **Run it now:** Task Scheduler → *Loot Drop daily update* → Run
- **See what happened:** `update.log`
- **Change the time:** Task Scheduler → *Loot Drop daily update* → Triggers

Needs Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312`), Git, and the GitHub CLI signed in as joepizza45.

## Email digests (off for now)
`deals.py` can email you only the *new* free games and deals each day. To turn it on:
1. Create a Gmail app password at https://myaccount.google.com/apppasswords (needs 2-Step Verification).
2. Set these as Windows user environment variables: `SMTP_USER` (your Gmail), `SMTP_PASSWORD` (the app password),
   `EMAIL_TO` (where to send) and `SITE_URL` (`https://joepizza45.github.io/game-deals/`).

## Tweaks
- More or fewer deals: change `DEAL_PAGES` in `deals.py` (60 deals per page).
- Which section a game goes in: games often have several Steam genres. The first one found in
  `GENRE_PRIORITY` decides its section. Clicking a genre chip shows every game with that genre.

## Why not CDKeys / G2A / Kinguin?
Those are key resellers ("grey market") with no public price data, and their terms forbid scraping.
