import time
from datetime import datetime, timedelta
import pandas as pd
import requests
#import pyarrow as pa
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

# 2. Build & Format DataFrame (Extracting Full OHLCV)
if all_bars:
    df = pd.DataFrame(all_bars)
    
    # Convert Polygon millisecond timestamp to datetime index
    df['timestamp'] = pd.to_datetime(df['t'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Extract Open ('o'), High ('h'), Low ('l'), Close ('c'), and Volume ('v')
    df = df[['o', 'h', 'l', 'c', 'v']]
    df.columns = ['open', 'high', 'low', 'close', 'volume']
    
    # Sort chronologically and drop any accidental duplicate timestamps
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep='last')]

    # 3. Save directly to Parquet
    output_file = f"{TICKER.lower()}_1m_polygon.parquet"
    duckdb.sql("SELECT * FROM df").write_parquet(output_file)

    print("\n" + "="*50)
    print(f"SUCCESS: Parquet file saved to '{output_file}'")
    print(f"Total Bar Count : {len(df):,}")
    print(f"Earliest Timestamp: {df.index.min()}")
    print(f"Latest Timestamp  : {df.index.max()}")
    print(f"Columns           : {list(df.columns)}")
    print("="*50)
else:
    print("Error: No data was fetched. Please check your API key.")