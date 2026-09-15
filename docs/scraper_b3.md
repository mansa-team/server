# B3 Market Scraper

Collects, enriches, and stores Brazilian stock (B3) data. Entry: `main/app/scraper_b3/scraper.py` (`B3Scraper.scrapeStocks()`); scheduling lives in `main/service/scraper_service.py` (no separate scheduler module).

## Sources (6)

| # | Source | Code | What it feeds |
|---|--------|------|---------------|
| 1 | StatusInvest advanced search + per-ticker page | `scraper.py:getInitialData`, `tagAlong` | Base universe (TICKER/NOME/SETOR/SUBSETOR/SEGMENTO/PRECO/P/L/P/VP/ROE/...) + TAG ALONG |
| 2 | TradingView scanner (`BMFBOVESPA:<TICKER>`) | `scraper.py:historicalRentability` | RENT 5 ANOS and perf windows |
| 3 | Investidor10 `cotacao-lucro/<TICKER>/adjusted` | `scraper.py:216` (`historicalCotationProfits`) | Yearly COTACAO + LUCRO LIQUIDO |
| 4 | Investidor10 `cotacoes/acao/chart/<TICKER>/3650/<bool>/real` | `scraper.py:241` (`historicalCotations`) | COTACAO 10Y PADRAO (`false`) + COTACAO 10Y AJUSTADA (`true`) |
| 5 | Oceans14 fallback (`gHistoricoCotacaoLucro.aspx?papel=`) | `scraper.py:228` (`historicalCotationProfits_Oceans14`) | Same yearly COTACAO + LUCRO LIQUIDO when Investidor10 fails |
| 6 | Google News RSS (`news.google.com/rss/search?q=<TICKER>&hl=pt-BR`) | `scraper.py:283` (`stockNews`) | NOTICIAS (TITULO/LINK/DATE/SOURCE) |
| + | BCB SGS 4189 (SELIC) | `scraper.py:32` (`getCurrentSelic`) | `valor` + `valor medio 10y` (120-month rolling mean), used to scale XANGO growth threshold |

Per-ticker fan-out is in `processTicker` (TradingView, dividends, yields, revenue, both profit sources, cotations, tag-along, news), then `fundamentalIndicators`.

## Scheduling & config (`config.py:77-81`, `scraper_service.py:23-36`)

```env
SCRAPER_ENABLED=FALSE        # default False
SCRAPER_SCHEDULER=           # default empty = no jobs; `;`-separated HH:MM list, e.g. "09:00;18:30"
JSON_EXPORT=FALSE            # default False
MYSQL_EXPORT=TRUE            # default True
MAX_WORKERS=10               # default 10 (40 is just an example override, not the default)
```

`registerScraperJobs()` splits `SCRAPER_SCHEDULER` on `;`, parses each as `HH:MM`, and registers `runScraper` with APScheduler `CronTrigger(hour, minute)` (`scraper_0`, `scraper_1`, ...). Invalid entries log a warning. `ScraperService.initialize()` calls it at boot; `runScraper()` builds `B3Scraper()` and calls `scrapeStocks()`.

## XANGO score (`main/app/scraper_b3/xango.py`)

Params (`xango.py:5-8`): `CONSISTENCY_WEIGHT=0.85`, `GROWTH_WEIGHT=0.75` (applied to growth term), `GROWTH_K=4`, `GROWTH_THRESHOLD_BASELINE=0.10`, 10y SELIC mean (`xango.py:39`).

- Growth threshold is SELIC-scaled: `growthThreshold = 0.10 * (selicBaseline / selicRate)` (`xango.py:45`).
- Growth is tanh-shaped (`xango.py:57`): `growth = 50 * (tanh(4 * (raw - T)) + 1)` where `raw = slope/mean` (OLS slope over 10y LUCRO LIQUIDO / mean).
- Base (`xango.py:85-89`): `Φ = growth * 0.75 + consistency * 0.85`, then `+20%` eligibility bonus: `base *= 1 + 0.20 * g_elig * c_elig` with `g_elig = 0.5*(tanh((growth-50)/5)+1)`, `c_elig = 0.5*(tanh((consistency-80)/3)+1)`.
- Liquidity uses prefix-sum (`scraper.py:395-396`, `xango.py:93`): `totalLiq = sum(LIQUIDEZ MEDIA DIARIA for tickers sharing first 4 letters)`; `mLiq` = sqrt decay below R$10M.
- Output (`scraper.py:410-413`): `XANGO INVESTING SCORE` + `XANGO M_VOL` / `XANGO M_DD` / `XANGO CONSISTENCY` / `XANGO GROWTH`.

## Outputs

JSON columns (`scraper.py:22`): `COTACAO 10Y PADRAO`, `COTACAO 10Y AJUSTADA`, `HISTORICO DIVIDENDOS`, `NOTICIAS`.
Derived indicators (`scraper.py:296-375`): `EBIT` (MARGEM EBIT x RECEITA), `DY MEDIO 5 ANOS`, `RENT MEDIA 5 ANOS`, `LUCRO LIQUIDO MEDIO 5 ANOS`, `CAGR DIVIDENDOS 5 ANOS`, `CAGR LUCROS 10 ANOS`, `SGR` (ROE x retention), `PRECO DE GRAHAM` (sqrt(22.5 x LPA x VPA)), `PRECO DE BAZIN` (avg 5y DIV / 0.06), plus XANGO columns above.
MySQL (`scraper.py:533-660`, table `b3_stocks`): `exportMysql` appends rows (`if_exists="append"`), `ALTER TABLE ... ADD COLUMN` for new columns (JSON vs TEXT vs DOUBLE), forces `LONGTEXT` on JSON columns, then backfills metadata (NOME/SETOR/SUBSETOR/SEGMENTO from latest non-null per ticker) and historical yearly columns (RECEITA/LUCRO/DIVIDENDOS/DY/MARGEM*/DESPESAS/COTACAO) from the previous non-null row per ticker.

Concurrency: `ThreadPoolExecutor(max_workers=Config.SCRAPER.MAX_WORKERS)` (`scraper.py:450-458`).
