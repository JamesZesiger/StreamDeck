# neko container notes

The `neko` service streams a Chromium browser (with Widevine L3) to your web browser over
WebRTC. You watch and control it from the StreamDeck player page, which embeds neko in an
iframe.

## One-time sign-in

Open the player for any embedded-mode title, click into the streamed browser, and sign in to
the service normally (use the "Show credentials" button in the toolbar to copy from `.env`).
The Chromium profile is on the `neko-profile` volume, so logins persist across
`docker compose restart neko`.

## Optional: auto-navigation on Play (CDP)

Out of the box, clicking Play opens the player and you paste the title link into the streamed
browser (the toolbar has a Copy-link button). To make Play navigate the streamed browser
automatically, the Chromium inside the container must expose the DevTools protocol:

1. Extract the image's original supervisord config:

   ```bash
   docker compose create neko
   docker compose cp neko:/etc/neko/supervisord/chromium.conf ./neko/chromium.conf
   ```

2. Edit `./neko/chromium.conf` and append these flags to the chromium `command=` line:

   ```
   --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0
   ```

   To also load the chrome-hiding extension, append:

   ```
   --load-extension=/opt/streamdeck-extension
   ```

3. Uncomment the `./neko/chromium.conf` volume mount in `docker-compose.yml`, and set
   `NEKO_CDP_URL=http://neko:9222` in `.env`. Recreate: `docker compose up -d --force-recreate neko`.

The port 9222 is **not** published to the host — only the `app` container reaches it on the
compose network. If the neko image is upgraded, re-extract the conf and re-apply the flags
(`neko/chromium.conf` is gitignored since it derives from the image).

## Quality expectations

Chromium on Linux uses Widevine L3 (software), so services cap streams around **720p**, some
at SD. This is a hard platform limit — the "Open in browser (best quality)" button on every
title is the intended path when you want 1080p/4K via your local browser.

## WSL2 / WebRTC

WebRTC uses UDP ports 52000–52100 (published in compose). If video doesn't start when viewing
from another device on your LAN, set `NEKO_NAT1TO1=<your LAN IP>` on the neko service so ICE
candidates advertise a reachable address.
