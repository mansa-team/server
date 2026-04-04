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
  "VALUE INVESTING SCORE": 8.5,
  "TIME": "2024-12-09 14:30:00"
}
```

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
