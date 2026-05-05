import logging
from config import Config

from io import StringIO
import math
import time
import warnings
from datetime import datetime
import pandas as pd
import numpy as np
import json

import cloudscraper
import re

from sqlalchemy import create_engine, text, QueuePool

from tenacity import retry, stop_after_attempt, wait_exponential
from concurrent.futures import ThreadPoolExecutor, as_completed

from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import LinearRegression

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=RuntimeWarning)

startTime = time.time()


class B3Scraper:
    def __init__(self):
        self.engine = create_engine(
            f"mysql+pymysql://{Config.MYSQL['STOCKS_USER']}:{Config.MYSQL['STOCKS_PASSWORD']}@{Config.MYSQL['STOCKS_HOST']}/{Config.MYSQL['STOCKS_DATABASE']}",
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            echo=False,
            connect_args={"charset": "utf8mb4"},
        )
        self.currentYear = datetime.now().year
        self.scraperDate = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.requests = cloudscraper.create_scraper(browser="chrome")
        adapter = cloudscraper.requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=3)
        self.requests.mount("http://", adapter)
        self.requests.mount("https://", adapter)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getInitialData(self):
        url = f"https://statusinvest.com.br/category/advancedsearchresultpaginated?search=%7B%22Sector%22%3A%22%22%2C%22SubSector%22%3A%22%22%2C%22Segment%22%3A%22%22%2C%22my_range%22%3A%22-20%3B100%22%2C%22forecast%22%3A%7B%22upsidedownside%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22estimatesnumber%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22revisedup%22%3Atrue%2C%22reviseddown%22%3Atrue%2C%22consensus%22%3A%5B%5D%7D%2C%22dy%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_l%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22peg_ratio%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_vp%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margembruta%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemliquida%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22ev_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidaebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidapatrimonioliquido%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_sr%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_capitalgiro%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativocirculante%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roe%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roic%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezcorrente%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22pl_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22passivo_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22giroativos%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22receitas_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lucros_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezmediadiaria%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22vpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22valormercado%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%7D&orderColumn=&isAsc=&page=0&take=6767&CategoryType=1"

        df = self.requests.get(url).json()
        df = pd.json_normalize(df, record_path="list", sep=",")

        try:
            df = df.drop(columns={"companyid", "segmentid", "sectorid", "subsectorid"})
        except:
            df = df.drop(columns={"companyid"})

        df = df.rename(
            columns={
                "ticker": "TICKER",
                "companyname": "NOME",
                "sectorname": "SETOR",
                "subsectorname": "SUBSETOR",
                "segmentname": "SEGMENTO",
                "price": "PRECO",
                "pL": "P/L",
                "pVp": "P/VP",
                "pEbit": "P/EBIT",
                "pAtivo": "P/ATIVO",
                "evEbit": "EV/EBIT",
                "margembruta": "MARGEM BRUTA",
                "margemebit": "MARGEM EBIT",
                "margemliquida": "MARG. LIQUIDA",
                "pSr": "PSR",
                "pCapitalgiro": "P/CAP. GIRO",
                "pAtivocirculante": "P. AT CIR. LIQ.",
                "giroativos": "GIRO ATIVOS",
                "roe": "ROE",
                "roa": "ROA",
                "roic": "ROIC",
                "dividaliquidapatrimonioliquido": "DIV. LIQ. / PATRI.",
                "dividaliquidaebit": "DIVIDA LIQUIDA / EBIT",
                "plAtivo": "PATRIMONIO / ATIVOS",
                "passivoAtivo": "PASSIVO / ATIVOS",
                "liquidezcorrente": "LIQ. CORRENTE",
                "pegRatio": "PEG Ratio",
                "receitas_cagr5": "CAGR RECEITAS 5 ANOS",
                "liquidezmediadiaria": "LIQUIDEZ MEDIA DIARIA",
                "vpa": "VPA",
                "lpa": "LPA",
                "valormercado": "VALOR DE MERCADO",
                "dy": "DY",
                "lucrosCagr5": "CAGR LUCROS 5 ANOS",
            }
        )
        df.dropna(subset=["TICKER", "PRECO", "LIQUIDEZ MEDIA DIARIA", "VALOR DE MERCADO"])
        df = df.set_index("TICKER")

        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalRentability(self, TICKER):
        url = f"https://scanner.tradingview.com/symbol?symbol=BMFBOVESPA%3A{TICKER}&fields=change%2CPerf.5D%2CPerf.W%2CPerf.1M%2CPerf.6M%2CPerf.YTD%2CPerf.Y%2CPerf.5Y%2CPerf.All&no_404=true&label-product=symbols-performance"
        df = self.requests.get(url).json()
        df = pd.json_normalize(df, sep=",")
        df = df.drop(columns={"Perf.W"})

        df["TICKER"] = TICKER
        df = df.rename(
            columns={
                "change": "RENT 1 DIA",
                "Perf.5D": "RENT 5 DIAS",
                "Perf.1M": "RENT 1 MES",
                "Perf.6M": "RENT 6 MESES",
                "Perf.YTD": "RENT 12 MESES",
                "Perf.Y": "RENT 1 ANO",
                "Perf.5Y": "RENT 5 ANOS",
                "Perf.All": "RENT TOTAL",
            }
        ).set_index("TICKER")

        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalDividends(self, TICKER):
        url = f"https://statusinvest.com.br/acao/companytickerprovents?companyName=&ticker={TICKER}&chartProventsType=2"
        df = self.requests.get(url).json()
        dfYearly = pd.json_normalize(df, record_path="assetEarningsYearlyModels", sep="")

        dfHistory = pd.json_normalize(df, record_path="assetEarningsModels", sep="")
        dfHistory = dfHistory.drop(columns={"sv", "etd", "sov", "y", "m", "d"})
        dfHistory = dfHistory.rename(
            columns={
                "ed": "DATA COM",
                "pd": "DATA PAGAMENTO",
                "et": "TIPO PROVENTO",
                "v": "VALOR AJUSTADO",
                "ov": "VALOR ORIGINAL",
                "adj": "FATOR AJUSTE",
            }
        )

        for col in ["DATA COM", "DATA PAGAMENTO"]:
            if col in dfHistory.columns:
                dfHistory[col] = dfHistory[col].str.split(" ").str[0].str.replace("/", "-")

        newDF = {
            "TICKER": TICKER,
            **{f"DIVIDENDOS {row.rank}": row.value for row in dfYearly.itertuples() if len(str(row.rank)) >= 4},
            "HISTORICO DIVIDENDOS": dfHistory.to_dict(orient="records"),
        }

        return pd.DataFrame([newDF]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalDividendYields(self, TICKER):
        url = f"https://statusinvest.com.br/acao/indicatorhistoricallist"

        payload = {"codes[]": TICKER.lower(), "time": 5, "byQuarter": "false", "futureData": "false"}

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://statusinvest.com.br/acoes/{TICKER.lower()}",
        }

        df = self.requests.post(url, headers=headers, data=payload).json()
        df = df["data"].get(TICKER.lower(), [])

        dyRanks = []
        for indicator in df:
            if indicator.get("key") == "dy":
                dyRanks = indicator.get("ranks", [])
                break

        newDF = {"TICKER": TICKER}
        if dyRanks:
            dyRanks = pd.json_normalize(dyRanks)
            newDF.update({f"DY {row.rank}": row.value for row in dyRanks.itertuples()})

        return pd.DataFrame([newDF]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalRevenue(self, TICKER):
        url = f"https://statusinvest.com.br/acao/getrevenue?code={TICKER}&type=2&viewType=0"
        df = pd.json_normalize(self.requests.get(url).json(), sep=",")

        newDF = {"TICKER": TICKER}
        for row in df.itertuples():
            newDF.update(
                {
                    f"LUCRO LIQUIDO {row.year}": row.lucroLiquido,
                    f"RECEITA LIQUIDA {row.year}": row.receitaLiquida,
                    f"DESPESAS {row.year}": row.despesas,
                    f"MARGEM BRUTA {row.year}": row.margemBruta,
                    f"MARGEM EBITDA {row.year}": row.margemEbitda,
                    f"MARGEM EBIT {row.year}": row.margemEbit,
                    f"MARGEM LIQUIDA {row.year}": row.margemLiquida,
                }
            )

        return pd.DataFrame([newDF]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalCotationProfits(self, TICKER):
        url = f"https://investidor10.com.br/api/cotacao-lucro/{TICKER}/adjusted"
        df = pd.DataFrame.from_dict(self.requests.get(url).json(), orient="index")
        df = df[df.index.str.isnumeric()]

        newDF = {
            "TICKER": TICKER,
            **{f"COTACAO {year}": float(row["quotation"]) for year, row in df.iterrows()},
            **{f"LUCRO LIQUIDO {year}": row["netProfit"] for year, row in df.iterrows()},
        }

        return pd.DataFrame([newDF]).set_index("TICKER")

    def historicalCotationProfits_Oceans14(self, TICKER):
        url = f"https://www.oceans14.com.br/rendaVariavel/acoes/respostaAjax/gHistoricoCotacaoLucro.aspx?papel={TICKER}"
        df = self.requests.get(url).json()
        df = pd.DataFrame(df[0].get("saida", []))

        newDF = {"TICKER": TICKER}
        for row in df.itertuples():
            newDF[f"COTACAO {row.ano}"] = row.cotacao
            newDF[f"LUCRO LIQUIDO {row.ano}"] = row.lucro

        return pd.DataFrame([newDF]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalCotations(self, TICKER):
        newDF = {"TICKER": TICKER}

        for state in [False, True]:
            url = f"https://investidor10.com.br/api/cotacoes/acao/chart/{TICKER}/3650/{str(state)}/real"
            cotationsList = self.requests.get(url).json().get("real", [])
            cotations = [
                {"DATA": item["created_at"].split(" ")[0].replace("/", "-"), "PRECO": item["price"]}
                for item in cotationsList
            ]

            prefix = "AJUSTADA" if state else "PADRAO"
            newDF[f"COTACAO 10Y {prefix}"] = cotations

        return pd.DataFrame([newDF]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def tagAlong(self, TICKER):
        url = f"https://statusinvest.com.br/acoes/{TICKER}"
        df = self.requests.get(url).text

        match = re.search(r'tagalong.*?[\'"]\s*:\s*[\'"]([\d,\s]+)', df, re.IGNORECASE)

        if not match:
            match = re.search(r"TAG ALONG.*?value.*?>([\d,\s]+)", df, re.IGNORECASE | re.DOTALL)

        if not match:
            tagIndex = df.find("TAG ALONG")
            if tagIndex != -1:
                match = re.search(r"([\d,\.]+)\s*%", df[tagIndex : tagIndex + 500])

        tagAlong = np.nan
        if match:
            try:
                tagAlong = int(float(match.group(1).replace(",", ".").strip()))
            except:
                pass

        return pd.DataFrame([{"TICKER": TICKER, "TAG ALONG": tagAlong}]).set_index("TICKER")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def stockNews(self, TICKER):
        df = pd.read_xml(
            StringIO(self.requests.get(f"https://news.google.com/rss/search?q={TICKER}&hl=pt-BR").text), xpath=".//item"
        )
        df = df.drop(columns={"guid", "description"})
        df["pubDate"] = pd.to_datetime(df["pubDate"])

        df = df.rename(columns={"title": "TITULO", "link": "LINK", "pubDate": "DATE", "source": "SOURCE"})

        newDF = {"TICKER": TICKER, "NOTICIAS": df.to_dict(orient="records")}

        return pd.DataFrame([newDF]).set_index("TICKER")

    def fundamentalIndicators(self, TICKER, df):
        newDF = {"TICKER": TICKER}

        try:
            mEbit = df.get("MARGEM EBIT", 0)
            receita = df.get(f"RECEITA LIQUIDA {self.currentYear - 1}", np.nan)
            if np.isnan(receita):
                receita = df.get(f"RECEITA LIQUIDA {self.currentYear - 2}", np.nan)
            newDF["EBIT"] = (mEbit * receita) / 100 if receita and not np.isnan(receita) and receita > 0 else np.nan
        except:
            newDF["EBIT"] = np.nan

        try:
            dyVals = np.array([df.get(f"DY {y}", np.nan) for y in range(self.currentYear - 5, self.currentYear)])
            newDF["DY MEDIO 5 ANOS"] = np.nanmean(dyVals)
        except:
            newDF["DY MEDIO 5 ANOS"] = np.nan

        try:
            rent5y = df.get("RENT 5 ANOS", np.nan)
            newDF["RENT MEDIA 5 ANOS"] = rent5y / 5 if not np.isnan(rent5y) and rent5y != 0 else np.nan
        except:
            newDF["RENT MEDIA 5 ANOS"] = np.nan

        try:
            incomes = np.array(
                [df.get(f"LUCRO LIQUIDO {y}", np.nan) for y in range(self.currentYear - 5, self.currentYear)]
            )
            newDF["LUCRO LIQUIDO MEDIO 5 ANOS"] = np.nanmean(incomes)
        except:
            newDF["LUCRO LIQUIDO MEDIO 5 ANOS"] = np.nan

        try:
            dStart = df.get(f"DIVIDENDOS {self.currentYear - 6}", np.nan)
            dEnd = df.get(f"DIVIDENDOS {self.currentYear - 1}", np.nan)
            if not np.isnan(dStart) and not np.isnan(dEnd) and dStart > 0 and dEnd > 0:
                newDF["CAGR DIVIDENDOS 5 ANOS"] = ((dEnd / dStart) ** 0.2 - 1) * 100
            else:
                newDF["CAGR DIVIDENDOS 5 ANOS"] = np.nan
        except:
            newDF["CAGR DIVIDENDOS 5 ANOS"] = np.nan

        try:
            pStart = df.get(f"LUCRO LIQUIDO {self.currentYear - 11}", np.nan)
            pEnd = df.get(f"LUCRO LIQUIDO {self.currentYear - 1}", np.nan)
            if not np.isnan(pStart) and not np.isnan(pEnd) and pStart > 0 and pEnd > 0:
                cagr = ((pEnd / pStart) ** 0.1 - 1) * 100
            else:
                cagr = np.nan
            newDF["CAGR LUCROS 10 ANOS"] = cagr
        except:
            newDF["CAGR LUCROS 10 ANOS"] = np.nan

        try:
            roe = df.get("ROE", np.nan)
            divY2 = df.get(f"DIVIDENDOS {self.currentYear - 2}", np.nan)
            netY2 = df.get(f"LUCRO LIQUIDO {self.currentYear - 2}", np.nan)
            if not np.isnan(roe) and not np.isnan(netY2) and not np.isnan(divY2) and netY2 != 0:
                newDF["SGR"] = roe * (1 - divY2 / netY2)
            else:
                newDF["SGR"] = np.nan
        except:
            newDF["SGR"] = np.nan

        try:
            lpa, vpa = df.get("LPA", np.nan), df.get("VPA", np.nan)
            newDF["PRECO DE GRAHAM"] = (
                np.sqrt(22.5 * lpa * vpa) if not np.isnan(lpa) and not np.isnan(vpa) and lpa > 0 and vpa > 0 else np.nan
            )
        except:
            newDF["PRECO DE GRAHAM"] = np.nan

        try:
            divs5y = np.array(
                [df.get(f"DIVIDENDOS {y}", np.nan) for y in range(self.currentYear - 5, self.currentYear)]
            )
            avgDiv = np.nanmean(divs5y)
            newDF["PRECO DE BAZIN"] = avgDiv / 0.06 if not np.isnan(avgDiv) and avgDiv > 0 else np.nan
        except:
            newDF["PRECO DE BAZIN"] = np.nan

        try:
            score = 0

            years = range(self.currentYear - 10, self.currentYear)

            row = df if isinstance(df, pd.Series) else df.iloc[0]
            profitCols = [col for col in row.keys() if str(col).startswith("LUCRO LIQUIDO") and str(col)[-1].isdigit()]

            profitDf = []
            for col in profitCols:
                try:
                    yearVal = int(col.split()[-1])
                    profitVal = row[col]
                    if not pd.isna(profitVal):
                        profitDf.append({"YEAR": yearVal, "LUCRO LIQUIDO": profitVal})
                except (ValueError, IndexError):
                    continue

            profitDf = pd.DataFrame(profitDf).sort_values("YEAR").reset_index(drop=True)
            profit10yDf = profitDf[profitDf["YEAR"].isin(years)].copy().reset_index(drop=True)

            if len(profit10yDf) >= 10:
                X = profit10yDf[["YEAR"]]
                y = profit10yDf[["LUCRO LIQUIDO"]]

                scalerX = MinMaxScaler()
                X_scaled = scalerX.fit_transform(X)

                scalerY = MinMaxScaler(feature_range=(0, 10))
                yScaled = scalerY.fit_transform(y)

                model = LinearRegression().fit(X_scaled, yScaled)

                opposingCathet = max(0, model.coef_[0][0])
                angleDeg = math.degrees(math.atan(opposingCathet))
                r2 = max(0, model.score(X_scaled, yScaled))

                profitsNumeric = profit10yDf["LUCRO LIQUIDO"].astype(float)
                yearlyGrowth = profitsNumeric.pct_change().dropna()
                positiveYearsRatio = (yearlyGrowth > 0).sum() / len(yearlyGrowth) if len(yearlyGrowth) > 0 else 0

                angleScore = (angleDeg / 90) * 100
                rawConsist = (r2 + positiveYearsRatio) / 2
                penaltySensitivity = max(0.1, 1 - (angleDeg / 110))
                score = angleScore * (rawConsist**penaltySensitivity)

                if r2 > 0.9 and positiveYearsRatio >= 0.9:
                    score = min(100, score + 5)

                if (profitDf["LUCRO LIQUIDO"] < 0).any():
                    score *= 0.5

                totalLiq = df.get("LIQUIDEZ MEDIA DIARIA", 0) or 0
                targetLiquidity = 10_000_000
                if totalLiq < targetLiquidity:
                    ratio = totalLiq / targetLiquidity
                    liquidityMultiplier = max(0.5, np.sqrt(min(1.0, ratio)))
                    score *= liquidityMultiplier

                if TICKER.endswith("4"):
                    score *= 0.75

            newDF["VALUE INVESTING SCORE"] = min(max(score, 0), 100)
        except Exception as e:
            newDF["VALUE INVESTING SCORE"] = np.nan

        return pd.DataFrame([newDF]).set_index("TICKER")

    def processTicker(self, ticker, tickerData):
        results = [tickerData]
        for task in [
            self.historicalRentability,
            self.historicalDividends,
            self.historicalDividendYields,
            self.historicalRevenue,
            self.historicalCotationProfits,
            # self.historicalCotationProfits_Oceans14,
            self.historicalCotations,
            self.tagAlong,
            self.stockNews,
        ]:
            try:
                taskDf = task(ticker)
                results.append(taskDf)
            except Exception as e:
                logger.error(f"Error ({ticker}) in {task.__name__}: {e}", exc_info=True)
                results.append(pd.DataFrame(index=pd.Index([ticker], name="TICKER")))

        combinedDF = pd.concat(results, axis=1)
        combinedDF = combinedDF.loc[:, ~combinedDF.columns.duplicated(keep="last")]
        try:
            fundamentalDF = self.fundamentalIndicators(ticker, combinedDF.iloc[0])
            fundamentalDF.index = combinedDF.index
            combinedDF = pd.concat([combinedDF, fundamentalDF], axis=1)
        except Exception as e:
            logger.error(f"Error ({ticker}) in fundamentalIndicators: {e}", exc_info=True)

        return (ticker, combinedDF)

    def scrapeStocks(self, maxWorkers=Config.SCRAPER["MAX_WORKERS"]):
        stocksDF = self.getInitialData()
        stocksDF["TIME"] = pd.to_datetime(self.scraperDate)
        stocksList = stocksDF.index.tolist()

        processedDfs = []

        with ThreadPoolExecutor(max_workers=maxWorkers) as executor:
            results = executor.map(lambda t: self.processTicker(t, stocksDF.loc[[t]]), stocksList)
            for ticker, resultDf in results:
                try:
                    processedDfs.append(resultDf)
                except Exception as e:
                    logger.error(f"Error processing {ticker}: {e}", exc_info=True)

        processedDfs = [
            df for df in processedDfs if len(df.dropna(how="all")) > 0 and len(df.dropna(how="all", axis=1)) > 0
        ]

        if processedDfs:
            combined = pd.concat(processedDfs, axis=0, ignore_index=False)

            if combined.columns.duplicated().any():
                combined = combined.loc[:, ~combined.columns.duplicated(keep="last")]

            newCols = [c for c in combined.columns if c not in stocksDF.columns]
            finalDf = pd.concat([stocksDF, combined[newCols]], axis=1, join="outer")
            finalDf = finalDf.reindex(stocksList)

            prefixLiq = finalDf.groupby(finalDf.index.str[:4])["LIQUIDEZ MEDIA DIARIA"].sum()
            for ticker in finalDf.index:
                prefix = ticker[:4]
                totalLiq = prefixLiq.get(prefix, 0)
                score = finalDf.loc[ticker, "VALUE INVESTING SCORE"]
                if pd.notna(score) and score > 0:
                    targetLiquidity = 10_000_000
                    if totalLiq < targetLiquidity:
                        ratio = totalLiq / targetLiquidity
                        liquidityMultiplier = max(0.5, np.sqrt(min(1.0, ratio)))
                        finalDf.loc[ticker, "VALUE INVESTING SCORE"] = min(max(score * liquidityMultiplier, 0), 100)
        else:
            finalDf = stocksDF.copy()

        finalDf = finalDf.round(2)
        finalDf = self.reorderColumns(finalDf)
        finalDf = self.serializeComplexTypes(finalDf)

        self.exportJson(finalDf)
        self.exportMysql(finalDf)

    def reorderColumns(self, df):
        if df.empty:
            return df
        special = ["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"]
        allCols = df.columns.tolist()
        historicalCols = sorted([c for c in allCols if re.match(r".*\d{4}$", c) and c not in special])
        metadataCols = [c for c in allCols if c not in historicalCols and c not in special]
        orderedCols = metadataCols + historicalCols + [c for c in special if c in allCols]
        return df[[c for c in orderedCols if c in df.columns]]

    def serializeComplexTypes(self, df):
        if df.empty:
            return df

        df = df.copy()
        df["TICKER"] = df.index
        df = df.reset_index(drop=True)

        specialCols = ["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"]

        def convertValue(val):
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False, default=str)
            return val

        for col in df.columns:
            if col in specialCols and df[col].dtype == "object":
                df[col] = df[col].apply(convertValue)

        return df

    def exportJson(self, df):
        if Config.SCRAPER["JSON"] and not df.empty:
            specialCols = ["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"]

            def convertValue(val, col):
                if col in specialCols and isinstance(val, (dict, list)):
                    return val
                elif isinstance(val, str):
                    try:
                        return json.loads(val)
                    except:
                        return val
                return val

            def convertRecursive(val):
                if hasattr(val, "isoformat"):
                    return val.isoformat()
                elif isinstance(val, dict):
                    return {k: convertRecursive(v) for k, v in val.items()}
                elif isinstance(val, list):
                    return [convertRecursive(item) for item in val]
                return val

            records = []
            for idx in range(len(df)):
                record = {}
                for col in df.columns:
                    val = df.iloc[idx][col]
                    val = convertValue(val, col)
                    record[col] = convertRecursive(val)

                records.append(record)

            with open(f"b3_stocks.json", "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False)

    def exportMysql(self, df):
        if not Config.SCRAPER["MYSQL"] or df.empty:
            return

        df = df.copy()
        df["TICKER"] = df.index
        df = df.reset_index(drop=True)

        with self.engine.begin() as conn:
            existingCols = pd.read_sql("SELECT * FROM b3_stocks LIMIT 1", con=conn).columns.tolist()
            newCols = [c for c in df.columns if c not in existingCols]

            if newCols:
                for col in newCols:
                    dtype = (
                        "JSON"
                        if df[col].dtype == "object"
                        and df[col]
                        .apply(lambda x: isinstance(x, (dict, list)) or (isinstance(x, str) and x.startswith("{")))
                        .any()
                        else ("TEXT" if df[col].dtype == "object" else "DOUBLE PRECISION")
                    )
                    conn.execute(text(f"ALTER TABLE b3_stocks ADD COLUMN `{col}` {dtype} NULL"))

            for col in ["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"]:
                if col in df.columns:
                    conn.execute(text(f"ALTER TABLE b3_stocks MODIFY COLUMN `{col}` LONGTEXT NULL"))

            df.to_sql("b3_stocks", con=conn, if_exists="append", index=False, method=None, chunksize=1)

            cleanupSql = """
            CREATE TEMPORARY TABLE IF NOT EXISTS tickerLookup (
                TICKER VARCHAR(20) PRIMARY KEY,
                NOME VARCHAR(255),
                SETOR VARCHAR(255),
                SUBSETOR VARCHAR(255),
                SEGMENTO VARCHAR(255)
            );

            INSERT INTO tickerLookup (TICKER, NOME, SETOR, SUBSETOR, SEGMENTO)
            SELECT TICKER, MAX(NOME), MAX(SETOR), MAX(SUBSETOR), MAX(SEGMENTO)
            FROM b3_stocks 
            WHERE NOME IS NOT NULL 
            GROUP BY TICKER
            ON DUPLICATE KEY UPDATE 
                NOME=VALUES(NOME), SETOR=VALUES(SETOR), 
                SUBSETOR=VALUES(SUBSETOR), SEGMENTO=VALUES(SEGMENTO);

            UPDATE b3_stocks s
            INNER JOIN tickerLookup l ON s.TICKER = l.TICKER
            SET 
                s.NOME = COALESCE(s.NOME, l.NOME),
                s.SETOR = COALESCE(s.SETOR, l.SETOR),
                s.SUBSETOR = COALESCE(s.SUBSETOR, l.SUBSETOR),
                s.SEGMENTO = COALESCE(s.SEGMENTO, l.SEGMENTO)
            WHERE s.NOME IS NULL 
                OR s.SETOR IS NULL 
                OR s.SUBSETOR IS NULL 
                OR s.SEGMENTO IS NULL;

            DROP TEMPORARY TABLE tickerLookup;
            """
            for statement in cleanupSql.split(";"):
                if statement.strip():
                    conn.execute(text(statement))


if __name__ == "__main__":
    scraper = B3Scraper()
    scraper.scrapeStocks()

    logger.info(f"Total Execution: {time.time() - startTime:.0f}s")