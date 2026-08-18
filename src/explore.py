import pandas as pd

df = pd.read_csv("data/MTA_Metro-North_Delays__Beginning_2012_20260817.csv")
print(df.head())
print(df.columns)

rows, columns = df.shape

print(f"Rows: {rows}, Columns: {columns}")