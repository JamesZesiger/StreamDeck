# StreamDeck

A personal, Dockerized launcher for your paid streaming services. Curate a library of titles
with artwork and details (from TMDB), browse them as tiles, and play them through each
service's own signed-in web player — deep-linked into your local browser for full quality.

**Nothing is downloaded, no DRM is circumvented, no sites are scraped.** See
[DESIGN.md](DESIGN.md) for architecture, decisions, and limits.

## Quick start

```bash
cp .env.example .env
# Fill in: TMDB_API_KEY (free from themoviedb.org) and the Postgres password.

docker compose up -d --build
```

- Library UI: http://localhost:8000

## Usage

1. **Add a title** — click *+ Add title*, paste the title's link from the streaming service
   (e.g. `https://www.netflix.com/title/...`), search by name, pick the TMDB match.
2. **Play** — each title's *▶ Play* opens its deep link in a new browser tab, in the
   service's own player, signed in to your account (Edge/Chrome on Windows negotiate
   PlayReady up to 4K).
3. **Sites** — the *Sites* page lists all configured services and has an *Add custom site*
   button (name, domain, optional TMDB provider id). The site list lives in
   `config/sites.json` (gitignored, created on first startup); manual edits apply on restart.
   Sign-in happens in your own browser session — no credentials are stored.

## Stack

FastAPI · PostgreSQL · Jinja2 + Tailwind + htmx · TMDB API for metadata.
