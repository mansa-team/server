from imports import *

from main.app.stocks_api.util import *

def queryHistorical(search: str = None, fields: str = None, dates: str = None):
    from main.app.stocks_api.cache import STOCKS_CACHE
    if STOCKS_CACHE is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    
    try:
        df = STOCKS_CACHE.copy()
        available_columns = df.columns.tolist()
        available_columns_set = set(available_columns)
        historical_fields, _ = categorizeColumns(available_columns)
        
        if not historical_fields:
            raise HTTPException(status_code=400, detail="No historical data available in cache")
        
        field_list_available = sorted(historical_fields.keys())
        field_list = field_list_available if not fields else [f.strip() for f in fields.split(",") if f.strip() in field_list_available]
        
        available_years = sorted(set(year for field in field_list for year in historical_fields[field]))
        year_start, year_end = parseYearInput(dates) if dates else (available_years[0], available_years[-1])

        cols = ["TICKER", "NOME"] + [f"{field} {year}" for field in field_list for year in range(year_end, year_start - 1, -1) if f"{field} {year}" in available_columns_set]
        
        if search:
            search_terms = [s.strip().upper() for s in search.split(",")]
            df = df[df['TICKER'].str.upper().isin(search_terms)]

        if 'TIME' in df.columns:
            df = df.sort_values(by='TIME', ascending=False)
        
        df = df[[c for c in cols if c in df.columns]]
        df = df.drop_duplicates(subset=['TICKER'], keep='first')

        return {
            "search": search or "all",
            "fields": sorted(field_list),
            "dates": [year_start, year_end],
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
        available_columns = df.columns.tolist()
        available_columns_set = set(available_columns)
        _, fundamental_cols = categorizeColumns(available_columns)
        
        field_list = fundamental_cols if not fields else [f.strip() for f in fields.split(",") if f.strip() in fundamental_cols]
        cols = ["TICKER", "NOME", "TIME"] + [field for field in field_list if field in available_columns_set]
        
        if search:
            search_terms = [s.strip().upper() for s in search.split(",")]
            df = df[df['TICKER'].str.upper().isin(search_terms)]
            
        if 'TIME' in df.columns:
            df['TIME_DT'] = pd.to_datetime(df['TIME'])
            
            if dates:
                try:
                    date_range = [d.strip() for d in dates.split(",")]
                    if len(date_range) == 2:
                        start_date = pd.to_datetime(date_range[0])
                        end_date = pd.to_datetime(date_range[1])
                        df = df[(df['TIME_DT'] >= start_date) & (df['TIME_DT'] <= end_date)]
                    elif len(date_range) == 1:
                        target_date = pd.to_datetime(date_range[0]).date()
                        df = df[df['TIME_DT'].dt.date == target_date]
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Data format error (YYYY-MM-DD): {str(e)}")

            df['TIME'] = df['TIME_DT'].astype(str)
            df = df.sort_values(by='TIME', ascending=False)
            df = df.drop(columns=['TIME_DT'])
            
        df = df[[c for c in cols if c in df.columns]]

        return {
            "search": search or "all",
            "fields": field_list,
            "dates": dates,
            "type": "fundamental",
            "count": len(df),
            "data": json.loads(df.to_json(orient="records"))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cached fundamental error: {str(e)}")