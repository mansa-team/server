# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

NextJS + React + shadcn/ui + assistant-ui + shadcn-fintech (user-confirmed 2026-10-10 for the new `frontend/` app; backend stays FastAPI in this repo, consumed over HTTP only). No `frontend/` exists yet — greenfield build against the contracts below.

## Users

Primary audience is **both** (user-confirmed): Brazilian B3 retail investors who track a wallet day-to-day, **and** advanced/analyst-type users who screen fundamentals, read 10-year series, and interrogate positions with an agent. One product, two depths: the casual job (what do I own, am I up, what pays me) and the analyst job (why, versus what, what next) share the same ledger and market data.

Other audiences: none confirmed. No multi-tenant advisor, admin-console, or public-publisher role is in scope for v1.

## Product Purpose

Mansa is a self-hosted B3 investing workstation: an accurate transaction-ledger wallet, B3 market/fundamental data with live quotes, and Orunmila — a finance-domain chat agent with wallet context, market tools, a code sandbox, and memory — behind one authenticated frontend.

Success means a user can record a trade, see correct cost basis / equity / TWR within the same session, screen a ticker's fundamentals and 10-year history, and ask Orunmila to explain or compute over their own positions — without leaving the app or doubting which number is canonical.

## Positioning

The claim a neighbor could not truthfully copy: **ledger-accurate B3 wallet + B3-native market cache + wallet-aware agent in one self-hosted stack.** Investidor10-class screeners show data but do not own the user's ledger semantics; general chat (Claude-class) reasons but has no B3 ledger, TWR, or earnings logic; quant notebooks compute but are not a daily wallet. Mansa's moat is the closed loop — every number the agent cites resolves to the same replayed ledger and cached B3 rows the dashboard shows.

## Operating Context

- **Market reality:** B3 tickers only (e.g. PETR4, VALE3); live quotes follow B3 hours 10:00–17:30 BRT, off-hours serve last close; prices in BRL; earnings carry Brazilian tax logic (Div 0% / JSCP 15% / RendTributado 15%).
- **Core workflows:** (1) wallet bookkeeping — create wallet, record entries (Compra/Venda), correct mistakes, rate holdings; (2) position review — summary, allocation, performance/TWR, progression, cashflows, dividends/monthly, earnings, rebalance; (3) market research — field discovery, historical year tables, point-in-time fundamentals, 10-year cotation series, live price; (4) agent analysis — open/rename/resume a chat session, stream tool-calling turns, download workspace files the agent produced.
- **Environment:** single pooled HTTP entry `http://localhost:8080` (nginx) in deploy; Next.js BFF repoints via one var `GATEWAY_API`. Auth is cookie-first in browsers (Secure-always `mansa_token` + double-submit `mansa_csrf`/`X-CSRF-Token`), header-bearer for API clients. Rate-limited surfaces: auth register/login 10/min, Google 5/min, Orunmila chat stream 5/min, workspace delete 30/min; `/user/*` unlimited.
- **Data provenance:** scraper ingests StatusInvest, TradingView, Investidor10 (yearly profits + 10y cotations), Oceans14 fallback, Google News RSS, BCB SELIC; serves from feather/MySQL cache with explicit TTLs and `503 Cache not initialized` when cold.

## Capabilities and Constraints

Confirmed against `docs/` + `main/controller/` (frontend must shape around these, not re-decide them):

