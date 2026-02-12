import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from imports import *

APIKey_Header = APIKeyHeader(name="X-API-Key", auto_error=False)
async def verifyAPIKey(APIKey: str = Depends(APIKey_Header)):
    if Config.STOCKS_API['KEY.SYSTEM'] == 'FALSE':
        return None
    
    validKey = Config.STOCKS_API['KEY'] #and DB_APIKEYS
    if not validKey:
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if APIKey is None or APIKey != validKey:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    return APIKey
 
def categorizeColumns(columns: list) -> tuple:
    historical_fields = {}
    fundamental_cols = []
    
    for col in columns:
        parts = col.split(' ')
        if len(parts) >= 2 and parts[-1].isdigit():
            year = int(parts[-1])
            field = " ".join(parts[:-1])
            if field not in historical_fields:
                historical_fields[field] = []
            historical_fields[field].append(year)
        else:
            if col not in ["TICKER", "NOME", "TIME"]:
                fundamental_cols.append(col)
                
    return historical_fields, fundamental_cols

def parseYearInput(years: str) -> tuple:
    if not years:
        return None, None
    year_list = [int(y.strip()) for y in years.split(",")]
    if len(year_list) == 1:
        return year_list[0], year_list[0]
    elif len(year_list) == 2:
        return year_list[0], year_list[1]
    raise HTTPException(status_code=400, detail="Years format: YEAR or START_YEAR,END_YEAR")

def normalizeColumns(data: pd.DataFrame, order: list) -> pd.DataFrame:
    columns = list(data.columns)
    orderedColumns = [col for col in order if col in columns]
    remainingColumns = sorted([col for col in columns if col not in orderedColumns])
    newOrder = orderedColumns + remainingColumns
    return data[newOrder]