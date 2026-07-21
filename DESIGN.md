# StreamDeck — Design Document

A personal, Dockerized launcher/harness for paid streaming services. You curate a library of
titles; the app shows them as tiles, gives a detail view, and plays them through the services'
own signed-in web players — either embedded (a server-side browser streamed into the UI) or by
deep-linking to your local browser.

## Goals

- Tile-grid library → detail view → Play → fullscreen video.
- Metadata (title, poster, description, runtime, year) stored locally in PostgreSQL.
- Playback always happens through the streaming service's own player, signed in to the
  user's paid account.
- Hide as much of the service's site chrome as practical — show the video.
- Single user, home LAN, `docker compose up`.

## Non-goals / hard rules

- **No downloading or capturing of media.** Nothing is written to disk except the app database
  and the browser profile volume.
- **No DRM circumvention, no attestation/integrity spoofing.** Widevine L3 limits are accepted,
  not worked around.
- **No credential sharing beyond the owner's own accounts.** Credentials live in `.env` on the
  owner's machine only.
- **No crawling/scraping of streaming sites.** Metadata comes from the TMDB API; service pages
  are only ever loaded to *play* content as a normal signed-in browser would.

## Architecture

```mermaid
flowchart LR
    subgraph client [Your browser / TV browser]
        UI[Library UI\ntiles, detail, player page]
        LOCAL[Local browser tab\n(deep-link mode)]
    end
    subgraph compose [docker compose]
        APP[app\nFastAPI + Jinja2 + htmx]
        DB[(db\nPostgreSQL 16)]
        NEKO[neko\nChromium + Widevine L3\nstreamed via WebRTC]
        VOL[[neko-profile volume\npersistent cookies/logins]]
    end
    TMDB[(TMDB API)]
    SVC[(Streaming services\nNetflix / Disney+ / Hulu ...)]

    UI -->|HTML/htmx| APP
    APP --> DB
    APP -->|search/details| TMDB
    UI -->|WebRTC video/audio + input| NEKO
    APP -->|navigate on Play\n(CDP, optional)| NEKO
    NEKO --- VOL
    NEKO -->|signed-in playback| SVC
    LOCAL -->|deep link, full quality| SVC
```

### Components

| Container | Image | Role |
|---|---|---|
| `app` | local build (`python:3.12-slim`) | FastAPI backend + server-rendered UI (Jinja2, Tailwind CDN, htmx) |
| `db` | `postgres:16-alpine` | Library metadata |
| `neko` | `m1k1o/neko:chromium` | Chromium with Widevine, display/audio streamed to the browser over WebRTC; keyboard/mouse pass through |

## Playback model (hybrid)

Each service has a `playback_mode`:

- **`embedded`** (default for Netflix, Disney+, Hulu, Prime Video, Max): Play opens
  `/titles/{id}/play`, a page that is a full-viewport iframe of the neko session. On the way,
  the app best-effort navigates the streamed Chromium to the title's deep link (see
  *Navigation* below). Quality ceiling: **Widevine L3 ⇒ ~720p, SD on some services.**
- **`deeplink`** (default for YouTube; selectable per service): Play is a plain link that opens
  the title in *your local* browser tab — full quality (Edge on Windows negotiates PlayReady
  up to 4K). Embedded titles also always show a secondary “Open in browser (best quality)”
  button.

### Navigation of the streamed browser

neko itself exposes no “navigate to URL” REST endpoint, so the app uses the Chrome DevTools
Protocol when available: if `NEKO_CDP_URL` is set (and the neko Chromium was started with
`--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0` via the supervisord override
documented in `neko/README.md`), the app calls `Page.navigate` over the CDP websocket when Play
is clicked. If CDP is not configured or unreachable, the player page degrades gracefully: it
shows the title link with a copy button so you can paste it into the streamed browser's address
bar. CDP here is used *only* to navigate — it is a remote control, not a scraper.

