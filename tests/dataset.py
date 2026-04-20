import pandas as pd

df = pd.read_json('b3_stocks.json')

print(df[['TICKER', 'NOME', 'VALUE INVESTING SCORE', 'NOTICIAS']])