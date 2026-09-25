# TMDB watch-provider IDs (US)

The `tmdb_provider_id` in [`app/sites.py`](../app/sites.py) is one of these
numbers. streamDeck passes it to TMDB's `/discover` as `with_watch_providers`
for the "Add all" preload, and matches it against each title's
`watch/providers` data to fill in `regions`. The data is JustWatch's, served
through TMDB.

This is the US list only (336 providers), pulled from
`/watch/providers/movie` and `/watch/providers/tv` with `watch_region=US` on
2026-09-25. Other countries have providers that aren't listed here.

## Already used by streamDeck

| ID | TMDB name | `sites.py` slug |
|---:|---|---|
| 8 | Netflix | `netflix` |
| 337 | Disney Plus | `disneyplus` |
| 15 | Hulu | `hulu` |
| 9 | Amazon Prime Video | `primevideo` |
| 1899 | HBO Max | `max` |

The `youtube` site has no provider ID set, so it can't use "Add all". TMDB
does list YouTube under four IDs:

| ID | Name | What it covers |
|---:|---|---|
| 192 | YouTube | Rent/buy, which streamDeck ignores |
| 235 | YouTube Free | Free, ad-supported movies |
| 188 | YouTube Premium | YouTube Originals |
| 2528 | YouTube TV | The live-TV subscription |

235 is the one to set for "Add all" to pull free YouTube movies.

## Things to know when picking an ID

- **Pick the service itself, not a channel.** Many services are also listed
  as add-on channels with their own IDs, such as "HBO Max Amazon Channel"
  (1825) alongside "HBO Max" (1899). The channel IDs only cover titles
  watched through that storefront.
- **"Store" entries are rent/buy.** "Apple TV Store" (2), "Amazon Video"
  (10) and "Google Play Movies" (3) are rent-or-buy storefronts, not
  subscriptions. streamDeck counts only subscription, free and ad-supported
  availability (see `_provider_regions` in `app/tmdb.py`), so these match
  little or nothing.
- **Names change; IDs don't.** For example, TMDB calls 1899 "HBO Max", not
  "Max". Look services up by ID.

## Most prominent 25

Ordered by TMDB's US display priority, the order JustWatch shows them in.

| ID | Name | Catalog | US priority |
|---:|---|---|---:|
| 15 | Hulu | Movies + TV | 1 |
| 8 | Netflix | Movies + TV | 3 |
| 9 | Amazon Prime Video | Movies + TV | 4 |
| 350 | Apple TV | Movies + TV | 5 |
| 337 | Disney Plus | Movies + TV | 6 |
| 2285 | JustWatch TV | Movies + TV | 7 |
| 10 | Amazon Video | Movies + TV | 8 |
| 2 | Apple TV Store | Movies + TV | 9 |
| 257 | fuboTV | Movies + TV | 10 |
| 1825 | HBO Max Amazon Channel | Movies + TV | 11 |
| 283 | Crunchyroll | Movies + TV | 12 |
| 583 | MGM+ Amazon Channel | Movies + TV | 13 |
| 2303 | Paramount Plus Premium | Movies + TV | 14 |
| 2616 | Paramount Plus Essential | Movies + TV | 15 |
| 386 | Peacock Premium | Movies + TV | 16 |
| 2383 | Philo | Movies + TV | 17 |
| 2736 | Brew | Movies | 18 |
| 190 | Curiosity Stream | Movies + TV | 19 |
| 3 | Google Play Movies | Movies + TV | 20 |
| 192 | YouTube | Movies + TV | 21 |
| 1968 | Crunchyroll Amazon Channel | Movies + TV | 22 |
| 1853 | Paramount Plus Apple TV channel | TV | 23 |
| 1854 | AMC Plus Apple TV channel | Movies + TV | 24 |
| 1852 | Britbox Apple TV channel | Movies + TV | 25 |
| 582 | Paramount+ Amazon Channel | Movies + TV | 26 |

## All 336 US providers