### Sign-in

The user signs in to each service **once, manually**, inside the streamed browser (input passes
through neko). The Chromium profile lives on the `neko-profile` volume, so cookies survive
restarts. Scripted/automated logins are deliberately avoided — they are the main trigger for
bot detection. Credentials in `.env` (`SVC_<SLUG>_USERNAME/PASSWORD`) are surfaced in the
player page behind a “Show credentials” control purely as a convenience for that one-time
sign-in.

### Hiding site chrome

`neko/extension/` contains a tiny MV3 Chromium extension (loaded with `--load-extension`, see
`neko/README.md`) whose content scripts inject per-domain CSS hiding headers/nav on
netflix.com, disneyplus.com, hulu.com. This is polish, not a foundation: title deep links on
these services already land in a near-chromeless player, and service DOMs drift, so the CSS
degrades gracefully to “you briefly see the site.”

## Metadata: TMDB

- Free API key in `.env` (`TMDB_API_KEY`).
- **Add-item flow:** paste the streaming URL → app detects the service from the domain
  (`services_registry.py`) → user types the title and picks the right match from TMDB
  `search/multi` results → app fetches details (`/movie/{id}` or `/tv/{id}`) and stores
  everything locally. No streaming site is ever fetched by the server.

## Data model

- `services`: `id`, `name`, `slug`, `base_domain`, `icon_path`, `playback_mode`
  (`embedded|deeplink`), `enabled`. Seeded on first startup.
- `titles`: `id`, `service_id→services`, `tmdb_id`, `media_type` (`movie|tv`), `title`,
  `overview`, `poster_url`, `backdrop_url`, `runtime_minutes`, `release_year`, `deep_link`,
  `watched`, `added_at`, `last_played_at`.

Schema is created with `create_all` on startup; Alembic can be introduced when the schema
starts changing.

## Routes

| Route | Kind | Purpose |
|---|---|---|
| `GET /` | page | Tile grid; `?service=` and `?watched=` filters |
| `GET /add` | page | Add-item flow (paste URL → TMDB search → confirm) |
| `GET /titles/{id}` | page | Detail view (backdrop hero, metadata, Play buttons) |
| `GET /titles/{id}/play` | page | Embedded player (neko iframe); triggers CDP navigate + stamps `last_played_at` |
| `POST /api/resolve-url` | htmx | Detect service from pasted URL + TMDB search results partial |
| `POST /api/titles` | htmx | Create title from a chosen TMDB match |
| `PATCH /api/titles/{id}/watched` | htmx | Toggle watched |
| `DELETE /api/titles/{id}` | htmx | Remove from library |
| `GET /api/credentials/{slug}` | htmx | Reveal `.env` credentials for one-time sign-in |
| `GET /healthz` | JSON | Liveness |

## Risks and accepted limits

- **Quality:** Widevine L3 in a Linux container caps embedded playback around 720p (SD on some
  services). Deep-link mode is the escape hatch, not a workaround inside the container.
- **Bot detection:** services may challenge logins from unusual environments. Persistent
  manual login mitigates; if a service blocks the container entirely, flip it to `deeplink`.
- **neko on WSL2:** WebRTC wants a UDP port range published; if Docker Desktop networking
  fights it, neko's TCP fallback works at some latency cost. Budget ~1–2 GB RAM for encoding.
- **Version drift:** the neko image tag should be pinned; the CDP supervisord override is the
  piece most likely to need adjusting after an image upgrade.
- **Runtime internet:** Tailwind/htmx CDNs and TMDB require outbound internet.

## Milestones

- **M0** — this document.
- **M1** — library core: `app`+`db` compose, models/seed, TMDB client, add flow, tiles + detail.
- **M2** — deep-link playback, watched tracking.
- **M3** — embedded playback: neko container, profile volume, player iframe, CDP navigate.
- **M4** — polish: chrome-hiding extension, credentials helper, filters, README.
