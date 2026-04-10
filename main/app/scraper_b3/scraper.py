from config import Config
from main.utils.util import log

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

warnings.filterwarnings('ignore', category=RuntimeWarning)

start_time = time.time()

class B3Scraper:
    def __init__(self):
        self.engine = create_engine(
            f"mysql+pymysql://{Config.MYSQL['STOCKS_USER']}:{Config.MYSQL['STOCKS_PASSWORD']}@{Config.MYSQL['STOCKS_HOST']}/{Config.MYSQL['STOCKS_DATABASE']}",
            poolclass=QueuePool,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            echo=False,
            connect_args={'charset': 'utf8mb4'}
        )
        self.currentYear = datetime.now().year
        self.scraperDate = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        self.requests = cloudscraper.create_scraper(browser='chrome')
        adapter = cloudscraper.requests.adapters.HTTPAdapter(
            pool_connections=100, 
            pool_maxsize=100,
            max_retries=3
        )
        self.requests.mount('http://', adapter)
        self.requests.mount('https://', adapter)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def getInitialData(self):
        url = f'https://statusinvest.com.br/category/advancedsearchresultpaginated?search=%7B%22Sector%22%3A%22%22%2C%22SubSector%22%3A%22%22%2C%22Segment%22%3A%22%22%2C%22my_range%22%3A%22-20%3B100%22%2C%22forecast%22%3A%7B%22upsidedownside%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22estimatesnumber%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22revisedup%22%3Atrue%2C%22reviseddown%22%3Atrue%2C%22consensus%22%3A%5B%5D%7D%2C%22dy%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_l%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22peg_ratio%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_vp%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margembruta%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22margemliquida%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22ev_ebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidaebit%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22dividaliquidapatrimonioliquido%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_sr%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_capitalgiro%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22p_ativocirculante%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roe%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roic%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22roa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezcorrente%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22pl_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22passivo_ativo%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22giroativos%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22receitas_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lucros_cagr5%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22liquidezmediadiaria%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22vpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22lpa%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%2C%22valormercado%22%3A%7B%22Item1%22%3Anull%2C%22Item2%22%3Anull%7D%7D&orderColumn=&isAsc=&page=0&take=6767&CategoryType=1'

        df = self.requests.get(url).json()
        df = pd.json_normalize(df, record_path='list', sep=',')

        try: df = df.drop(columns={'companyid', 'segmentid', 'sectorid', 'subsectorid'})
        except: df = df.drop(columns={'companyid'})

        df = df.rename(columns={
            'ticker': 'TICKER',
            'companyname': 'NOME',
            'sectorname': 'SETOR',
            'subsectorname': 'SUBSETOR',
            'segmentname': 'SEGMENTO',
            'price': 'PRECO',
            'p_l': 'P/L',
            'p_vp': 'P/VP',
            'p_ebit': 'P/EBIT',
            'p_ativo': 'P/ATIVO',
            'ev_ebit': 'EV/EBIT',
            'margembruta': 'MARGEM BRUTA',
            'margemebit': 'MARGEM EBIT',
            'margemliquida': 'MARG. LIQUIDA',
            'p_sr': 'PSR',
            'p_capitalgiro': 'P/CAP. GIRO',
            'p_ativocirculante': 'P. AT CIR. LIQ.',
            'giroativos': 'GIRO ATIVOS',
            'roe': 'ROE',
            'roa': 'ROA',
            'roic': 'ROIC',
            'dividaliquidapatrimonioliquido': 'DIV. LIQ. / PATRI.',
            'dividaliquidaebit': 'DIVIDA LIQUIDA / EBIT',
            'pl_ativo': 'PATRIMONIO / ATIVOS',
            'passivo_ativo': 'PASSIVO / ATIVOS',
            'liquidezcorrente': 'LIQ. CORRENTE',
            'peg_ratio': 'PEG Ratio',
            'receitas_cagr5': 'CAGR RECEITAS 5 ANOS',
            'liquidezmediadiaria': 'LIQUIDEZ MEDIA DIARIA',
            'vpa': 'VPA',
            'lpa': 'LPA',
            'valormercado': 'VALOR DE MERCADO',
            'dy': 'DY',
            'lucros_cagr5': 'CAGR LUCROS 5 ANOS',
        }).set_index('TICKER')

        return df.dropna(subset=['PRECO', 'LIQUIDEZ MEDIA DIARIA', 'VALOR DE MERCADO'])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalRentability(self, TICKER):
        url = f'https://scanner.tradingview.com/symbol?symbol=BMFBOVESPA%3A{TICKER}&fields=change%2CPerf.5D%2CPerf.W%2CPerf.1M%2CPerf.6M%2CPerf.YTD%2CPerf.Y%2CPerf.5Y%2CPerf.All&no_404=true&label-product=symbols-performance'
        df = self.requests.get(url).json()
        df = pd.json_normalize(df, sep=',')
        df = df.drop(columns={'Perf.W'})

        df['TICKER'] = TICKER
        df = df.rename(columns={
            'change': 'RENT 1 DIA',
            'Perf.5D': 'RENT 5 DIAS',
            'Perf.1M': 'RENT 1 MES',
            'Perf.6M': 'RENT 6 MESES',
            'Perf.YTD': 'RENT 12 MESES',
            'Perf.Y': 'RENT 1 ANO',
            'Perf.5Y': 'RENT 5 ANOS',
            'Perf.All': 'RENT TOTAL'
        }).set_index('TICKER')

        return df

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalDividends(self, TICKER):
        url = f'https://statusinvest.com.br/acao/companytickerprovents?companyName=&ticker={TICKER}&chartProventsType=2'
        df = self.requests.get(url).json()
        dfYearly = pd.json_normalize(df, record_path='assetEarningsYearlyModels', sep='')

        dfHistory = pd.json_normalize(df, record_path='assetEarningsModels', sep='')
        dfHistory = dfHistory.drop(columns={'sv','etd','sov','y','m','d'})
        dfHistory = dfHistory.rename(columns={
            'ed': 'DATA COM',
            'pd': 'DATA PAGAMENTO',
            'et': 'TIPO PROVENTO',
            'v': 'VALOR AJUSTADO',
            'ov': 'VALOR ORIGINAL',
            'adj': 'FATOR AJUSTE'
        })

        for col in ['DATA COM', 'DATA PAGAMENTO']:
            if col in dfHistory.columns: dfHistory[col] = dfHistory[col].str.split(' ').str[0].str.replace('/', '-')

        newDF = {'TICKER': TICKER}
        for row in dfYearly.itertuples():
            if len(str(row.rank)) >= 4:
                newDF[f'DIVIDENDOS {row.rank}'] = row.value
        
        newDF['HISTORICO DIVIDENDOS'] = dfHistory.to_dict(orient='records')

        return pd.DataFrame([newDF]).set_index('TICKER')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalDividendYields(self, TICKER):
        url = f'https://statusinvest.com.br/acao/indicatorhistoricallist'

        payload = {
            'codes[]': TICKER.lower(),
            'time': 5,
            'byQuarter': 'false',
            'futureData': 'false'
        }

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'https://statusinvest.com.br/acoes/{TICKER.lower()}'
        }

        df = self.requests.post(url, headers=headers, data=payload).json()
        df = df['data'].get(TICKER.lower(), [])

        dyRanks = []
        for indicator in df:
            if indicator.get('key') == 'dy':
                dyRanks = indicator.get('ranks', [])
                break

        newDF = {'TICKER': TICKER}
        if dyRanks:
            dyRanks = pd.json_normalize(dyRanks)
            for row in dyRanks.itertuples():
                newDF[f'DY {row.rank}'] = row.value

        return pd.DataFrame([newDF]).set_index('TICKER')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalRevenue(self, TICKER):
        url = f'https://statusinvest.com.br/acao/getrevenue?code={TICKER}&type=2&viewType=0'
        df = self.requests.get(url).json()
        df = pd.json_normalize(df, sep=',')

        newDF = {'TICKER': TICKER}
        for row in df.itertuples():
            newDF[f'LUCRO LIQUIDO {row.year}'] = row.lucroLiquido
            newDF[f'RECEITA LIQUIDA {row.year}'] = row.receitaLiquida
            newDF[f'DESPESAS {row.year}'] = row.despesas
            newDF[f'MARGEM BRUTA {row.year}'] = row.margemBruta
            newDF[f'MARGEM EBITDA {row.year}'] = row.margemEbitda
            newDF[f'MARGEM EBIT {row.year}'] = row.margemEbit
            newDF[f'MARGEM LIQUIDA {row.year}'] = row.margemLiquida

        return pd.DataFrame([newDF]).set_index('TICKER')
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalCotationProfits(self, TICKER):
        url = f'https://investidor10.com.br/api/cotacao-lucro/{TICKER}/adjusted'
        df = self.requests.get(url).json()
        df = pd.DataFrame.from_dict(df, orient='index')
        df = df[df.index.str.isnumeric()]

        newDF = {'TICKER': TICKER}
        for year, row in df.iterrows():
            newDF[f'COTACAO {year}'] = float(row['quotation'])
            newDF[f'LUCRO LIQUIDO {year}'] = row['net_profit']

        return pd.DataFrame([newDF]).set_index('TICKER')

    def historicalCotationProfits_Oceans14(self, TICKER):
        url = f'https://www.oceans14.com.br/rendaVariavel/acoes/respostaAjax/gHistoricoCotacaoLucro.aspx?papel={TICKER}'
        df = self.requests.get(url).json()
        df = pd.DataFrame(df[0].get('saida', []))

        newDF = {'TICKER': TICKER}
        for row in df.itertuples():
            newDF[f'COTACAO {row.ano}'] = row.cotacao
            newDF[f'LUCRO LIQUIDO {row.ano}'] = row.lucro

        return pd.DataFrame([newDF]).set_index('TICKER')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def historicalCotations(self, TICKER):
        newDF = {'TICKER': TICKER}

        for state in [False, True]:
            url = f'https://investidor10.com.br/api/cotacoes/acao/chart/{TICKER}/3650/{str(state)}/real'
            df = self.requests.get(url).json().get('real', [])
            df = [
                {
                    "DATA": df['created_at'].split(' ')[0].replace('/', '-'), 
                    "PRECO": df['price']
                } for df in df
            ]

            prefix = "AJUSTADA" if state else "PADRAO"
            newDF[f'COTACAO 10Y {prefix}'] = df
        
        return pd.DataFrame([newDF]).set_index('TICKER')

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=3))
    def tagAlong(self, TICKER):
        url = f'https://statusinvest.com.br/acoes/{TICKER}'
        df = self.requests.get(url).text

        match = re.search(r'tagalong.*?[\'"]\s*:\s*[\'"]([\d,\s]+)', df, re.IGNORECASE)

        if not match: match = re.search(r'TAG ALONG.*?value.*?>([\d,\s]+)', df, re.IGNORECASE | re.DOTALL)
        
        if not match:
            tagIndex = df.find("TAG ALONG")
            if tagIndex != -1:
                match = re.search(r'([\d,\.]+)\s*%', df[tagIndex:tagIndex + 500])

        tagAlong = np.nan
        if match:
            try: tagAlong = int(float(match.group(1).replace(',', '.').strip()))
            except: pass

        return pd.DataFrame([{'TICKER': TICKER, 'TAG ALONG': tagAlong}]).set_index('TICKER')

    def fundamentalIndicators(self, TICKER, df):
        newDF = {'TICKER': TICKER}

        # EBIT (Earnings Before Interest and Taxes)
        # EBIT = Margem EBIT × Receita Líquida
        m_ebit = df.get('MARGEM EBIT', 0)
        receita = df.get(f'RECEITA LIQUIDA {self.currentYear - 1}', np.nan)
        if receita is None or np.isnan(receita):
            receita = df.get(f'RECEITA LIQUIDA {self.currentYear - 2}', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if receita is not None and not np.isnan(receita) and receita > 0:
                newDF['EBIT'] = (m_ebit * receita) / 100
            else:
                newDF['EBIT'] = np.nan

        # Average Dividend Yield 5 Years
        # avgDY_5y = (∑ DYᵢ) / 5
        dy_vals = [df.get(f'DY {y}', np.nan) for y in range(self.currentYear - 5, self.currentYear)]
        dy_vals = [v for v in dy_vals if v is not None and not np.isnan(v)]
        with np.errstate(invalid='ignore', divide='ignore'):
            newDF['DY MEDIO 5 ANOS'] = sum(dy_vals) / len(dy_vals) if dy_vals else np.nan

        # Average Rentability 5 Years
        # RENT_avg_5y = RENT_5y / 5
        rent5y = df.get('RENT 5 ANOS', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if not np.isnan(rent5y) and rent5y != 0:
                newDF['RENT MEDIA 5 ANOS'] = rent5y / 5
            else:
                newDF['RENT MEDIA 5 ANOS'] = np.nan

        # Average Net Income 5 Years
        # LUCRO_avg_5y = (∑ Lucro Líquidoᵢ) / 5
        incomes = [df.get(f'LUCRO LIQUIDO {y}', np.nan) for y in range(self.currentYear - 5, self.currentYear)]
        incomes = [v for v in incomes if v is not None and not np.isnan(v)]
        with np.errstate(invalid='ignore', divide='ignore'):
            newDF['LUCRO LIQUIDO MEDIO 5 ANOS'] = sum(incomes) / len(incomes) if incomes else np.nan

        # CAGR Dividends 5 Years
        # CAGR = [(Div_end / Div_start)^(1/5) - 1] × 100
        d_start = df.get(f'DIVIDENDOS {self.currentYear - 6}', np.nan)
        d_end = df.get(f'DIVIDENDOS {self.currentYear - 1}', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if not np.isnan(d_start) and not np.isnan(d_end) and d_start > 0 and d_end > 0:
                newDF['CAGR DIVIDENDOS 5 ANOS'] = ((d_end / d_start) ** (0.2) - 1) * 100
            else:
                newDF['CAGR DIVIDENDOS 5 ANOS'] = np.nan

        # CAGR Profits 10 Years
        # CAGR = [(Profit_end / Profit_start)^(1/10) - 1] × 100
        p_start = df.get(f'LUCRO LIQUIDO {self.currentYear - 11}', np.nan)
        p_end = df.get(f'LUCRO LIQUIDO {self.currentYear - 1}', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if not np.isnan(p_start) and not np.isnan(p_end) and p_start > 0 and p_end > 0:
                cagr = ((p_end / p_start) ** (0.1) - 1) * 100
            else:
                cagr = np.nan
        newDF['CAGR LUCROS 10 ANOS'] = cagr

        # Sustainable Growth Rate
        # SGR = ROE × (1 - Div / NetProfit)
        roe = df.get('ROE', np.nan)
        div_y2 = df.get(f'DIVIDENDOS {self.currentYear - 2}', np.nan)
        net_y2 = df.get(f'LUCRO LIQUIDO {self.currentYear - 2}', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if not np.isnan(roe) and not np.isnan(net_y2) and not np.isnan(div_y2) and net_y2 != 0:
                newDF['SGR'] = roe * (1 - div_y2 / net_y2)
            else:
                newDF['SGR'] = np.nan

        # Graham's Top Price
        # V_Graham = √(22.5 × LPA × VPA)
        lpa, vpa = df.get('LPA', np.nan), df.get('VPA', np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            if not np.isnan(lpa) and not np.isnan(vpa) and lpa > 0 and vpa > 0:
                newDF['PRECO DE GRAHAM'] = np.sqrt(22.5 * lpa * vpa)
            else:
                newDF['PRECO DE GRAHAM'] = np.nan

        # Bazin's Price for 6% Yield
        # P_Bazin = avgDividendo_5y / 0.06
        divs_5y = [df.get(f'DIVIDENDOS {y}', np.nan) for y in range(self.currentYear - 5, self.currentYear)]
        divs_5y = [d for d in divs_5y if d is not None and not np.isnan(d)]
        with np.errstate(invalid='ignore', divide='ignore'):
            if divs_5y:
                avg_div = sum(divs_5y) / len(divs_5y)
                newDF['PRECO DE BAZIN'] = avg_div / 0.06 if avg_div > 0 else np.nan
            else:
                newDF['PRECO DE BAZIN'] = np.nan

        # Value Investing Score (0, 10)
        try:
            recent_p5 = [df.get(f'LUCRO LIQUIDO {y}', np.nan) for y in range(self.currentYear-5, self.currentYear)]
            with np.errstate(invalid='ignore', divide='ignore'):
                recent_avg5 = np.nanmean([p for p in recent_p5 if not np.isnan(p)]) if any(not np.isnan(p) for p in recent_p5) else np.nan
                past_p5 = [df.get(f'LUCRO LIQUIDO {y}', np.nan) for y in range(self.currentYear-10, self.currentYear-5)]
                past_avg5 = np.nanmean([p for p in past_p5 if not np.isnan(p)]) if any(not np.isnan(p) for p in past_p5) else np.nan
            
            with np.errstate(invalid='ignore', divide='ignore'):
                if not np.isnan(recent_avg5) and not np.isnan(past_avg5) and past_avg5 > 0:
                    growth_recent = ((recent_avg5 / past_avg5) - 1) * 100
                else:
                    growth_recent = np.nan
            growth_recent_capped = min(growth_recent, cagr * 2.5) if not np.isnan(growth_recent) and not np.isnan(cagr) and growth_recent > 0 else (growth_recent if not np.isnan(growth_recent) else np.nan)
            
            # Composite Growth
            # $G = (CAGR × 0.8) + (G_{recent} × 0.2)$
            with np.errstate(invalid='ignore', divide='ignore'):
                if not np.isnan(cagr) and not np.isnan(growth_recent_capped):
                    growth_composite = (cagr * 0.8) + (growth_recent_capped * 0.2)
                else:
                    growth_composite = np.nan
            
            score = 0

            # Growth Score
            if not np.isnan(growth_composite):
                if growth_composite >= 15:   score += 3.0
                elif growth_composite >= 10: score += 2.25
                elif growth_composite >= 5:  score += 1.5
            
            # Growth Divergence Penalty
            with np.errstate(invalid='ignore', divide='ignore'):
                if not np.isnan(cagr) and not np.isnan(growth_recent):
                    growth_diff = cagr - growth_recent
                    if growth_diff > 30:   score -= 2.0
                    elif growth_diff > 15: score -= 0.5

            # Liquidity Score
            liq = df.get('LIQUIDEZ MEDIA DIARIA', np.nan)
            if not np.isnan(liq):
                if liq >= 100000000:  score += 2.0
                elif liq >= 40000000: score += 1.0
                elif liq >= 20000000: score += 0.5
                elif liq >= 10000000: score += 0.0
                elif liq >= 5000000:  score -= 0.5
                else:                 score -= 2.0

            # Governance & ROE
            if not str(TICKER).endswith('3'): score -= 2.0
            roe = df.get('ROE', np.nan)
            if not np.isnan(roe):
                if roe >= 20: score += 1.0
                elif roe >= 15: score += 0.75

            # Debt (Dívida Líquida/EBIT)
            div_ebit = df.get('DIVIDA LIQUIDA / EBIT', np.nan)
            if not np.isnan(div_ebit):
                if div_ebit <= 2:   score += 1.0
                elif div_ebit <= 3: score += 0.75
                elif div_ebit > 5:  score -= 2.0

            # Survival & Consistency (Losses & Staircase)
            losses = 0
            violations = 0
            prev = None
            for y in range(self.currentYear - 16, self.currentYear):
                val = df.get(f'LUCRO LIQUIDO {y}', np.nan)
                if not np.isnan(val):
                    if val < 0: losses += 1
                    with np.errstate(invalid='ignore', divide='ignore'):
                        if prev is not None and val < prev and prev != 0:
                            if (prev - val) / abs(prev) > 0.10:
                                violations += 1
                    prev = val
            
            survival = 3.0 if losses == 0 else 0
            if violations >= 4: survival -= 2.0
            elif violations >= 2: survival -= 1.0
            
            score += max(0, survival)
            newDF['VALUE INVESTING SCORE'] = min(max(score, 0), 10.0)
        except: newDF['VALUE INVESTING SCORE'] = np.nan

        return pd.DataFrame([newDF]).set_index('TICKER')

    def processTicker(self, ticker, tickerData):
        results = [tickerData]
        for task in [
            self.historicalRentability,
            self.historicalDividends,
            self.historicalDividendYields, 
            self.historicalRevenue,
            self.historicalCotationProfits,
            #self.historicalCotationProfits_Oceans14,
            self.historicalCotations,
            self.tagAlong
        ]:
            try: results.append(task(ticker))
            except Exception as e: print(f"Error ({ticker}) in {task.__name__}: {e}")
            
        combinedDF = pd.concat(results, axis=1)
        combinedDF = combinedDF.loc[:, ~combinedDF.columns.duplicated(keep='last')]
        try:
            fundamentalDF = self.fundamentalIndicators(ticker, combinedDF.iloc[0])
            fundamentalDF.index = combinedDF.index
            combinedDF = pd.concat([combinedDF, fundamentalDF], axis=1)
        except Exception as e: pass #print(f"Error ({ticker}) in fundamentalIndicators: {e}")
        return combinedDF

    def scrapeStocks(self, maxWorkers=Config.SCRAPER['MAX_WORKERS']):
        stocksDF = self.getInitialData()
        stocksDF['TIME'] = pd.to_datetime(self.scraperDate)
        stocksList = stocksDF.index.tolist()

        with ThreadPoolExecutor(max_workers=maxWorkers) as executor:
            tasks = {executor.submit(self.processTicker, t, stocksDF.loc[[t]]): t for t in stocksList}
            processed_dfs = []
            for f in as_completed(tasks):
                try:
                    res = f.result()
                    if res is not None:
                        processed_dfs.append(res)
                except Exception: pass
     
        if processed_dfs:
            final_df = pd.concat(processed_dfs, ignore_index=True).round(2)
        else:
            final_df = pd.DataFrame()

        final_df = self.reorderColumns(final_df)
        final_df = self.serializeComplexTypes(final_df)

        self.exportJson(final_df)
        self.exportMysql(final_df)

    def reorderColumns(self, df):
        if df.empty:
            return df
        special = ['COTACAO 10Y PADRAO', 'COTACAO 10Y AJUSTADA', 'HISTORICO DIVIDENDOS']
        all_cols = df.columns.tolist()
        historical_cols = sorted([c for c in all_cols if re.match(r'.*\d{4}$', c) and c not in special])
        metadata_cols = [c for c in all_cols if c not in historical_cols and c not in special]
        ordered_cols = metadata_cols + historical_cols + [c for c in special if c in all_cols]
        return df[[c for c in ordered_cols if c in df.columns]]

    def serializeComplexTypes(self, df):
        if df.empty:
            return df
        for col in df.columns:
            if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
                df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x)
        return df

    def exportJson(self, df):
        if Config.SCRAPER['JSON'] and not df.empty:
            df.to_json(f'b3_stocks.json', orient='records', indent=4)

    def exportMysql(self, df):
        if not Config.SCRAPER['MYSQL'] or df.empty:
            return
        
        with self.engine.begin() as conn:
            existing_cols = pd.read_sql("SELECT * FROM b3_stocks LIMIT 1", con=conn).columns.tolist()
            new_cols = [c for c in df.columns if c not in existing_cols]
            
            if new_cols:
                for col in new_cols:
                    dtype = "JSON" if df[col].dtype == 'object' and df[col].apply(lambda x: isinstance(x, str) and x.startswith('{')).any() else ("TEXT" if df[col].dtype == 'object' else "DOUBLE PRECISION")
                    conn.execute(text(f"ALTER TABLE b3_stocks ADD COLUMN `{col}` {dtype} NULL"))

            for col in ['COTACAO 10Y PADRAO', 'COTACAO 10Y AJUSTADA', 'HISTORICO DIVIDENDOS']:
                if col in df.columns:
                    conn.execute(text(f"ALTER TABLE b3_stocks MODIFY COLUMN `{col}` LONGTEXT NULL"))

            df.to_sql('b3_stocks', con=conn, if_exists='append', index=False, method='multi', chunksize=200)

            cleanup_sql = """
            CREATE TEMPORARY TABLE IF NOT EXISTS ticker_lookup (
                TICKER VARCHAR(20) PRIMARY KEY,
                NOME VARCHAR(255),
                SETOR VARCHAR(255),
                SUBSETOR VARCHAR(255),
                SEGMENTO VARCHAR(255)
            );

            INSERT INTO ticker_lookup (TICKER, NOME, SETOR, SUBSETOR, SEGMENTO)
            SELECT TICKER, MAX(NOME), MAX(SETOR), MAX(SUBSETOR), MAX(SEGMENTO)
            FROM b3_stocks 
            WHERE NOME IS NOT NULL 
            GROUP BY TICKER
            ON DUPLICATE KEY UPDATE 
                NOME=VALUES(NOME), SETOR=VALUES(SETOR), 
                SUBSETOR=VALUES(SUBSETOR), SEGMENTO=VALUES(SEGMENTO);

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

            DROP TEMPORARY TABLE ticker_lookup;
            """
            for statement in cleanup_sql.split(';'):
                if statement.strip():
                    conn.execute(text(statement))

if __name__ == "__main__":
    scraper = B3Scraper()
    scraper.scrapeStocks()
    print(f"\nTotal Execution: {time.time() - start_time:.0f}s")