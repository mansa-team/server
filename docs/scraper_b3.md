# Brazilian Stocks Market Scraper

A high-performance Python scraper to collect, process, and store Brazilian stock market (B3) data from StatusInvest and TradingView. Built for research and API data for the Mansa project.

## Usage

1. Environment configuration (`.env`):
  ```env
  #
  #$ DATABASE
  #
  STOCKS_MYSQL_USER=user
  STOCKS_MYSQL_PASSWORD=password
  STOCKS_MYSQL_HOST=host
  STOCKS_MYSQL_DATABASE=database

  #
  #$ SCRAPER
  #
  SCRAPER_ENABLED=TRUE
  SCRAPER_SCHEDULER=18:30
  JSON_EXPORT=FALSE
  MYSQL_EXPORT=TRUE
  MAX_WORKERS=40
  ```

## Output Format

### MySQL Table (b3_stocks)

| Column Type | Description |
|------------|-------------|
| Metadata | TICKER, NOME, SETOR, SUBSETOR, SEGMENTO |
| Current | PRECO, DY, P/L, ROE, etc. |
| Historical | LUCRO LIQUIDO 2024, DIVIDENDOS 2023, etc. |
| Special | COTACAO 10Y PADRAO, HISTORICO DIVIDENDOS |

### Sample Record

```json
{
  "TICKER": "PETR4",
  "NOME": "Petróleo Brasileiro S.A.",
  "SETOR": "Petróleo, Gás e Biocombustíveis",
  "PRECO": 34.21,
  "DY": 8.73,
  "P/L": 7.5,
  "ROE": 0.18,
  "CAGR LUCROS 10 ANOS": 15.4,
  "INVESTING SCORE": 8.5,
  "TIME": "2024-12-09 14:30:00"
}
```

## Xangô

Mansa's own stock scoring algorithm created for the Brazilian Stock Market that focus on the fundamental approaches that Mansa seeks for evaluating stocks, it addresses the Growth-Volatility Paradox to select stocks with consise growth in profits, grading stocks based on their ability to generate consistent profits over time and grow with them, using math to achieve these goals.

### Global Score Function

$$f(P, L, c) = \min(100, \max(0, \Phi(P) \cdot \Omega(P) \cdot \Lambda(L, c) \cdot M_{profit}(P)))$$

Where:
- $P$: 10-year profit vector $\{p_1, p_2, \dots, p_{10}\}$
- $L$: Average daily liquidity (R$)
- $c$: Ticker class (3 = common shares, other = preferred/unit)

### Engines

#### Profit Quality Gate ($M_{profit}$)
Penalizes stocks with any negative annual profit:
$$M_{profit}(P) = \begin{cases} \alpha_{profit} & \text{if } \exists p_t \leq 0 \\ 1.0 & \text{otherwise} \end{cases}$$
Default: $\alpha_{profit} = 0.5$

#### Fundamental Engine ($\Phi$)
Evaluates intrinsic velocity with size-bias elimination:
$$\Phi(P) = \omega_{growth} \cdot S_{growth}(P) + (1 - \omega_{growth}) \cdot S_{cons}(P)$$

- **Relative Growth** ($S_{growth}$): OLS slope normalized by mean profit, capped at threshold:
  $$S_{growth}(P) = \min\left(100, \max\left(0, \frac{\max(\beta / \mu_p, e^{\hat{\beta}} - 1)}{T_{growth}} \cdot 100\right)\right)$$
  Default: $T_{growth} = 0.07$ (7%)

- **Consistency** ($S_{cons}$): Weighted reliability metric:
  $$S_{cons}(P) = 60 \cdot \left(\frac{1}{n} \sum \mathbf{1}_{\{p_t > 0\}}\right) + 40 \cdot \left(\frac{1}{n-1} \sum \mathbf{1}_{\{p_t > p_{t-1}\}}\right)$$

Default: $\omega_{growth} = 0.75$

#### Risk-Quality Engine ($\Omega$)
Measures "Trend Adherence" using CV-RMSE:
$$\Omega(P) = M_{vol}(P) \cdot M_{DD}(P)$$

- **Volatility Multiplier** ($M_{vol}$): Penalizes residuals from linear trend only:
  $$M_{vol}(P) = \max\left(F_{vol}, 1 - 2 \cdot \max\left(0, \frac{RMSE}{\mu_p} - T_{cv}\right)\right)$$
  Defaults: $T_{cv} = 0.16$, $F_{vol} = 0.40$

- **Drawdown** ($M_{DD}$): Recovery-aware forgiveness:
  $$M_{DD}(P) = \max\left(F_{dd}, 1 - \hat{DD}_{effective}\right)$$
  Defaults: $F_{dd} = 0.60$, $T_{recovery} = 0.45$

#### Constraint Engine ($\Lambda$)
Ensures theoretical alpha can be realized:
$$\Lambda(L, c) = M_{liq}(L) \cdot M_{class}(c)$$

- **Liquidity** ($M_{liq}$): Square-root decay for low liquidity:
  $$M_{liq}(L) = \begin{cases} 1.0 & \text{if } L \geq T_{liq} \\ \max\left(F_{liq}, \sqrt{L/T_{liq}}\right) & \text{otherwise} \end{cases}$$
  Defaults: $T_{liq} = 10,000,000$ (R$10M), $F_{liq} = 0.5$

- **Class** ($M_{class}$): Governance factor for B3 tickers:
  $$M_{class}(c) = \begin{cases} 1.0 & \text{if } c = 3 \\ \alpha_{class} & \text{otherwise} \end{cases}$$
  Default: $\alpha_{class} = 0.75$

### Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MIN_YEARS` | 10 | Minimum years of data |
| `GROWTH_WEIGHT` | 0.75 | Weight for growth vs consistency |
| `GROWTH_THRESHOLD` | 0.07 | Growth threshold (7%) |
| `VOLATILITY_THRESHOLD` | 0.16 | CV-RMSE threshold |
| `VOLATILITY_FLOOR` | 0.40 | Minimum volatility multiplier |
| `RECOVERY_THRESHOLD` | 0.45 | Recovery ratio for full forgiveness |
| `DRAWDOWN_FLOOR` | 0.60 | Minimum drawdown multiplier |
| `LIQUIDITY_THRESHOLD` | 10,000,000 | Minimum daily liquidity (R$) |
| `LIQUIDITY_FLOOR` | 0.5 | Minimum liquidity multiplier |
| `PROFIT_PENALTY` | 0.5 | Penalty for negative profit years |
| `CLASS_PENALTY` | 0.75 | Multiplier for non-common shares |

---

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
