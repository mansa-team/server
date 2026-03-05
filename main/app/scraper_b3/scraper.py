import os

from config import engine, Config
from main.utils.util import log

import time
from datetime import datetime
import json
import math
import pandas as pd
import numpy as np

import gc
import subprocess
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

from tenacity import retry, stop_after_attempt, wait_exponential
from main.app.scraper_b3.normalize import normalize

class B3Scraper:
    def __init__(self, db: Engine):
        self.engine = db
        self.start_time = time.time()
        self.current_year = datetime.now().year
        self.scrape_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.script_directory = os.path.dirname(os.path.abspath(__file__))
        self.download_folder = os.path.join(self.script_directory, 'cache')
        self.csv_file_path = os.path.join(self.download_folder, 'statusinvest-busca-avancada.csv')

        self.csv_file_url = f'https://statusinvest.com.br/category/AdvancedSearchResultExport?search=%7B%22Sector%22%3A%22%22%2C%22SubSector%22%3A%22%22%2C%22Segment%22%3A%22%22%2C%22my_range%22%3A%22-20%3B100%22%2C%22forecast%22%3A%7B%22upsidedownside%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22estimatesnumber%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22revisedup%22%3Atrue%2C%22reviseddown%22%3Atrue%2C%22consensus%22%3A%5B%5D%7D%2C%22dy%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_l%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22peg_ratio%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_vp%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margembruta%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemliquida%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22ev_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidaebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidapatrimonioliquido%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_sr%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_capitalgiro%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativocirculante%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roe%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roic%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezcorrente%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22pl_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22passivo_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22giroativos%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22receitas_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lucros_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezmediadiaria%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22vpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22valormercado%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%7D&CategoryType=1'
        self.driver_queue = None

    def setupSelenium(self):
        options = webdriver.ChromeOptions()
        options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.8191.896 Safari/537.36')
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-images')
        options.add_argument('--blink-settings=imagesEnabled=false')

        prefs = {
            "download.default_directory": self.download_folder,
            "download.prompt_for_download": False,
        }
        options.add_experimental_option('prefs', prefs)

        driver = webdriver.Chrome(
            options=options,
            service=Service(log_output=os.devnull),
        )
        driver.implicitly_wait(3)
        return driver

    def initDriverQueue(self, numWorkers):
        self.driver_queue = Queue(maxsize=numWorkers)
        for i in range(numWorkers):
            driver = self.setupSelenium()
            self.driver_queue.put(driver)

    def getDriver(self):
        return self.driver_queue.get()

    def returnDriver(self, driver):
        try:
            driver.execute_script("window.localStorage.clear();")
            driver.execute_script("window.sessionStorage.clear();")
            driver.delete_all_cookies()
            driver.get("about:blank")
        except:
            pass
        self.driver_queue.put(driver)

    def shutdownDrivers(self):
        if self.driver_queue:
            while not self.driver_queue.empty():
                try:
                    driver = self.driver_queue.get_nowait()
                    driver.quit()
                except:
                    pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def downloadCsvFile(self, url, driver):
        if not os.path.exists(self.download_folder):
            os.makedirs(self.download_folder)
        driver.get(url)
        time.sleep(2)
        stocksData = pd.read_csv(self.csv_file_path, index_col="TICKER", sep=';', skipinitialspace=True, decimal=',', thousands='.')
        return stocksData

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getSectorsData(self, stocksData, driver):
        stockSectorsUrl = f'https://statusinvest.com.br/category/advancedsearchresultpaginated?search=%7B%22Sector%22%3A%22%22%2C%22SubSector%22%3A%22%22%2C%22Segment%22%3A%22%22%2C%22my_range%22%3A%22-20%3B100%22%2C%22forecast%22%3A%7B%22upsidedownside%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22estimatesnumber%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22revisedup%22%3Atrue%2C%22reviseddown%22%3Atrue%2C%22consensus%22%3A%5B%5D%7D%2C%22dy%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_l%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22peg_ratio%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_vp%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margembruta%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemliquida%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22ev_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidaebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidapatrimonioliquido%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_sr%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_capitalgiro%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativocirculante%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roe%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roic%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezcorrente%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22pl_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22passivo_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22giroativos%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22receitas_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lucros_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezmediadiaria%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22vpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22valormercado%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%7D&orderColumn=&isAsc=&page=0&take=611&CategoryType=1'
        driver.get(stockSectorsUrl)
        sectorsJson = json.loads(driver.find_element('xpath', '/html/body/pre').text)
        sectorsData = pd.json_normalize(sectorsJson, record_path='list', sep=',')
        sectorsData.rename(columns={'ticker': 'TICKER', 'companyname': 'NOME', 'sectorname': 'SETOR', 'subsectorname': 'SUBSETOR', 'segmentname': 'SEGMENTO'}, inplace=True)
        sectorsData.set_index('TICKER', inplace=True)
        stocksData = pd.merge(stocksData, sectorsData[['NOME', 'SETOR', 'SUBSETOR', 'SEGMENTO']], on='TICKER')
        return stocksData

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getTagAlong(self, TICKER, driver):
        driver.get(f'https://statusinvest.com.br/acoes/{TICKER}')
        tagAlong = driver.find_element('xpath', "//div[@class='top-info top-info-1 top-info-sm-2 top-info-md-3 top-info-xl-n sm d-flex justify-between']/div[@class='info']").text
        for item in ['help_outline', 'TAG ALONG', ' %', '\n']:
            tagAlong = tagAlong.replace(item, '')
        return int(tagAlong) if tagAlong != '--' else np.nan

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getHistoricalRent(self, TICKER, driver):
        driver.get(f'https://scanner.tradingview.com/symbol?symbol=BMFBOVESPA%3A{TICKER}&fields=change%2CPerf.5D%2CPerf.W%2CPerf.1M%2CPerf.6M%2CPerf.YTD%2CPerf.Y%2CPerf.5Y%2CPerf.All&no_404=true&label-product=symbols-performance')
        historicalRentJson = json.loads(driver.find_element('xpath', '/html/body/pre').text)
        histRentDataFrame = pd.json_normalize(historicalRentJson, sep=',')
        histRentDataFrame.drop(columns={'Perf.W'}, inplace=True)
        histRentDataFrame.rename(columns={'change': 'RENT 1 DIA', 'Perf.5D': 'RENT 5 DIAS', 'Perf.1M': 'RENT 1 MES', 'Perf.6M': 'RENT 6 MESES', 'Perf.YTD': 'RENT 12 MESES', 'Perf.Y': 'RENT 1 ANO', 'Perf.5Y': 'RENT 5 ANOS', 'Perf.All': 'RENT TOTAL'}, inplace=True)
        histRentDataFrame['TICKER'] = TICKER
        histRentDataFrame.set_index('TICKER', inplace=True)
        result = {}
        for col in histRentDataFrame.columns:
            result[col] = histRentDataFrame.at[TICKER, col]
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getHistoricalDividends(self, TICKER, driver):
        driver.get(f'https://statusinvest.com.br/acao/companytickerprovents?companyName=&ticker={TICKER}&chartProventsType=2')
        yieldsJson = json.loads(driver.find_element('xpath', '/html/body/pre').text)
        yieldsJson = pd.json_normalize(yieldsJson, record_path='assetEarningsYearlyModels', sep='')
        result = {}
        for row in yieldsJson.itertuples():
            result[f'DIVIDENDOS {row.rank}'] = row.value
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getHistoricalDY(self, TICKER, driver):
        driver.get(f'https://statusinvest.com.br/acoes/{TICKER}')
        script = f"""
        var callback = arguments[arguments.length - 1];
        fetch('/acao/indicatorhistoricallist', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest'
            }},
            body: 'codes%5B%5D={TICKER.lower()}&time=5&byQuarter=false&futureData=false'
        }})
        .then(response => response.json())
        .then(data => callback(data))
        .catch(error => callback(null));
        """
        histDataJson = driver.execute_async_script(script)
        tickerData = histDataJson['data'].get(TICKER.lower(), [])
        dyRanks = []
        for indicator in tickerData:
            if indicator.get('key') == 'dy':
                dyRanks = indicator.get('ranks', [])
                break
        result = {}
        if dyRanks:
            dyDf = pd.json_normalize(dyRanks)
            for row in dyDf.itertuples():
                result[f'DY {row.rank}'] = row.value
        return result

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getHistoricalRevenue(self, TICKER, driver):
        driver.get(f'https://statusinvest.com.br/acao/getrevenue?code={TICKER}&type=2&viewType=0')
        revenueJson = json.loads(driver.find_element('xpath', '/html/body/pre').text)
        revenueJson = pd.json_normalize(revenueJson, sep=',')
        result = {}
        for row in revenueJson.itertuples():
            result[f'RECEITA LIQUIDA {row.year}'] = row.receitaLiquida
            result[f'DESPESAS {row.year}'] = row.despesas
            result[f'LUCRO LIQUIDO {row.year}'] = row.lucroLiquido
            result[f'MARGEM BRUTA {row.year}'] = row.margemBruta
            result[f'MARGEM EBITDA {row.year}'] = row.margemEbitda
            result[f'MARGEM EBIT {row.year}'] = row.margemEbit
            result[f'MARGEM LIQUIDA {row.year}'] = row.margemLiquida
        return result

    def calcFundamentalistIndicators(self, TICKER, stockData):
        # EBIT
        try:
            ebit = stockData.get(f'MARGEM EBIT {self.current_year - 1}', 0) * stockData.get(f'RECEITA LIQUIDA {self.current_year - 1}', 0) / 100
            stockData['EBIT'] = ebit if ebit != 0 else np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['EBIT'] = np.nan

        # Average Dividend Yields over 5 years
        try:
            dyValues = []
            for year in range(self.current_year - 5, self.current_year):
                dyValue = stockData.get(f'DY {year}')
                if dyValue is not None:
                    dyValues.append(dyValue)
            stockData['DY MEDIO 5 ANOS'] = sum(dyValues) / len(dyValues) if dyValues else np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['DY MEDIO 5 ANOS'] = np.nan

        # Average Rentability over 5 years
        try:
            rentFiveYears = stockData.get('RENT 5 ANOS')
            stockData['RENT MEDIA 5 ANOS'] = rentFiveYears / 5 if rentFiveYears else np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['RENT MEDIA 5 ANOS'] = np.nan

        # Average Net Income over 5 years
        try:
            incomeValues = []
            for year in range(self.current_year - 5, self.current_year):
                incomeValue = stockData.get(f'LUCRO LIQUIDO {year}')
                if incomeValue is not None:
                    incomeValues.append(incomeValue)
            stockData['LUCRO LIQUIDO MEDIO 5 ANOS'] = sum(incomeValues) / len(incomeValues) if incomeValues else np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['LUCRO LIQUIDO MEDIO 5 ANOS'] = np.nan

        # CAGR Dividends over 5 years
        try:
            divStart = stockData.get(f'DIVIDENDOS {self.current_year - 6}')
            divEnd = stockData.get(f'DIVIDENDOS {self.current_year - 1}')
            if divStart and divStart != 0 and divEnd:
                stockData['CAGR DIVIDENDOS 5 ANOS'] = ((divEnd / divStart) ** (1/5) - 1) * 100
            else:
                stockData['CAGR DIVIDENDOS 5 ANOS'] = np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['CAGR DIVIDENDOS 5 ANOS'] = np.nan

        # Sustainable Growth Rate (SGR)
        try:
            roe = stockData.get('ROE')
            divYear = stockData.get(f'DIVIDENDOS {self.current_year - 1}')
            netYear = stockData.get(f'LUCRO LIQUIDO {self.current_year - 1}')
            if roe and netYear and netYear != 0 and divYear is not None:
                stockData['SGR'] = roe * (1 - divYear / netYear)
            else:
                stockData['SGR'] = np.nan
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['SGR'] = np.nan

        # Graham's Top Price
        try:
            lpa = stockData.get('LPA')
            vpa = stockData.get('VPA')
            if lpa and lpa > 0 and vpa and vpa > 0:
                stockData['PRECO DE GRAHAM'] = math.sqrt(22.5 * lpa * vpa)
            else:
                stockData['PRECO DE GRAHAM'] = np.nan
        except (KeyError, ZeroDivisionError, TypeError, ValueError):
            stockData['PRECO DE GRAHAM'] = np.nan

        # Bazin's Top Price
        try:
            mediaDividendos = 0
            for year in range(self.current_year - 5, self.current_year):
                div_val = stockData.get(f'DIVIDENDOS {year}')
                if div_val:
                    mediaDividendos += div_val
            mediaDividendos = mediaDividendos / 5
            stockData['PRECO DE BAZIN'] = mediaDividendos / 0.06
        except (KeyError, ZeroDivisionError, TypeError):
            stockData['PRECO DE BAZIN'] = np.nan

        return stockData

    def processStock(self, ticker, stocksData):
        driver = self.getDriver()
        stockData = stocksData.loc[ticker].to_dict()
        try:
            funcList = [
                ('getTagAlong', self.getTagAlong),
                ('getHistoricalRent', self.getHistoricalRent),
                ('getHistoricalDividends', self.getHistoricalDividends),
                ('getHistoricalDY', self.getHistoricalDY),
                ('getHistoricalRevenue', self.getHistoricalRevenue)
            ]
            for funcName, function in funcList:
                try:
                    if funcName == 'getTagAlong':
                        stockData['TAG ALONG'] = function(ticker, driver)
                    else:
                        result = function(ticker, driver)
                        stockData.update(result)
                except Exception as e:
                    log("scraper", f'{ticker} failed {funcName}: {e}')
            stockData = self.calcFundamentalistIndicators(ticker, stockData)
        except Exception as e:
            log("scraper", f'{ticker} general error: {e}')
        finally:
            self.returnDriver(driver)
        return ticker, stockData

    def scrapeData(self):
        self.initDriverQueue(int(Config.SCRAPER['MAX_WORKERS']))
        mainDriver = self.getDriver()
        try:
            if os.path.exists(self.download_folder):
                for root, dirs, files in os.walk(self.download_folder, topdown=False):
                    for name in files:
                        os.remove(os.path.join(self.download_folder, name))

            stocksData = self.downloadCsvFile(self.csv_file_url, mainDriver)
            stocksData = self.getSectorsData(stocksData, mainDriver)
            stocksData['TIME'] = self.scrape_date

            stocksList = stocksData.index.tolist()
            results = {}

            with ThreadPoolExecutor(max_workers=int(Config.SCRAPER['MAX_WORKERS'])) as executor:
                futureToTicker = {
                    executor.submit(self.processStock, ticker, stocksData): ticker
                    for ticker in stocksList
                }
                for future in as_completed(futureToTicker):
                    ticker = futureToTicker[future]
                    try:
                        processedTicker, stockData = future.result()
                        results[processedTicker] = stockData
                    except Exception as e:
                        log("scraper", f'{ticker} failed: {e}')

            if results:
                resultsDF = pd.DataFrame.from_dict(results, orient='index')
                resultsDF.index.name = 'TICKER'
                stocksData = stocksData.combine_first(resultsDF)

            stocksData = stocksData.round(2)
            normalizedColumns = ['TIME', 'NOME', 'TICKER', 'SETOR', 'SUBSETOR', 'SEGMENTO', 'ALTMAN Z-SCORE', 'SGR', 'LIQUIDEZ MEDIA DIARIA', 'PRECO', 'PRECO DE BAZIN', 'PRECO DE GRAHAM', 'TAG ALONG', 'RENT 12 MESES', 'RENT MEDIA 5 ANOS', 'DY', 'DY MEDIO 5 ANOS', 'P/L', 'P/VP', 'P/ATIVOS', 'MARGEM BRUTA', 'MARGEM EBIT', 'MARG. LIQUIDA', 'EBIT', 'P/EBIT', 'EV/EBIT', 'DIVIDA LIQUIDA / EBIT', 'DIV. LIQ. / PATRI.', 'PSR', 'P/CAP. GIRO', 'P. AT CIR. LIQ.', 'LIQ. CORRENTE', 'LUCRO LIQUIDO MEDIO 5 ANOS', 'ROE', 'ROA', 'ROIC', 'PATRIMONIO / ATIVOS', 'PASSIVOS / ATIVOS', 'GIRO ATIVOS', 'CAGR DIVIDENDOS 5 ANOS', 'CAGR RECEITAS 5 ANOS', 'CAGR LUCROS 5 ANOS', 'VPA', 'LPA', 'PEG Ratio', 'VALOR DE MERCADO']
            stocksData.index.name = 'TICKER'
            stocksData = stocksData.reset_index()
            stocksData = normalize(stocksData, normalizedColumns)

            if Config.SCRAPER['JSON'] == 'TRUE':
                stocksData.to_json(f'b3_stocks.json', orient='records', indent=4)

            if Config.SCRAPER['MYSQL'] == 'TRUE':
                try:
                    existingColumns = pd.read_sql("SELECT * FROM b3_stocks LIMIT 1", con=self.engine)
                    newColumns = set(stocksData.columns) - set(existingColumns.columns)
                    for col in newColumns:
                        with self.engine.connect() as conn:
                            colType = "TEXT" if stocksData[col].dtype == 'object' else "DOUBLE"
                            query = text(f"ALTER TABLE b3_stocks ADD COLUMN `{col}` {colType} NULL")
                            conn.execute(query)
                            conn.commit()
                except:
                    pass

                stocksData.to_sql('b3_stocks', con=self.engine, if_exists='append', index=False)

                with self.engine.connect() as conn:
                    cleanup_sql = """
                    SET SQL_SAFE_UPDATES = 0;
                    DROP TABLE IF EXISTS ticker_lookup;

                    CREATE TABLE ticker_lookup (
                        TICKER VARCHAR(20),
                        NOME VARCHAR(255),
                        SETOR VARCHAR(255),
                        SUBSETOR VARCHAR(255),
                        SEGMENTO VARCHAR(255),
                        PRIMARY KEY (TICKER)
                    ) AS 
                    SELECT 
                        CAST(TICKER AS CHAR(20)) AS TICKER, 
                        MAX(NOME) as NOME, 
                        MAX(SETOR) as SETOR, 
                        MAX(SUBSETOR) as SUBSETOR, 
                        MAX(SEGMENTO) as SEGMENTO
                    FROM b3_stocks 
                    WHERE NOME IS NOT NULL
                    GROUP BY TICKER;

                    UPDATE b3_stocks s
                    INNER JOIN ticker_lookup l ON s.TICKER = l.TICKER
                    SET 
                        s.NOME = COALESCE(s.NOME, l.NOME),
                        s.SETOR = COALESCE(s.SETOR, l.SETOR),
                        s.SUBSETOR = COALESCE(s.SUBSETOR, l.SUBSETOR),
                        s.SEGMENTO = COALESCE(s.SEGMENTO, l.SEGMENTO)
                    WHERE s.NOME IS NULL 
                       OR s.SETOR IS NULL 
                       OR s.SUBSETOR IS NULL 
                       OR s.SEGMENTO IS NULL;

                    SET SQL_SAFE_UPDATES = 1;
                    DROP TABLE IF EXISTS ticker_lookup;
                    """
                    for statement in cleanup_sql.split(';'):
                        if statement.strip():
                            conn.execute(text(statement))
                    conn.commit()
        finally:
            self.returnDriver(mainDriver)
            self.shutdownDrivers()
            chrome_processes = ['chromedriver.exe', 'chrome.exe']
            for process in chrome_processes:
                try:
                    subprocess.run(['taskkill', '/F', '/IM', process], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except:
                    pass
            gc.collect()

engine = create_engine(f"mysql+pymysql://{Config.MYSQL['USER']}:{Config.MYSQL['PASSWORD']}@{Config.MYSQL['HOST']}/{Config.MYSQL['DATABASE']}")
from sqlalchemy.engine import Engine
b3_scraper = B3Scraper(engine)

if __name__ == "__main__":
    b3_scraper.scrapeData()
    log("scraper", f"Execution time: {time.time() - b3_scraper.start_time:.0f} seconds")