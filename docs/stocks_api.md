# Brazilian Stocks Market API

A comprehensive API for accessing 40+ fundamental data points from the Brazilian Stock Market, featuring an API Key system for secure access and optimal performance.

Built for the [Mansa](https://github.com/mansa-team) project and designed for integration with Retrieval-Augmented Generation (RAG) systems.

## Usage
1. Environment configuration (`.env`):
   ```env
    #
    #$ DATABASE CONFIGURATION
    #
    MYSQL_USER=user
    MYSQL_PASSWORD=password
    MYSQL_HOST=localhost
    MYSQL_DATABASE=database

    #
    #$ STOCKS API
    #
    STOCKSAPI_ENABLED=TRUE
    STOCKSAPI_HOST=localhost
    STOCKSAPI_PORT=3200
    
    STOCKSAPI_KEY.SYSTEM=TRUE
    STOCKSAPI_PRIVATE.KEY=your_api_key_here
    
    STOCKSAPI_DEFAULT.QUOTA=5000
    STOCKSAPI_QUOTA.RESETDAYS=30
   ```

## API Endpoints

### Health Check
```bash
curl http://localhost:3200/stocks/health
```
Returns service status and timestamp.

### API Key Verification
```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:3200/stocks/key
```

### Key Management
Users can generate or refresh their API Key. Each user is limited to one active key at a time. Generating a new key will automatically deactivate the previous one but maintain the current usage statistics.
```bash
curl "http://localhost:3200/stocks/key/generate?userId=1"
```
**Parameters:**
- `userId`: The unique identifier for the user.

### Historical Data
Query financial metrics across multiple years:
```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/historical?search=PETR4&fields=DY,LUCRO%20LIQUIDO&dates=2020,2024"
```
**Parameters:**
- `search`: Ticker symbol or company name
- `fields`: Comma-separated field names
- `dates`: Single year or range (e.g., `2020` or `2020,2024`)

```
DESPESAS, DIVIDENDOS, DY, LUCRO LIQUIDO, MARGEM BRUTA, MARGEM EBIT, MARGEM EBITDA, MARGEM LIQUIDA, RECEITA LIQUIDA
```

### Fundamental Data
Query current valuations and metrics by date range:
```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/fundamental?search=VALE3&fields=ROE,P/L,PRECO&dates=2024-01-01,2024-12-31"
```
**Parameters:**
- `search`: Ticker symbol or company name
- `fields`: Comma-separated field names
- `dates`: Single date or range (supports YYYY, YYYY-MM, or YYYY-MM-DD formats)

```
PRECO, VALOR DE MERCADO, LIQUIDEZ MEDIA DIARIA, P/L, P/VP, P/ATIVOS, P/EBIT, P/CAP. GIRO, P. AT CIR. LIQ., PSR, EV/EBIT, PEG Ratio, PRECO DE GRAHAM, PRECO DE BAZIN, MARG. LIQUIDA, MARGEM BRUTA, MARGEM EBIT, ROE, ROA, ROIC, VPA, LPA, DY, DY MEDIO 5 ANOS, CAGR DIVIDENDOS 5 ANOS, CAGR RECEITAS 5 ANOS, CAGR LUCROS 5 ANOS, RENT 1 DIA, RENT 5 DIAS, RENT 1 MES, RENT 6 MESES, RENT 1 ANO, RENT 5 ANOS, RENT MEDIA 5 ANOS, RENT TOTAL, PATRIMONIO / ATIVOS, PASSIVOS / ATIVOS, LIQ. CORRENTE, DIVIDA LIQUIDA / EBIT, DIV. LIQ. / PATRI., GIRO ATIVOS, NOME, TICKER, SETOR, SUBSETOR, SEGMENTO, SGR, TAG ALONG
```

## Response Format

All successful responses follow this structure:

```json
{
  "search": "PETR4",
  "fields": ["P/L", "ROE"],
  "dates": "2024",
  "type": "fundamental",
  "count": 250,
  "data": [
    {
      "TICKER": "PETR4",
      "NOME": "Petróleo Brasileiro S.A.",
      "TIME": "2024-11-15T10:30:00",
      "P/L": 7.5,
      "ROE": 0.18
    }
  ]
}
```

## License
Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.