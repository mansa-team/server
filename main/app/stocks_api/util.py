from imports import *
from fastapi import HTTPException
 
def categorizeColumns(columns: list) -> tuple:
    historicalFields = {}
    fundamentalCols = []
    
    for col in columns:
        parts = col.split(' ')
        if len(parts) >= 2 and parts[-1].isdigit():
            year = int(parts[-1])
            field = " ".join(parts[:-1])
            if field not in historicalFields:
                historicalFields[field] = []
            historicalFields[field].append(year)
        else:
            if col not in ["TICKER", "NOME", "TIME"]:
                fundamentalCols.append(col)
                
    return historicalFields, fundamentalCols

def parseYearInput(years: str) -> tuple:
    if not years:
        return None, None
    yearList = [int(y.strip()) for y in years.split(",")]
    if len(yearList) == 1:
        return yearList[0], yearList[0]
    elif len(yearList) == 2:
        return yearList[0], yearList[1]
    raise HTTPException(status_code=400, detail="Years format: YEAR or START_YEAR,END_YEAR")

def normalizeColumns(data: pd.DataFrame, order: list) -> pd.DataFrame:
    columns = list(data.columns)
    orderedColumns = [col for col in order if col in columns]
    remainingColumns = sorted([col for col in columns if col not in orderedColumns])
    newOrder = orderedColumns + remainingColumns
    return data[newOrder]