import numpy as np
import pandas as pd

MIN_YEARS = 10
CONSISTENCY_WEIGHT = 0.85
GROWTH_WEIGHT = 0.75
GROWTH_THRESHOLD_BASELINE = 0.10
GROWTH_K = 4
VOLATILITY_THRESHOLD = 0.16
VOLATILITY_FLOOR = 0.40
RECOVERY_THRESHOLD = 0.45
DRAWDOWN_FLOOR = 0.60


def calculateInvestingScore(
    ticker: str,
    profitsDf: pd.DataFrame,
    companyLiquidity: float,
    prefixLiquidity: float | None = None,
    selic: pd.DataFrame | None = None,
) -> dict:
    currentYear = pd.Timestamp.now().year
    years = range(currentYear - 10, currentYear)
    profits10y = profitsDf[profitsDf["YEAR"].isin(years)].sort_values("YEAR", ascending=True)

    nan_result = {
        "score": np.nan,
        "m_vol": np.nan,
        "m_dd": np.nan,
        "consistency": np.nan,
        "growth": np.nan,
    }

    if len(profits10y) < MIN_YEARS:
        return nan_result

    # Selic-adjusted growth threshold
    if selic is not None and len(selic) > 0:
        selicRate = selic.iloc[-1]["valor"]
        selicBaseline = selic.iloc[-1]["valor medio 10y"]
    else:
        selicRate = 1.0
        selicBaseline = 1.0

    growthThreshold = (
        GROWTH_THRESHOLD_BASELINE * (selicBaseline / selicRate) if selicRate > 0 else GROWTH_THRESHOLD_BASELINE
    )

    n = len(profits10y)
    x = np.arange(n).astype(float)
    profitsValues = profits10y["LUCRO LIQUIDO"].astype(float).values.flatten()

    # Growth calculation (tanh-based)
    mean = np.mean(profitsValues)
    slope = np.polyfit(x, profitsValues, 1)[0]
    rawGrowth = slope / mean
    growth = 50 * (np.tanh(GROWTH_K * (rawGrowth - growthThreshold)) + 1)

    # Volatility (mVol)
    pred = np.polyval(np.polyfit(x, profitsValues, 1), x)
    cvRmse = np.sqrt(np.mean((profitsValues - pred) ** 2)) / mean
    mVol = max(VOLATILITY_FLOOR, 1 - 2 * max(0, cvRmse - VOLATILITY_THRESHOLD))

    # Consistency
    yoy = np.diff(profitsValues) / profitsValues[:-1]
    posRatio = np.mean(yoy > 0)
    profRatio = np.mean(profitsValues > 0)
    consistency = profRatio * 60 + posRatio * 40

    # Drawdown (mDd)
    runningMax = np.maximum.accumulate(profitsValues)
    maxDd = min(1, 1 - np.min(profitsValues / np.maximum(runningMax, 1)))
    recovery = profitsValues[-1] / np.max(profitsValues)

    recoveryLow = RECOVERY_THRESHOLD * 0.55
    if recovery >= RECOVERY_THRESHOLD:
        mDd = max(DRAWDOWN_FLOOR, 1 - maxDd * 0.25)
    elif recovery >= recoveryLow:
        forgiveness = 0.6 * (recovery - recoveryLow) / (RECOVERY_THRESHOLD - recoveryLow)
        mDd = max(DRAWDOWN_FLOOR, 1 - maxDd * (1 - forgiveness))
    else:
        mDd = max(DRAWDOWN_FLOOR, 1 - maxDd * recovery / recoveryLow)
    mDd = min(1, mDd)

    base = growth * GROWTH_WEIGHT + consistency * CONSISTENCY_WEIGHT

    g_elig = 0.5 * (np.tanh((growth - 50) / 5) + 1)
    c_elig = 0.5 * (np.tanh((consistency - 80) / 3) + 1)
    base *= 1.0 + 0.20 * g_elig * c_elig
    
    score = min(100, max(0, base * mVol * mDd))

    totalLiq = prefixLiquidity if prefixLiquidity else companyLiquidity
    mLiq = max(0.5, np.sqrt(min(1, totalLiq / 10_000_000))) if totalLiq < 10_000_000 else 1

    mClass = 0.75 if not ticker.endswith("3") else 1

    mProfits = 0.5 if (profitsValues <= 0).any() else 1

    finalScore = min(100, score * mLiq * mClass * mProfits)

    return {
        "score": finalScore,
        "m_vol": mVol,
        "m_dd": mDd,
        "consistency": consistency,
        "growth": growth,
    }