- **Auth (`/auth`, `docs/authentication.md`):** JWT HS256 `{userId, sessionId, exp}`, 30-day sessions/tokens; token order `X-Access-Token` > `Bearer` > cookie; cookie-only login/register/Google-callback JSON (no `accessToken` in bodies); Google OAuth redirects only to localhost hosts else JSON fallback; `POST /auth/introspect` (service token `X-Service-Token`, 30/min) is the service seam. No password recovery, 2FA, or profile editing exists.
- **User (`/user`, `docs/user.md`):** `GET /user/me`, `GET /user/admin` (ADMIN-only), sessions list (limit default 20/max 100) / current / revoke-one / revoke-all (includes current); serialized session is `{sessionId, deviceType, lastActiveAt, createdAt, isActive, isCurrent, userAgent}` only.
- **Stocks API (`/stocks`, `docs/stocks_api.md`):** `GET /stocks/fields` first (dynamic names, never guessed); `/historical` (ticker-prefix search `^[A-Za-z0-9,\s]*$`, year dates, `400` on empty, 1h TTL); `/fundamental` (YYYY / YYYY-MM / YYYY-MM-DD / range semantics, cotation columns excluded, 5m); `/cotations` (search required, full 10y by default, `adjusted` selects PADRAO/AJUSTADA, 5m); `/cotations/live` (single exact ticker ≤7 chars, realtime-cotation shape, `404` unknown / `503` B3 failure, 15s); MCP `/stocks/mcp` exposes the same 5 ops; `?compact=true` / `X-MCP: true` selects the abbreviated wire form (kept for agent surfaces). Open by default (`STOCKSAPI_KEY.SYSTEM=false`); when closed, per-key quota 100 with atomic increment, `401` vs `429` distinction.
- **Wallet (`/wallet`, `docs/wallet_metrics.md` + `wallet_controller.py:34-545`):** wallets CRUD; entries record/delete; `GET /positions`, `/rebalance`, `/summary` (`applied` = Σ qty×avg, `equity` = Σ qty×live, `variation` = equity−applied, ledger-replayed, snapshot-on-read), `/allocation` (per-position equity + total, shares client-side), `PUT /ratings` + `PUT /set-rating` (single `rating` field; Xango score is the initial default, user overwrite survives refresh), `GET /earnings`, `/performance` (equity-weighted chained TWR + dividends_received net + price_return + annualized + volatility), `/progression` + `/progression-summary`, `POST /record-entry`, `GET /explain-twr`, `/cashflows`, `/dividends/monthly`. Cost basis: Compra raises basis (costs included), Venda reduces qty only (avg untouched, sell costs off-proceeds). Oversell = `422`.
- **Orunmila (`/orunmila`, `docs/orunmila.md`):** 30-turn Gemini-native tool loop (`gemini-flash-lite-latest`, temp 0.5), 7 local tools (memory search/save, code exec, file read/write/list/serve) + MCP market sessions, ForgeVM sandbox per turn with per-user `/workspace/{userId}`, SSE streaming (`ping=15`), fused memory rank (0.6 vector + 0.25 fulltext + 0.15 recency; caps 50 basic / 250 premium), compaction budget (8000 tokens / 12 episodes). Routes: health, sessions list/rename/history/delete, `POST /chat/stream`, `GET /chat/stream/{sessionId}`, workspace delete/download/list.
- **Transport/caching:** nginx caches `/stocks/*` GETs only (key splits on `X-MCP`); `/wallet/ /auth/ /user/ /orunmila/ /mcp` bypass. Endpoint caches are `cashews` over `mem://` (or `REDIS_URL`) with the TTLs above. Frontend talks to the BFF (`GATEWAY_API`), never directly to MySQL or service internals.
- **Explicitly undecided:** v1 IA (decided 2026-10-10 per user): screener lives on home (/); nav pills Início/Carteira/Chat; /screener redirects to /. Remaining undecided: offline tolerance, premium gate UI.

## Brand Commitments

- Name **Mansa**; backend services USER / STOCKS_API / ORUNMILA / SCRAPER keep their prefixes and route names — the frontend must not rename domain concepts (applied/equity/variation, TWR, XANGO score, compact wire form).
- Binding visual constraints volunteered in the brief and preserved here without expansion (expansion lives in DESIGN.md): display face **Bodoni Moda**, interface face **Geist Sans**, technical-label face **IBM Plex Mono**; palette as specified (`#072824` deep teal, `#439240` forest, `#94D251` lime, `#A1D958` soft lime, `#FFF95B` electric yellow, `#141414` near black, `#202020` noise base, `#292929` dark gray, `#F2F3EE` off-white, monochromatic fine noise texture); references the user made binding: **Investidor10** (data density), **Claude** (chat craft), **QuantPad** (quant surface), **waku.one** (rich animated parallax / particle flow / bold dark vibe — primary motion and attitude reference).
- Voice: Brazilian-investor direct, numbers-first, no invented testimonials, benchmarks, pricing, or performance claims.

## Evidence on Hand

- Real contracts: `docs/authentication.md`, `docs/user.md`, `docs/stocks_api.md`, `docs/orunmila.md`, `docs/wallet_metrics.md`, `docs/scraper_b3.md`; controllers `main/controller/authentication_controller.py`, `user_controller.py`, `stocksapi_controller.py`, `wallet_controller.py`, `orunmila_controller.py`; `config.py:23-94`; `README.md:96-110` (nginx/BFF); verified live reference `https://waku.one` (viewport capture 2026-10-10: black ground, oversized serif display with one yellow word, mono kickers, particle silhouette, terminal install bar).
- Absences future work must not fabricate: no `frontend/` code, tokens, or goldens; no user testimonials, customers, benchmarks, pricing, or licensing claims; no completed visual system to extract (DESIGN.md is a seed, not a scan).
- Data character: ticker universes number in the hundreds; historical tables are year-columns (`"FIELD YEAR"`); cotation series are 10-year daily; live quotes are single-ticker realtime; wallet ledgers start empty and grow per user.

## Product Principles

1. **Ledger truth over display convenience.** Every figure the UI or agent shows resolves to the replayed transaction ledger and cached B3 rows; no screen keeps its own math.
2. **Two depths, one app.** The same surface serves a glanceable retail job and a full analyst job; depth is progressive disclosure, never a separate product.
3. **Agent as colleague, not oracle.** Orunmila cites wallet rows and market responses, runs code in the sandbox for claims it computes, and its workspace files are downloadable evidence.
4. **B3-native by default.** Tickers, market hours, BRL, Brazilian earnings tax, and Portuguese-domain sources are first-class, not locale options.
5. **Self-hosted honesty.** Empty, loading, stale-cache (`503`), quota (`429`), and rate-limit states are designed surfaces — the system admits what it does not know.
