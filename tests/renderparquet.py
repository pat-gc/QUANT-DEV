import os
import sys
import duckdb
import pandas as pd
import plotly.graph_objects as go

def extract_and_plot_first_day(filepath, output_filename="first_day_candles.png"):
    """
    Extracts the first day's worth of OHLCV data from a parquet file using DuckDB
    and renders it as a candlestick chart to a PNG image.
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found at {filepath}")
        return

    try:
        # Check raw Parquet schema to see all physical columns (including hidden index columns)
        schema_df = duckdb.execute("SELECT name, type FROM parquet_schema(?)", [filepath]).df()
        raw_cols = schema_df['name'].tolist()

        # Load dataframe with DuckDB
        df = duckdb.execute("SELECT * FROM read_parquet(?)", [filepath]).df()
    except Exception as e:
        print(f"Error reading parquet file with DuckDB: {e}")
        return

    if df.empty:
        print("Error: The Parquet file contains no data.")
        return

    # Map raw Polygon short column names (o, h, l, c, v) if present
    col_map = {'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'}
    df = df.rename(columns=col_map)

    # Search for any time/date column in df.columns or raw schema
    time_candidates = ['timestamp', 'datetime', 'date', 'time', 't', 'window_start', 'start', '__index_level_0__']
    found_col = None

    for col in df.columns:
        if str(col).lower() in time_candidates or 'time' in str(col).lower() or 'date' in str(col).lower():
            found_col = col
            break

    # If not in df.columns, check if DuckDB needs an explicit SQL query for a hidden index
    if not found_col:
        for candidate in ['__index_level_0__', 'index']:
            if candidate in raw_cols:
                try:
                    df = duckdb.execute(f'SELECT "{candidate}" AS timestamp, * FROM read_parquet(?)', [filepath]).df()
                    found_col = 'timestamp'
                    break
                except Exception:
                    pass

    if found_col:
        # Convert identified time column to DatetimeIndex
        if pd.api.types.is_numeric_dtype(df[found_col]):
            sample_val = df[found_col].iloc[0]
            unit = 'ns' if sample_val > 1e16 else ('ms' if sample_val > 1e11 else 's')
            df['timestamp'] = pd.to_datetime(df[found_col], unit=unit, utc=True)
        else:
            df['timestamp'] = pd.to_datetime(df[found_col], utc=True)
        df = df.set_index('timestamp')
    else:
        print("\n❌ Could not locate a valid timestamp column or hidden index.")
        print("Here is the raw schema of the Parquet file according to DuckDB:")
        print(schema_df.to_string(index=False))
        print("\nIf only OHLCV columns exist without a timestamp, the Parquet file was likely exported with index=False.")
        return

    # Verify required OHLC columns exist
    required_cols = ['open', 'high', 'low', 'close']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        print(f"Error: Missing OHLC columns {missing_cols}. Columns present: {list(df.columns)}")
        return

    # Sort chronology
    df = df.sort_index()

    # Get the first date in the dataset
    first_date = df.index.normalize().min()

    # Filter for the first day's data
    first_day_df = df[df.index.normalize() == first_date]

    if first_day_df.empty:
        print(f"No data found for the first day: {first_date.strftime('%Y-%m-%d')}")
        return

    # Create candlestick chart
    fig = go.Figure(data=[go.Candlestick(
        x=first_day_df.index.astype(str),
        open=first_day_df['open'],
        high=first_day_df['high'],
        low=first_day_df['low'],
        close=first_day_df['close']
    )])

    date_str = first_date.strftime("%Y-%m-%d")
    fig.update_layout(
        title=f'Candlestick Chart for {date_str}',
        xaxis_title='Time',
        yaxis_title='Price ($)',
        template='plotly_white',
        xaxis_rangeslider_visible=False
    )

    try:
        fig.write_image(output_filename)
        print(f"Saved first day candles ({date_str}) to {output_filename}")
    except Exception as e:
        print(f"Error writing PNG output: {e}\n(Make sure 'kaleido' is installed in your venv: pip install kaleido)")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_and_plot_first_day(sys.argv[1])
    else:
        print("Usage: python renderparquet.py <path_to_parquet_file>")