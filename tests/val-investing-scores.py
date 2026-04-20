import pandas as pd
import numpy as np
import math
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LinearRegression
import requests

API_BASE = "http://localhost:3200/stocks"

def calculate_score(df, ticker, total_liq):
    score = 0

    current_year = datetime.now().year
    years = range(current_year - 10, current_year)

    row = df.loc[df.index[0]] if df.index[0] in df.index else df.iloc[0]
    profit_cols = [col for col in row.keys() if str(col).startswith("LUCRO LIQUIDO") and str(col)[-1].isdigit()]

    profit_df = []
    for col in profit_cols:
        try:
            year_val = int(col.split()[-1])
            lucro_val = row[col]
            if not pd.isna(lucro_val):
                profit_df.append({"YEAR": year_val, "LUCRO LIQUIDO": lucro_val})
        except (ValueError, IndexError):
            continue
    
    profit_df = pd.DataFrame(profit_df).sort_values("YEAR").reset_index(drop=True)
    profit10y_df = profit_df[profit_df['YEAR'].isin(years)].copy().reset_index(drop=True)

    if len(profit10y_df) >= 10:
        X = profit10y_df[["YEAR"]]
        y = profit10y_df[["LUCRO LIQUIDO"]]

        scaler_x = MinMaxScaler()
        X_scaled = scaler_x.fit_transform(X)
        scaler_y = MinMaxScaler(feature_range=(0, 10))
        y_scaled = scaler_y.fit_transform(y)
        model = LinearRegression().fit(X_scaled, y_scaled)

        opposing_cathet = max(0, model.coef_[0][0])
        angle_deg = math.degrees(math.atan(opposing_cathet))
        r2 = max(0, model.score(X_scaled, y_scaled))
        profits_numeric = profit10y_df["LUCRO LIQUIDO"].astype(float)
        yearly_growth = profits_numeric.pct_change().dropna()
        positive_years_ratio = (yearly_growth > 0).sum() / len(yearly_growth) if len(yearly_growth) > 0 else 0

        angle_score = (angle_deg / 90) * 100
        raw_consist = (r2 + positive_years_ratio) / 2
        penalty_sensitivity = max(0.1, 1 - (angle_deg / 110))
        score = angle_score * (raw_consist**penalty_sensitivity)

        if r2 > 0.9 and positive_years_ratio >= 0.9:
            score = min(100, score + 5)

        if (profit_df["LUCRO LIQUIDO"] < 0).any():
            score *= 0.5

        target_liquidity = 10_000_000
        if total_liq < target_liquidity:
            ratio = total_liq / target_liquidity
            liquidity_multiplier = max(0.5, np.sqrt(min(1.0, ratio)))
            score *= liquidity_multiplier

        if ticker.endswith("4"):
            score *= 0.75

    return min(max(score, 0), 100)

def eval(TICKER):
    historical = requests.get(f"{API_BASE}/historical?search={TICKER}").json().get("data", [])
    if not historical: return None
    
    fundamental = requests.get(f"{API_BASE}/fundamental?search={TICKER[:4]}&dates=2026-04-16").json().get("data", [])
    if not fundamental: return None
    
    total_liq = sum(i.get("LIQUIDEZ MEDIA DIARIA", 0) or 0 for i in fundamental)

    df_fund = pd.DataFrame([i for i in fundamental if i.get("TICKER") == TICKER])
    if df_fund.empty: return None

    df_fund = df_fund.drop(columns=["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS"], errors="ignore")
    if "TIME" in df_fund.columns: df_fund = df_fund.loc[df_fund.groupby("TICKER")["TIME"].idxmax()]

    df_hist = pd.DataFrame(historical)
    df = pd.merge(df_hist, df_fund, on="TICKER")

    score = calculate_score(df.iloc[[0]], TICKER, total_liq)

    return {"TICKER": TICKER, "SCORE": score}

if __name__ == "__main__":
    tickers = [
        "WEGE3", "RADL3", "EGIE3", "ITUB4", "LREN3", "BBAS3", "VALE3", 
        "EQTL3", "RENT3", "FLRY3", "LEVE3", "B3SA3", "PSSA3", "TOTS3",

        "BBSE3", "TAEE11", "FRAS3", "SAPR11", "BRAP4", "CPFE3", "CSUD3", 
        "SLCE3", "ODPV3", "PNVL3",

        "CMIG4", "MDIA3", "CXSE3", "GRND3", "PRIO3", "SMTO3", "UGPA3",

        "SBSP3", "ABCB4", "TIMS3", "VIVT3", "SANB11", "CSMG3", "YDUQ3", 
        "VBBR3", "HYPE3", "VIVA3", "GOAU4", "RANI3", "SUZB3", "BRFS3", "INTB3",

        "TUPY3", "EMBR3", "ALUP11", "MGLU3", "AURE3", "KEPL3", "CSAN3", 
        "UNIP6", "TRPL4", "BPAC11", "CSNA3", "KLBN11", "DXCO3", "CYRE3", 
        "DIRR3", "ENGI11", "BRKM5", "MYPK3",

        "OIBR3", "TASA4", "PETZ3", "CASH3", "RAIZ4", "LIGT3", "GOLL4", 
        "AZUL4", "USIM5", "JALL3", "NGRD3", "AERI3", "BHIA3", "HBSA3"
    ]
    tickers = list(dict.fromkeys(tickers))
    results = []
    for ticker in tickers:
        result = eval(ticker)
        if result:
            results.append(result)

    results.sort(key=lambda x: x["SCORE"], reverse=True)
    for r in results:
        print(f"{r['TICKER']}: {r['SCORE']:.2f}")