import os
import datetime
import pandas as pd
from polygon import RESTClient
from dotenv import load_dotenv

load_dotenv()

class MarketDataProvider:
    def __init__(self):
        api_key = os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY")
        if not api_key:
            raise ValueError("[!] .env 파일에 MASSIVE_API_KEY가 설정되지 않았습니다.")
        self.client = RESTClient(api_key)

    def fetch_candlestick_data(self, ticker: str, days: int = 180) -> pd.DataFrame:
        """Massive API로부터 OHLCV 일봉 데이터를 수집하고 보조지표를 계산합니다."""
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=days)

        try:
            aggs = self.client.get_aggs(
                ticker=ticker.upper(),
                multiplier=1,
                timespan="day",
                from_=start_date.strftime("%Y-%m-%d"),
                to=end_date.strftime("%Y-%m-%d")
            )
        except Exception as e:
            print(f"[!] Massive API 호출 실패 ({ticker}): {e}")
            return pd.DataFrame()

        records = []
        for bar in aggs:
            records.append({
                "Date": pd.to_datetime(bar.timestamp, unit="ms"),
                "Open": bar.open,
                "High": bar.high,
                "Low": bar.low,
                "Close": bar.close,
                "Volume": bar.volume
            })

        df = pd.DataFrame(records)
        if df.empty:
            return df

        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)

        # 1. 기술적 보조지표 계산 (10 EMA, 20 EMA, 볼린저 밴드)
        df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
        df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
        df["SMA20"] = df["Close"].rolling(window=20).mean()
        df["STD20"] = df["Close"].rolling(window=20).std()
        df["BB_UPPER"] = df["SMA20"] + (df["STD20"] * 2)
        df["BB_LOWER"] = df["SMA20"] - (df["STD20"] * 2)

        return df