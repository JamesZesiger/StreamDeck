# neko container notes

The `neko` service streams a Chromium browser (with Widevine L3) to your web browser over
WebRTC. You watch and control it from the StreamDeck player page, which embeds neko in an
iframe.

## One-time sign-in

Open the player for any embedded-mode title, click into the streamed browser, and sign in to
the service normally (use the "Show credentials" button in the toolbar to copy from `.env`).
The Chromium profile is on the `neko-profile` volume, so logins persist across
`docker compose restart neko`.

## Auto-navigation on Play (extension WebSocket)

Clicking Play navigates the streamed browser automatically. The mechanism: the StreamDeck
helper extension (`neko/extension/`, loaded via `--load-extension` in `chromium.conf`) keeps a
WebSocket open to the app (`ws://app:8000/ws/nav`); Play broadcasts a navigate message and the
extension steers the active tab with `chrome.tabs.update`. The app pings every 20s to keep the
extension's MV3 service worker alive.

CDP was the original mechanism and remains a fallback (`NEKO_CDP_URL`, via `cdp_proxy.py`),
but modern headful Chromium (150+) closes the DevTools server shortly after startup as part of
Chrome's remote-debugging hardening — don't rely on it.

Pieces that make this work (already wired in `docker-compose.yml`):

- `./neko/chromium.conf` overrides the image's supervisord config: loads the extension,
  drops `--bwsi` (guest mode doesn't persist cookies), moves the profile to
  `.../chromium/profile` (a non-default dir, required for any debugging), and runs
  `cdp_proxy.py`.
- `./neko/policies/` overrides the image's Chromium policies: `DeveloperToolsAvailability`
  set to allowed and the `ExtensionInstallBlocklist: ["*"]` removed — the image's wildcard
  blocklist silently blocks `--load-extension`.
- `hostname: nekobrowser` is pinned: Chromium's profile `SingletonLock` embeds the hostname,
  and without a fixed one every container recreate leaves a stale lock that crash-loops the
  browser. If Chromium ever refuses to start after unclean shutdowns, clear it with:
  `docker run --rm -v personalresearch_neko-profile:/p alpine rm -f /p/profile/Singleton*`

If the neko image is upgraded, re-extract `chromium.conf` and `policies.json` from the new
image and re-apply the same edits.

## Quality expectations

Chromium on Linux uses Widevine L3 (software), so services cap streams around **720p**, some
at SD. This is a hard platform limit — the "Open in browser (best quality)" button on every
title is the intended path when you want 1080p/4K via your local browser.

## WSL2 / WebRTC

WebRTC uses UDP ports 52000–52100 (published in compose). If video doesn't start when viewing
from another device on your LAN, set `NEKO_NAT1TO1=<your LAN IP>` on the neko service so ICE
candidates advertise a reachable address.
