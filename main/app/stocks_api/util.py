from imports import *
 
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