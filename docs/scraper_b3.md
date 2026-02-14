# Brazilian Stocks Market Scraper

A high-performance Python scraper to collect, process, and store Brazilian stock market (B3) data from StatusInvest and TradingView. Built for research and for API data and models for the [Mansa](https://github.com/mansa-team) project.

## Usage
1. Environment configuration (`.env`):
   ```env
   #
   #$ DATABASE CONFIGURATION
   #
   MYSQL_USER=user
   MYSQL_PASSWORD=password
   MYSQL_HOST=host
   MYSQL_DATABASE=database

   #
   #$ SCRAPER CONFIGURATION
   #
   SCRAPER_ENABLED=TRUE
   # Example: 18:30;18:45;19:00
   SCRAPER_SCHEDULER=18:30

   JSON_EXPORT=TRUE
   MYSQL_EXPORT=FALSE

   MAX_WORKERS=6
   ```

## Response Format

### JSON Export (`b3_stocks.json`)
```json
{
  "TICKER": "PETR4",
  "SETOR": "Petróleo, Gás e Biocombustíveis",
  "SUBSETOR": "Petróleo",
  "SEGMENTO": "Exploração, Refino e Distribuição",
  "PRECO": 34.21,
  "DY": 8.73,
  "TAG ALONG": 100,
  "RENT_12_MESES": 28.5,
  "RENT_MEDIA_5_ANOS": 15.2,
  "DY_MEDIO_5_ANOS": 9.1,
  "PRECO_DE_GRAHAM": 45.67,
  "PRECO_DE_BAZIN": 52.34,
  "EBIT": 123456789.0,
  "SGR": 12.5,
  "DIVIDENDOS_2023": 2.34,
  "DIVIDENDOS_2022": 2.10,
  "DY_2023": 7.89,
  "DY_2022": 6.45,
  "RECEITA_LIQUIDA_2023": 987654321.0,
  "LUCRO_LIQUIDO_2023": 123456789.0,
  "TIME": "2024-12-09 14:30:00"
}
```

## License
Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.