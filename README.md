# StreamDeck

A personal, Dockerized launcher for your paid streaming services. Curate a library of titles
with artwork and details (from TMDB), browse them as tiles, and play them through each
service's own signed-in web player — embedded via a streamed server-side browser, or
deep-linked to your local browser for full quality.

**Nothing is downloaded, no DRM is circumvented, no sites are scraped.** See
[DESIGN.md](DESIGN.md) for architecture, decisions, and limits.

## Quick start

```bash
cp .env.example .env
# Fill in: TMDB_API_KEY (free from themoviedb.org), Postgres + neko passwords,
# and optionally your streaming credentials (SVC_*) for the sign-in helper.

docker compose up -d --build
```

- Library UI: http://localhost:8000
- Streamed browser (neko): http://localhost:8080

## Usage

1. **Add a title** — click *+ Add title*, paste the title's link from the streaming service
   (e.g. `https://www.netflix.com/title/...`), search by name, pick the TMDB match.
2. **Play (embedded)** — the player page streams a server-side Chromium. First time per
   service, sign in inside the stream (cookies persist). Quality caps ~720p (Widevine L3).
3. **Play (best quality)** — every title also has *Open in browser*, which deep-links the
   title into your local browser tab.
4. Per-service playback mode (`embedded` vs `deeplink`) lives in the `services` table.

Optional: enable auto-navigation on Play (the app steering the streamed browser to the title)
— see [neko/README.md](neko/README.md).

## Stack

FastAPI · PostgreSQL · Jinja2 + Tailwind + htmx · [m1k1o/neko](https://github.com/m1k1o/neko)
(WebRTC-streamed Chromium) · TMDB API for metadata.
