import os
import time
from datetime import datetime, timedelta
import pandas as pd
import requests
import duckdb

# 1. API Setup & Configuration
API_KEY = "DaLuonEpJvkPvHEuy65yNyQnoVCrDpTp"
TICKER = "QQQ"

# Polygon's free plan allows up to 2 years of historical data
END_DATE = datetime.now().strftime("%Y-%m-%d")
START_DATE = (datetime.now() - timedelta(days=720)).strftime("%Y-%m-%d")

# Dynamically chunk date range into ~60-day blocks (safely under Polygon's 50k bar limit)
dates = pd.date_range(start=START_DATE, end=END_DATE, freq="60D").strftime("%Y-%m-%d").tolist()
if END_DATE not in dates:
    dates.append(END_DATE)

date_ranges = [(dates[i], dates[i+1]) for i in range(len(dates) - 1)]

print(f"Fetching max 1m OHLCV data for {TICKER} from {START_DATE} to {END_DATE} ({len(date_ranges)} chunks)...")

all_bars = []

for start, end in date_ranges:
    url = f"https://api.polygon.io/v2/aggs/ticker/{TICKER}/range/1/minute/{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={API_KEY}"
    response = requests.get(url).json()
    
    if "results" in response and response["results"]:
        all_bars.extend(response["results"])
        print(f"✓ Fetched {len(response['results']):,} bars for {start} to {end}")
    else:
        print(f"⚠️ No bars returned or error for {start} to {end}: {response.get('status', 'Error')}")
    
    # Sleep 13 seconds between requests to respect Polygon free rate limit (5 calls/min)
    time.sleep(13)

# 2. Build & Format DataFrame
if all_bars:
    df = pd.DataFrame(all_bars)
    
    # Convert Polygon millisecond timestamp ('t') to UTC datetime
    df['timestamp'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    
    # Keep timestamp as a standard column so DuckDB includes it in the output table
    df = df[['timestamp', 'o', 'h', 'l', 'c', 'v']]
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    
    # Sort chronologically and drop duplicates based on the timestamp column
    df = df.sort_values('timestamp')
    df = df.drop_duplicates(subset=['timestamp'], keep='last')

    # 3. Save directly to Parquet using DuckDB
    output_dir = ""
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{TICKER.lower()}_1m_polygon_2yrs.parquet")

    duckdb.sql("SELECT * FROM df").write_parquet(output_file)

    print("\n" + "="*50)
    print(f"SUCCESS: Parquet file saved to '{output_file}'")
    print(f"Total Bar Count   : {len(df):,}")
    print(f"Earliest Timestamp: {df['timestamp'].min()}")
    print(f"Latest Timestamp  : {df['timestamp'].max()}")
    print(f"Columns           : {list(df.columns)}")
    print("="*50)
else:
    print("Error: No data was fetched. Please check your API key.")