Alphabetical. **Catalog** says whether TMDB lists the provider for movies, TV,
or both.

| ID | Name | Catalog | US priority |
|---:|---|---|---:|
| 156 | A&E | Movies + TV | 51 |
| 2033 | A&E Crime Central Apple TV channel | Movies + TV | 180 |
| 148 | ABC | Movies + TV | 255 |
| 2314 | Acaciatv Amazon Channel | Movies | 221 |
| 87 | Acorn TV | Movies + TV | 54 |
| 2034 | Acorn TV Apple TV channel | Movies + TV | 181 |
| 196 | AcornTV Amazon Channel | Movies + TV | 86 |
| 1958 | AD tv | Movies + TV | 162 |
| 318 | Adult Swim | Movies + TV | 92 |
| 532 | aha | Movies + TV | 147 |
| 2316 | Alchemiya Amazon Channel | Movies + TV | 222 |
| 2317 | All warrior network Amazon Channel | Movies + TV | 223 |
| 251 | ALLBLK | Movies + TV | 60 |
| 2064 | ALLBLK Amazon channel  | Movies + TV | 215 |
| 2036 | ALLBLK Apple TV channel | Movies + TV | 182 |
| 2679 | Amasian TV | Movies + TV | 358 |
| 1898 | Amazon MX Player | Movies + TV | 382 |
| 9 | Amazon Prime Video | Movies + TV | 4 |
| 613 | Amazon Prime Video Free with Ads | Movies + TV | 140 |
| 2100 | Amazon Prime Video with Ads | Movies + TV | 202 |
| 10 | Amazon Video | Movies + TV | 8 |
| 80 | AMC | Movies + TV | 44 |
| 1854 | AMC Plus Apple TV channel | Movies + TV | 24 |
| 526 | AMC+ | Movies + TV | 31 |
| 528 | AMC+ Amazon Channel | Movies + TV | 28 |
| 635 | AMC+ Roku Premium Channel | Movies + TV | 30 |
| 2318 | Amebatv Amazon Channel | Movies + TV | 224 |
| 1956 | Angel Studios | Movies + TV | 160 |
| 399 | Animal Planet | TV | 108 |
| 350 | Apple TV | Movies + TV | 5 |
| 2243 | Apple TV Amazon Channel | Movies + TV | 216 |
| 2 | Apple TV Store | Movies + TV | 9 |
| 529 | ARROW | Movies + TV | 363 |
| 2623 | Artiflix | Movies | 356 |
| 2685 | Artify | Movies + TV | 360 |
| 514 | AsianCrush | Movies + TV | 116 |
| 2320 | Aspire TV Amazon Channel | Movies + TV | 225 |
| 2324 | Baeble Amazon Channel | Movies | 229 |
| 397 | BBC America | Movies + TV | 101 |
| 2039 | BBC Select Apple Tv channel | Movies + TV | 194 |
| 2321 | BeFit Amazon Channel | Movies + TV | 226 |
| 2323 | Best of British Tv Amazon Channel | Movies + TV | 228 |
| 2322 | Best tv ever Amazon Channel | TV | 227 |
| 2325 | Best Westerns Ever Amazon Channel | Movies + TV | 230 |
| 287 | BFI Player Amazon Channel | Movies | 233 |
| 2786 | BINGE Movies & TV | Movies + TV | 378 |
| 2555 | Bloodstream | Movies | 340 |
| 365 | Bravo TV | TV | 98 |
| 2736 | Brew | Movies | 18 |
| 151 | BritBox | Movies + TV | 58 |
| 197 | BritBox Amazon Channel | Movies + TV | 87 |
| 1852 | Britbox Apple TV channel | Movies + TV | 25 |
| 2326 | Broadway HD Amazon Channel | Movies + TV | 231 |
| 554 | BroadwayHD | Movies + TV | 128 |
| 2327 | Brown Sugar Amazon Channel | Movies + TV | 232 |
| 2129 | BYUtv | Movies + TV | 73 |
| 2620 | CaixaForum+ | Movies + TV | 353 |
| 2071 | Carnegie Hall+ Amazon Channel | Movies | 199 |
| 2042 | Carnegie Hall+ Apple TV channel | Movies | 195 |
| 438 | Chai Flicks | Movies + TV | 81 |
| 2703 | Chilling | Movies | 361 |
| 289 | Cinemax Amazon Channel | Movies + TV | 68 |
| 2061 | Cinemax Apple TV channel | Movies + TV | 193 |
| 1957 | Cineverse | Movies + TV | 161 |
| 2704 | Cineverse Amazon Channel | Movies + TV | 362 |
| 2393 | Cocina ON Amazon Channel | TV | 245 |
| 1811 | Cohen Media Amazon Channel | Movies + TV | 153 |
| 258 | Criterion Channel | Movies + TV | 40 |
| 283 | Crunchyroll | Movies + TV | 12 |
| 1968 | Crunchyroll Amazon Channel | Movies + TV | 22 |
| 692 | Cultpix | Movies + TV | 144 |
| 190 | Curiosity Stream | Movies + TV | 19 |
| 603 | CuriosityStream Amazon Channel | Movies + TV | 357 |
| 2060 | CuriosityStream Apple TV channel | Movies + TV | 192 |
| 2368 | Daily Burn Amazon Channel | TV | 236 |
| 2494 | dAnime Amazon Channel | TV | 331 |
| 2369 | Daring Docs Amazon Channel | Movies | 237 |
| 2308 | Darkroom | Movies + TV | 137 |
| 444 | Dekkoo | Movies + TV | 77 |
| 2371 | Dekkoo Amazon Channel | Movies + TV | 238 |
| 2442 | Demand Africa Amazon Channel | Movies + TV | 288 |
| 403 | Discovery | TV | 109 |
| 520 | Discovery + | Movies + TV | 158 |
| 584 | Discovery+ Amazon Channel | Movies + TV | 27 |
| 337 | Disney Plus | Movies + TV | 6 |
| 508 | DisneyNOW | Movies + TV | 122 |
| 1971 | DistroTV | Movies + TV | 171 |
| 569 | DocAlliance Films | Movies | 134 |
| 2376 | DocCom Amazon Channel | Movies + TV | 239 |
| 475 | DOCSVILLE | Movies + TV | 117 |
| 604 | DocuBay Amazon Channel | Movies + TV | 380 |
| 2377 | DocuramaFilms Amazon Channel | Movies + TV | 240 |
| 2408 | Doki Amazon Channel | Movies + TV | 262 |
| 2378 | Dove Amazon Channel | Movies + TV | 241 |
| 2379 | Dox Amazon Channel | Movies + TV | 242 |
| 2452 | Dreamscape Kids Amazon Channel | Movies | 297 |
| 263 | DreamWorksTV Amazon Channel | TV | 113 |
| 2392 | Echoboom Amazon Channel  | Movies + TV | 244 |
| 2059 | Eros Now Select Apple TV channel | Movies + TV | 191 |
| 1718 | ESPN | Movies | 158 |
| 1768 | ESPN Plus | Movies | 164 |
| 2411 | Eternal Family | Movies + TV | 142 |
| 677 | Eventive | Movies | 145 |
| 60 | Fandango | Movies | 156 |
| 7 | Fandango At Home | Movies + TV | 37 |
| 332 | Fandango at Home Free | Movies + TV | 39 |
| 25 | Fandor | Movies | 47 |
| 199 | Fandor Amazon Channel | Movies + TV | 89 |
| 2409 | Fawesome | Movies + TV | 143 |
| 2394 | Fear Factory Amazon Channel | Movies | 246 |
| 2453 | FidoTV Channel Amazon Channel | TV | 298 |
| 579 | Film Movement Plus | Movies | 201 |
| 2395 | Film Movement Plus Amazon Channel | Movies | 247 |
| 602 | FilmBox Live Amazon Channel | Movies + TV | 257 |
| 701 | FilmBox+ | Movies + TV | 146 |
| 2782 | Filmtap | Movies | 377 |
| 559 | Filmzie | Movies | 130 |
| 2396 | Fitfusion Amazon Channel | Movies | 248 |
| 432 | Flix Premiere | Movies | 114 |
| 331 | FlixFling | Movies + TV | 94 |
| 2239 | FlixHouse | Movies | 43 |
| 2398 | Food Matters Amazon Channel | Movies + TV | 250 |
| 366 | Food Network | TV | 100 |
| 2478 | FOUND TV | Movies + TV | 326 |
| 2545 | FOX One | TV | 342 |
| 2554 | FOX One Amazon Channel | TV | 339 |
| 2400 | France Channel Amazon Channel | Movies + TV | 260 |
| 211 | Freeform | Movies + TV | 50 |
| 257 | fuboTV | Movies + TV | 10 |
| 2448 | FUEL TV+ Amazon Channel | Movies + TV | 293 |
| 597 | Full Moon Amazon Channel | Movies | 176 |
| 2401 | Fuse+ Amazon Channel | Movies + TV | 251 |
| 123 | FXNow | Movies + TV | 42 |
| 1962 | FYI Network | TV | 166 |
| 2164 | Gaia Amazon Channel | Movies + TV | 259 |
| 2480 | Gaiam TV Yoga & Fit | Movies + TV | 328 |
| 1990 | GlewedTV | Movies | 178 |
| 3 | Google Play Movies | Movies + TV | 20 |
| 2433 | Great American Pure Flix Amazon Channel | Movies + TV | 281 |
| 2454 | Green Planet Stream Amazon Channel | Movies | 299 |
| 100 | GuideDoc | Movies | 57 |
| 1746 | Hallmark TV Amazon Channel | Movies + TV | 337 |
| 290 | Hallmark+ Amazon Channel | Movies + TV | 69 |
| 2058 | Hallmark+ Apple TV channel | Movies + TV | 190 |
| 1899 | HBO Max | Movies + TV | 152 |
| 1825 | HBO Max Amazon Channel | Movies + TV | 11 |
| 417 | Here TV | Movies + TV | 111 |
| 2406 | Here TV  Amazon Channel | Movies + TV | 256 |
| 406 | HGTV | TV | 105 |
| 503 | Hi-YAH | Movies | 120 |
| 2403 | Hi-YAH Amazon Channel | Movies + TV | 253 |
| 430 | HiDive | Movies + TV | 74 |
| 2390 | Hidive Amazon Channel | Movies + TV | 243 |
| 155 | History | Movies + TV | 330 |
| 268 | History Vault | Movies | 61 |
| 2073 | HISTORY Vault Amazon Channel | Movies + TV | 198 |
| 2057 | HISTORY Vault Apple TV channel | Movies + TV | 197 |
| 315 | Hoichoi | Movies + TV | 136 |
| 212 | Hoopla | Movies + TV | 36 |
| 1890 | Hopster Amazon Channel | TV | 258 |
| 2754 | Howdy Amazon Channel | Movies + TV | 372 |
| 15 | Hulu | Movies + TV | 1 |
| 2056 | IFC Films Unlimited Apple TV channel | Movies + TV | 196 |
| 2404 | Indie Club Amazon Channel | Movies | 254 |
| 368 | IndieFlix | Movies | 102 |
| 2405 | IndieFlix Shorts Amazon Channel | Movies | 255 |
| 2407 | IndiePix Unlimited Amazon Channel | Movies | 261 |
| 408 | Investigation Discovery | TV | 106 |
| 581 | iQIYI | Movies + TV | 138 |
| 2330 | Jolt Film | Movies | 205 |
| 2285 | JustWatch TV | Movies + TV | 7 |
| 2603 | KableOne | Movies + TV | 348 |
| 191 | Kanopy | Movies + TV | 35 |
| 2414 | Kartoon Channel Amazon Channel | Movies + TV | 264 |
| 2415 | Kidstream Amazon Channel | Movies + TV | 265 |
| 2135 | Kino Film Collection | Movies | 210 |
| 1793 | Klassiki | Movies | 150 |
| 464 | Kocowa | Movies + TV | 329 |
| 2413 | Kocowa Amazon Channel | TV | 263 |
| 2621 | KQED | Movies + TV | 349 |
| 157 | Lifetime | Movies + TV | 52 |
| 284 | Lifetime Movie Club | Movies | 66 |
| 2089 | Lifetime Movie Club Amazon Channel | Movies + TV | 200 |
| 2055 | Lifetime Movie Club Apple TV channel | Movies + TV | 189 |
| 2358 | Lionsgate+ Amazon Channels | Movies + TV | 163 |
| 551 | Magellan TV | Movies + TV | 126 |
| 2417 | Magnolia Network Amazon Channel | TV | 267 |
| 2418 | Magnolia Selects Amazon Channel | Movies + TV | 268 |
| 2420 | Marquee TV Amazon Channel | Movies + TV | 270 |
| 585 | Metrograph | Movies | 139 |
| 34 | MGM Plus | Movies + TV | 49 |
| 636 | MGM Plus Roku Premium Channel | Movies + TV | 32 |
| 583 | MGM+ Amazon Channel | Movies + TV | 13 |
| 427 | Mhz Choice | Movies + TV | 82 |
| 1960 | Midnight Pulp | Movies + TV | 164 |
| 2367 | Midnight Pulp Amazon Channel | Movies + TV | 235 |
| 2533 | Mometu | Movies + TV | 334 |
| 2419 | Monsters and Nightmares Amazon Channel | Movies + TV | 269 |
| 2262 | Motorvision TV Amazon Channel | TV | 217 |
| 2565 | MovieMe | Movies | 344 |
| 562 | MovieSaints | Movies | 132 |
| 2445 | MovieSphere+ Amazon Channel | Movies + TV | 291 |
| 11 | MUBI | Movies + TV | 56 |
| 201 | MUBI Amazon Channel | Movies + TV | 85 |
| 1972 | myfilmfriend | Movies + TV | 172 |
| 2423 | MyOutdoor TV Amazon Channel | TV | 272 |
| 264 | MyOutdoorTV | TV | 63 |
| 291 | MZ Choice Amazon Channel | Movies + TV | 71 |
| 1964 | National Geographic | Movies + TV | 168 |
| 79 | NBC | Movies + TV | 48 |
| 8 | Netflix | Movies + TV | 3 |
| 175 | Netflix Kids | Movies + TV | 59 |
| 1796 | Netflix Standard with Ads | Movies + TV | 151 |
| 455 | Night Flight Plus | Movies + TV | 76 |
| 575 | OnDemandKorea | Movies + TV | 135 |
| 2424 | Outside TV Features Amzon Channel | Movies + TV | 273 |
| 1976 | Outside Watch | Movies + TV | 174 |
| 2044 | OUTtv Apple TV channel | Movies + TV | 188 |
| 1953 | Ovation TV | TV | 159 |
| 433 | OVID | Movies | 80 |
| 487 | OXYGEN | TV | 335 |
| 1853 | Paramount Plus Apple TV channel | TV | 23 |
| 2616 | Paramount Plus Essential | Movies + TV | 15 |
| 2303 | Paramount Plus Premium | Movies + TV | 14 |
| 582 | Paramount+ Amazon Channel | Movies + TV | 26 |
| 633 | Paramount+ Roku Premium Channel | Movies + TV | 62 |
| 2427 | Passionflix Amazon Channel | Movies + TV | 275 |
| 209 | PBS | Movies + TV | 41 |
| 2429 | PBS America Amazon Channel | TV | 277 |
| 2430 | PBS Documentaries Amazon Channel | Movies + TV | 278 |
| 293 | PBS Kids Amazon Channel | Movies + TV | 67 |
| 2431 | PBS Living Amazon Channel | Movies + TV | 279 |
| 294 | PBS Masterpiece Amazon Channel | Movies + TV | 70 |
| 386 | Peacock Premium | Movies + TV | 16 |
| 387 | Peacock Premium Plus | Movies + TV | 214 |
| 2553 | Peacock Premium Plus Amazon Channel | Movies + TV | 338 |
| 2383 | Philo | Movies + TV | 17 |
| 2765 | Pijama Films | Movies | 375 |
| 2428 | Pinoy Box Office Amazon Channel | Movies + TV | 276 |
| 2432 | PixL Amazon Channel | Movies | 280 |
| 2473 | Planet Earth Amazon Channel | TV | 316 |
| 538 | Plex | Movies + TV | 124 |
| 2077 | Plex Channel | Movies + TV | 127 |
| 300 | Pluto TV | Movies + TV | 72 |
| 638 | Public Domain Movies | Movies | 141 |
| 278 | Pure Flix | Movies + TV | 65 |
| 2266 | Qello Concerts by Stingray Amazon Channel | Movies | 325 |
| 344 | Rakuten Viki | Movies + TV | 96 |
| 2434 | REELZ+ Amazon Channel | TV | 282 |
| 446 | Retrocrush | Movies + TV | 78 |
| 295 | RetroCrush Amazon Channel | Movies + TV | 332 |
| 473 | Revry | Movies + TV | 118 |
| 2435 | Revry Amazon Channel | Movies + TV | 283 |
| 1875 | Runtime | Movies + TV | 155 |
| 2436 | Ryan and Friends Plus Amazon Channel | Movies + TV | 284 |
| 411 | Science Channel | TV | 107 |
| 202 | Screambox Amazon Channel | Movies + TV | 90 |
| 2069 | ScreenPix Amazon Channel  | Movies + TV | 333 |
| 2050 | ScreenPix Apple TV channel | Movies + TV | 187 |
| 2438 | Sensical Amazon Channel | Movies + TV | 285 |
| 1715 | Shahid VIP | Movies + TV | 170 |
| 688 | ShortsTV Amazon Channel | Movies | 148 |
| 600 | Shout! Factory Amazon Channel | Movies + TV | 318 |
| 439 | Shout! Factory TV | Movies + TV | 79 |
| 99 | Shudder | Movies + TV | 53 |
| 204 | Shudder Amazon Channel | Movies + TV | 83 |
| 2049 | Shudder Apple TV channel | Movies + TV | 186 |
| 1809 | Sling TV Orange | TV | 177 |
| 299 | Sling TV Orange and Blue | Movies | 78 |
| 2745 | Sony Pictures Core Amazon Channel | Movies + TV | 371 |
| 486 | Spectrum On Demand | Movies + TV | 119 |
| 43 | Starz | Movies + TV | 165 |
| 1794 | Starz Amazon Channel | Movies + TV | 88 |
| 1855 | Starz Apple TV channel | Movies + TV | 203 |
| 634 | Starz Roku Premium Channel | Movies + TV | 351 |
| 2273 | Stingray Classica Amazon Channel | Movies | 218 |
| 2274 | Stingray Djazz Amazon Channel | Movies | 219 |
| 2275 | Stingray Karaoke Amazon Channel | Movies | 220 |
| 2174 | Strand Releasing Amazon Channel | Movies | 213 |
| 309 | Sun Nxt | Movies + TV | 45 |
| 143 | Sundance Now | Movies + TV | 55 |
| 205 | Sundance Now Amazon Channel | Movies + TV | 91 |
| 2048 | Sundance Now Apple TV channel | TV | 185 |
| 1771 | Takflix | Movies | 149 |
| 2068 | Tastemade Amazon Channel  | Movies + TV | 322 |
| 2047 | Tastemade Apple TV channel | Movies + TV | 184 |
| 506 | TBS | Movies + TV | 115 |
| 361 | TCM | Movies | 97 |
| 2366 | The Coda Collection Amazon Channel | Movies | 234 |
| 83 | The CW | Movies + TV | 34 |
| 2172 | The Great Courses Amazon Channel | TV | 323 |
| 555 | The Oprah Winfrey Network | TV | 129 |
| 207 | The Roku Channel | Movies + TV | 29 |
| 2443 | The Surf Network Amazon Channel | Movies + TV | 289 |
| 2622 | Thirteen | TV | 350 |
| 412 | TLC | TV | 103 |
| 363 | TNT | Movies + TV | 99 |
| 2444 | Toku Amazon Channel | Movies + TV | 290 |
| 2030 | Toon Goggles | TV | 179 |
| 2684 | TPT | Movies + TV | 359 |
| 413 | Travel Channel | TV | 110 |
| 2078 | Troma NOW | Movies + TV | 204 |
| 507 | tru TV | Movies + TV | 121 |
| 2446 | True Royalty Amazon Channel | Movies + TV | 292 |
| 567 | True Story | Movies | 131 |
| 73 | Tubi TV | Movies + TV | 347 |
| 1860 | Univer Video | Movies + TV | 177 |
| 2066 | UP Faith & Family Amazon Channel  | Movies + TV | 321 |
| 2045 | UP Faith & Family Apple TV channel | Movies + TV | 183 |
| 322 | USA Network | Movies + TV | 93 |
| 2465 | Vemox Cine Amazon Channel | Movies | 310 |
| 422 | VH1 | TV | 112 |
| 2296 | Viaplay Amazon Channel | Movies + TV | 324 |
| 458 | Vice TV  | TV | 84 |
| 2529 | Vimeo | Movies | 104 |
| 457 | VIX  | Movies + TV | 75 |
| 1866 | ViX Premium Amazon Channel | Movies + TV | 154 |
| 2466 | Warriors and Gangsters Amazon Channel | Movies + TV | 311 |
| 2459 | Watchit.Kid Amazon Channel | TV | 304 |
| 2657 | WETA+ | Movies + TV | 352 |
| 509 | WeTV | TV | 123 |
| 2668 | Wonder Project Amazon Channel | Movies + TV | 355 |
| 546 | WOW Presents Plus | Movies + TV | 125 |
| 260 | WWE Network | Movies + TV | 64 |
| 2467 | Xive TV Documentaries Amazon Channel | Movies + TV | 312 |
| 2468 | XLTV Amazon Channel  | Movies + TV | 313 |
| 1963 | Xumo Play | Movies + TV | 167 |
| 2470 | Yipee Kids TV Amazon Channel | Movies + TV | 314 |
| 2462 | Yoga and Fitness TV Amazon channel | Movies + TV | 307 |
| 2464 | Young Hollywood Amazon Channel | Movies | 309 |
| 192 | YouTube | Movies + TV | 21 |
| 235 | YouTube Free | Movies + TV | 95 |
| 188 | YouTube Premium | Movies + TV | 33 |
| 2528 | YouTube TV | Movies + TV | 38 |
| 2667 | YOW.tv | Movies + TV | 354 |
| 2439 | ZenLIFE by Stingray Amazon Channel | Movies | 286 |

## Regenerating

TMDB adds and renames providers over time. To get a fresh list, run this
inside the running streamDeck container, which already has `TMDB_API_KEY`
(from the directory with streamDeck's `docker-compose.yml`; in the whole
homenet stack use `docker exec -i homenet-streamdeck-1 python -` instead):

```bash
docker compose exec -T app python - <<'PY'
import os, httpx
seen = {}
for kind in ("movie", "tv"):
    r = httpx.get(f"https://api.themoviedb.org/3/watch/providers/{kind}",
                  params={"api_key": os.environ["TMDB_API_KEY"],
                          "watch_region": "US"})
    for p in r.json()["results"]:
        seen[p["provider_id"]] = p["provider_name"]
for pid, name in sorted(seen.items(), key=lambda kv: kv[1].casefold()):
    print(pid, name, sep="\t")
PY
```

Change `watch_region` to look up another country (ISO 3166-1 code, e.g. `GB`).
