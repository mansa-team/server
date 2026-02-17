from imports import *
from fastapi import HTTPException

from main.app.stocks_api.util import *
from main.app.stocks_api.key import *

def queryHistorical(search: str = None, fields: str = None, dates: str = None):
    from main.app.stocks_api.cache import STOCKS_CACHE
    if STOCKS_CACHE is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    
    try:
        df = STOCKS_CACHE.copy()
        availableColumns = df.columns.tolist()
        availableColumnsSet = set(availableColumns)
        historicalFields, _ = categorizeColumns(availableColumns)
        
        if not historicalFields:
            raise HTTPException(status_code=400, detail="No historical data available in cache")
        
        fieldListAvailable = sorted(historicalFields.keys())
        fieldList = fieldListAvailable if not fields else [f.strip() for f in fields.split(",") if f.strip() in fieldListAvailable]
        
        availableYears = sorted(set(year for field in fieldList for year in historicalFields[field]))
        yearStart, yearEnd = parseYearInput(dates) if dates else (availableYears[0], availableYears[-1])

        cols = ["TICKER", "NOME"] + [f"{field} {year}" for field in fieldList for year in range(yearEnd, yearStart - 1, -1) if f"{field} {year}" in availableColumnsSet]
        
        if search:
            searchTerms = [s.strip().upper() for s in search.split(",")]
            df = df[df['TICKER'].str.upper().isin(searchTerms)]

        if 'TIME' in df.columns:
            df = df.sort_values(by='TIME', ascending=False)
        
        df = df[[c for c in cols if c in df.columns]]
        df = df.drop_duplicates(subset=['TICKER'], keep='first')

        return {
            "search": search or "all",
            "fields": sorted(fieldList),
            "dates": [yearStart, yearEnd],
            "type": "historical",
            "count": len(df),
            "data": json.loads(df.to_json(orient="records"))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cached historical error: {str(e)}")

def queryFundamental(search: str = None, fields: str = None, dates: str = None):
    from main.app.stocks_api.cache import STOCKS_CACHE
    if STOCKS_CACHE is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    
    try:
        df = STOCKS_CACHE.copy()
        availableColumns = df.columns.tolist()
        availableColumnsSet = set(availableColumns)
        _, fundamentalCols = categorizeColumns(availableColumns)
        
        fieldList = fundamentalCols if not fields else [f.strip() for f in fields.split(",") if f.strip() in fundamentalCols]
        cols = ["TICKER", "NOME", "TIME"] + [field for field in fieldList if field in availableColumnsSet]
        
        if search:
            searchTerms = [s.strip().upper() for s in search.split(",")]
            df = df[df['TICKER'].str.upper().isin(searchTerms)]
            
        if 'TIME' in df.columns:
            df['TIME_DT'] = pd.to_datetime(df['TIME'])
            
            if dates:
                try:
                    dateRange = [d.strip() for d in dates.split(",")]
                    if len(dateRange) == 2:
                        startDate = pd.to_datetime(dateRange[0])
                        endDate = pd.to_datetime(dateRange[1])
                        df = df[(df['TIME_DT'] >= startDate) & (df['TIME_DT'] <= endDate)]
                    elif len(dateRange) == 1:
                        targetDate = pd.to_datetime(dateRange[0]).date()
                        df = df[df['TIME_DT'].dt.date == targetDate]
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Data format error (YYYY-MM-DD): {str(e)}")

            df['TIME'] = df['TIME_DT'].astype(str)
            df = df.sort_values(by='TIME', ascending=False)
            df = df.drop(columns=['TIME_DT'])
            
        df = df[[c for c in cols if c in df.columns]]

        return {
            "search": search or "all",
            "fields": fieldList,
            "dates": dates,
            "type": "fundamental",
            "count": len(df),
            "data": json.loads(df.to_json(orient="records"))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cached fundamental error: {str(e)}")