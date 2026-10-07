# Wallet portfolio metrics — precise definitions

Source of truth: the **transaction ledger** (`transactions` ordered by
`date, entryId`). `SummaryManager.ledgerPositions`
(`main/app/wallet/summary.py`) replays it per ticker; `Holding` rows are a
cache and are never consulted on the summary/allocation surface (#11).

## Cost basis (buy/sell semantics)

`EntriesManager.applyEntries` (`main/app/wallet/entries.py:74-91`):

- `Compra`: `total = qty*avg + q*p + costs; qty += q; avg = total/qty`.
  Buy costs **increase** the basis (and therefore `applied`).
- `Venda`: `qty -= q` (raises 422 if oversell). The average is **unchanged**
  by sells; sell costs do **not** touch the basis.

## GET /wallet/summary

`SummaryManager.getSummary` (`main/app/wallet/summary.py`):

| Key | Definition |
| :--- | :--- |
| `applied` | Σ over open ledger positions of `quantity × avgPrice`. Capital currently committed at cost. |
| `equity` | Σ over open ledger positions of `quantity × livePrice` (tickers with no price contribute 0). Live price = 15s-cached quote with padrao-close fallback (`PositionsManager.pricePass`). |
| `variation` | `equity − applied`. Unrealized result, **excludes** dividends and realized sells. |
| `first_date` | Earliest ledger `Transaction.date` (ISO), `None` when the ledger is empty. |

Snapshot side effect (kept intentionally — reviewer #5 conflicts with the
user-approved snapshot-on-read/autosync behavior and is **not** applied):
upserts today's `Snapshot` with `applied/equity/variation`,
`profitAmount = profitTwr12mAmount = variation`, `profitTwr = profitTwr12m = NULL`,
and stamps `wallet.lastRecalc`. **Snapshot `profitTwr*` fields are currently
always NULL — the snapshot carries no TWR; windowed TWR comes only from
`/performance`.**

## GET /wallet/allocation

Per open ledger position: `{"ticker", "asset_type", "equity": qty×price or 0.0
when priceless}` + `equity_total`. Shares/grouping derive client-side.

## Ratings (single `rating` field)

Single-rating rule: `Holding.rating` is the only rating column. The Xango
score is its initial/default value — seeded at holding creation
(`EntriesManager.recalcHolding`, falling back to 10.0 when Xango is
unavailable) and backfilled by `maybeRefreshRatings` solely where `rating`
is NULL. `PUT /wallet/ratings` (0–100) overwrites `rating`, and the Xango
refresh never clobbers an existing value — user overrides survive reads.

`PUT /wallet/ratings` returns `{"ticker", "rating"}`. Rebalance `weight`
and positions `rating` read `Holding.rating` directly.

## /performance (TWR — owned by performance lane, defined here for reference)

`PerformanceManager.cachedPerformance` (`main/app/wallet/performance.py:30-160`):
per ticker/day with an open position, `dayReturn = (close−prevClose)/prevClose
+ Σ(gross/qtyAtEx)/prevClose` over earnings with `exDate == day` (gross
per-share × ledger quantity at ex-date); days aggregate equity-weighted by
prior-day equity (`qty × prevClose`); `twr = Π(1+r) − 1` chained.
`dividends_received` = Σ **net** over earnings with `from ≤ exDate ≤ to`.
`price_return` = chained price-only component. `twr_annualized =
(1+twr)^(365/spanDays) − 1` (0 when `spanDays ≤ 0). `volatility =
stdev(dailyTotal) × √252` (0 with < 2 days). Costs enter only via the ledger
quantities/averages, never as explicit TWR legs.

## /cashflows, /progression, /dividends/monthly (reference)

- `getCashflows`: per ledger row in window — `Compra → in = q×p + costs, out = 0`;
  `Venda → in = 0, out = q×p − costs`. Sell costs reduce proceeds.
- `getProgression` point: `equity = Σ qty×lastClose`;
  `invested += q×p + costs` on buys, `invested −= q×p − costs` on sells
  (sell leg uses the **execution** price, not avg — an approximation).
- `Earning`: `gross = VALOR AJUSTADO per-share × ledger qty at exDate`;
  `net = gross × (1 − IR)`, IR = Div 0 / JSCP 15% / RendTributado 15%;
  `status = Recebido` iff `payDate ≤ today` else `A Receber`; monthly groups by
  `payDate`. Unknown `TIPO PROVENTO` labels are skipped (see `TIPO_MAP`).
