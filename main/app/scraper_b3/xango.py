import pandas as pd
import numpy as np
import requests
from datetime import datetime

MIN_YEARS = 10

CONSISTENCY_WEIGHT = 0.55 #consistency_w + growth_w > 1 but ok, used just for normalization
GROWTH_WEIGHT = 0.75
GROWTH_THRESHOLD = 0.10

VOLATILITY_THRESHOLD = 0.16
VOLATILITY_FLOOR = 0.40

RECOVERY_THRESHOLD = 0.45
DRAWDOWN_FLOOR = 0.60

TICKERS = [
    "WEGE3", "RADL3", "EGIE3", "ITUB3", "LREN3", "BBAS3", "VALE3", "EQTL3", "RENT3",
    "FLRY3", "LEVE3", "B3SA3", "PSSA3", "TOTS3", "BBSE3", "TAEE11", "FRAS3",
    "SAPR3", "BRAP4", "CPFE3", "CSUD3", "SLCE3", "ODPV3", "PNVL3", "CMIG3",
    "MDIA3", "CXSE3", "GRND3", "PRIO3", "SMTO3", "UGPA3", "SBSP3", "ABCB4",
    "TIMS3", "VIVT3", "SANB11", "CSMG3", "YDUQ3", "VBBR3", "HYPE3", "VIVA3",
    "GOAU4", "RANI3", "SUZB3", "BRFS3", "INTB3", "TUPY3", "EMBR3", "ALUP11",
    "MGLU3", "AURE3", "KEPL3", "CSAN3", "UNIP6", "TRPL4", "BPAC11", "CSNA3",
    "KLBN11", "DXCO3", "CYRE3", "DIRR3", "ENGI11", "BRKM5", "MYPK3", "OIBR3",
    "TASA4", "PETZ3", "CASH3", "RAIZ4", "LIGT3", "GOLL4", "AZUL4", "USIM5",
    "JALL3", "NGRD3", "AERI3", "BHIA3", "HBSA3"
]
TICKERS_SEARCH  = [t[:4] for t in TICKERS]
TICKERS_SEARCH = ", ".join(TICKERS_SEARCH)

fund = pd.DataFrame(requests.get(f"http://localhost:3200/stocks/fundamental?search={TICKERS_SEARCH}&fields=LIQUIDEZ MEDIA DIARIA&dates=2026-04-16").json()["data"])
hist = pd.DataFrame(requests.get(f"http://localhost:3200/stocks/historical?search={TICKERS_SEARCH}&fields=LUCRO LIQUIDO").json()["data"])
df = pd.merge(fund, hist).drop(columns={"LUCRO LIQUIDO 999"})

total_liq = df.groupby("NOME")["LIQUIDEZ MEDIA DIARIA"].sum()

years = range(datetime.now().year - 10, datetime.now().year)

results = []
for idx, row in df[df["TICKER"].isin(TICKERS)].iterrows():
    profits = row[row.index.str.startswith("LUCRO LIQUIDO")].dropna()
    profits = profits.to_frame("value").rename_axis("year").reset_index()
    profits = profits.assign(year=lambda x: x["year"].str.extract(r"(\d+)")[0].astype(int))

    profits_10y = profits[profits["year"].isin(years)].sort_values("year", ascending=True)

    score = growth = consistency = m_vol = m_dd = m_liq = m_class = n = np.nan
    if len(profits_10y) >= MIN_YEARS:
        n = len(profits_10y)
        x = np.arange(n).astype(float)
        profits_10y = profits_10y["value"].astype(float).values.flatten()
        
        mean = np.mean(profits_10y)
        slope = np.polyfit(x, profits_10y, 1)[0]
        log_slope = np.polyfit(x, np.log(np.maximum(profits_10y, 0) + 1), 1)[0]
        growth = min(100, max(0, max(slope / mean, np.exp(log_slope) - 1) / GROWTH_THRESHOLD * 100))

        pred = np.polyval(np.polyfit(x, profits_10y, 1), x)
        cv_rmse = np.sqrt(np.mean((profits_10y - pred) ** 2)) / mean
        m_vol = max(VOLATILITY_FLOOR, 1 - 2 * max(0, cv_rmse - VOLATILITY_THRESHOLD))
        
        yoy = np.diff(profits_10y) / profits_10y[:-1]
        pos_ratio = np.mean(yoy > 0)
        prof_ratio = np.mean(profits_10y > 0)
        consistency = prof_ratio * 60 + pos_ratio * 40

        running_max = np.maximum.accumulate(profits_10y)
        max_dd = min(1, 1 - np.min(profits_10y / np.maximum(running_max, 1)))
        recovery = profits_10y[-1] / np.max(profits_10y)

        recovery_low = RECOVERY_THRESHOLD * 0.55
        if recovery >= RECOVERY_THRESHOLD:
            m_dd = max(DRAWDOWN_FLOOR, 1 - max_dd * 0.25)
        elif recovery >= recovery_low:
            forgiveness = 0.6 * (recovery - recovery_low) / (RECOVERY_THRESHOLD - recovery_low)
            m_dd = max(DRAWDOWN_FLOOR, 1 - max_dd * (1 - forgiveness))
        else:
            m_dd = max(DRAWDOWN_FLOOR, 1 - max_dd * recovery / recovery_low)
        m_dd = min(1, m_dd)

        base = growth * GROWTH_WEIGHT + consistency * CONSISTENCY_WEIGHT
        score = min(100, max(0, base * m_vol * m_dd))
        
        m_liq = max(0.5, np.sqrt(min(1, total_liq.loc[row["NOME"]] / 10_000_000))) if total_liq.loc[row["NOME"]] < 10_000_000 else 1

        m_class = 0.75 if not row["TICKER"].endswith("3") else 1

        m_profits = 0.5 if (profits_10y <= 0).any() else 1

        score = min(100, score * m_liq * m_class * m_profits)

    try:
        results.append({
            "ticker": row["TICKER"],
            "score": score,
            "growth": growth,
            "consistency": consistency,
            "m_vol": m_vol,
            "m_dd": m_dd,
            "m_liq": m_liq,
            "m_class": m_class,
            "n_years": n
        })
    except:
        print(f"{row["TICKER"]}: failed")

print(pd.DataFrame(results).sort_values('score', ascending=False).to_string())