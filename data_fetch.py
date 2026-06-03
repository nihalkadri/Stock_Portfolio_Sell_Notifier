import os
import time
import requests
import yfinance as yf
import pandas as pd
from typing import Optional, Any

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

def safe_float(x: Any) -> Optional[float]:
    """Convert scalar or single-element Series to float, return None on failure."""
    try:
        # If pandas Series with one element
        if hasattr(x, "iloc") and getattr(x, "shape", None) and getattr(x, "shape")[0] == 1:
            return float(x.iloc[0])
        return float(x)
    except Exception:
        return None

def _extract_close_series_from_hist(hist: pd.DataFrame, ticker: str = None) -> Optional[pd.Series]:
    """
    Given a history DataFrame from yfinance.download or Ticker.history,
    return a single Series of Close prices (index = dates).
    Handles MultiIndex columns and single-level columns.
    """
    if hist is None or hist.empty:
        return None

    # If MultiIndex columns (e.g., ('Close','SJVN.NS') or ('Close', ticker))
    if isinstance(hist.columns, pd.MultiIndex):
        # Try to select the 'Close' level
        if 'Close' in hist.columns.get_level_values(0):
            try:
                close_df = hist.xs('Close', axis=1, level=0)
                if isinstance(close_df, pd.DataFrame):
                    if ticker and ticker in close_df.columns:
                        return close_df[ticker]
                    return close_df.iloc[:, -1]
                return close_df
            except Exception:
                pass

        # Some MultiIndex shapes have level order reversed; try level=1
        if 'Close' in hist.columns.get_level_values(1):
            try:
                close_df = hist.xs('Close', axis=1, level=1)
                if isinstance(close_df, pd.DataFrame):
                    if ticker and ticker in close_df.columns:
                        return close_df[ticker]
                    return close_df.iloc[:, -1]
                return close_df
            except Exception:
                pass

    # If single-level columns (typical Ticker.history)
    if 'Close' in hist.columns:
        return hist['Close']

    # As a last resort, try to find a column named like 'Close' anywhere
    for col in hist.columns:
        if isinstance(col, str) and col.lower() == 'close':
            return hist[col]

    # No close series found
    return None

def _try_history_download(ticker: str, period: str = "1y", interval: str = "1d"):
    """Try yf.download which sometimes returns MultiIndex frames."""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, threads=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception as e:
        print(f"⚠️ history download error for {ticker}: {e}")
    return None

def _try_ticker_history(ticker: str):
    """Try Ticker.history and Ticker.info/fast_info fallbacks."""
    try:
        t = yf.Ticker(ticker)
        hist = None
        try:
            hist = t.history(period="1y", interval="1d", actions=False)
        except Exception as e:
            print(f"⚠️ Ticker.history error for {ticker}: {e}")
            hist = None
        info = {}
        fast = {}
        try:
            info = t.info or {}
        except Exception as e:
            print(f"⚠️ ticker.info read error for {ticker}: {e}")
            info = {}
        try:
            fast = getattr(t, "fast_info", {}) or {}
        except Exception:
            fast = {}
        return hist, info, fast
    except Exception as e:
        print(f"⚠️ ticker object error for {ticker}: {e}")
        return None, {}, {}

def get_stock_data(ticker: str, retries: int = 4, backoff: float = 2.0) -> Optional[dict]:
    """
    Robustly fetch price, moving averages and basic fundamentals.
    Returns None if no reliable price found.
    """
    for attempt in range(retries + 1):
        print(f"🔎 Fetch attempt {attempt+1}/{retries+1} for {ticker}")

        # 1) Try yf.download (handles MultiIndex)
        hist = _try_history_download(ticker, period="1y", interval="1d")
        if hist is None or hist.empty:
            # fallback to Ticker.history and info
            hist, info, fast = _try_ticker_history(ticker)
        else:
            # still try to get info for fundamentals
            _, info, fast = _try_ticker_history(ticker)

        close_series = _extract_close_series_from_hist(hist, ticker=ticker)

        # Force use of last non-NaN close
        if close_series is not None:
            try:
                close_nonnull = close_series.dropna()
                if close_nonnull is not None and len(close_nonnull) > 0:
                    last_price = close_nonnull.iloc[-1]
                    prev_close = close_nonnull.iloc[-2] if len(close_nonnull) >= 2 else None

                    # moving averages from close_nonnull (aligned)
                    ma_50 = close_nonnull.rolling(window=50).mean().iloc[-1] if len(close_nonnull) >= 50 else None
                    ma_200 = close_nonnull.rolling(window=200).mean().iloc[-1] if len(close_nonnull) >= 200 else None

                    # fundamentals from info
                    pe = info.get("trailingPE") or info.get("forwardPE") or info.get("priceToEarnings") or None
                    high_52w = info.get("fiftyTwoWeekHigh") or None
                    low_52w = info.get("fiftyTwoWeekLow") or None

                    price_val = safe_float(last_price)
                    prev_val = safe_float(prev_close)
                    ma50_val = safe_float(ma_50)
                    ma200_val = safe_float(ma_200)

                    if price_val is not None:
                        return {
                            "price": round(price_val, 2),
                            "change_pct": round(((price_val - prev_val) / prev_val) * 100, 2) if prev_val else 0.0,
                            "ma_50": round(ma50_val, 2) if ma50_val else None,
                            "ma_200": round(ma200_val, 2) if ma200_val else None,
                            "pe": round(pe, 2) if pe else "N/A",
                            "high_52w": round(high_52w, 2) if high_52w else "N/A",
                            "low_52w": round(low_52w, 2) if low_52w else "N/A",
                        }
                else:
                    print(f"⏳ close series for {ticker} has no non-NaN values after dropna()")
            except Exception as e:
                print(f"⚠️ parsing close series error for {ticker}: {e}")

        # retry/backoff
        if attempt < retries:
            wait = backoff * (attempt + 1)
            print(f"⏳ No valid price yet for {ticker}. Sleeping {wait}s before retry.")
            time.sleep(wait)

    print(f"❌ No price data for {ticker} after {retries+1} attempts.")
    return None

def fetch_market_news(ticker: str, max_results: int = 3) -> str:
    if not TAVILY_API_KEY:
        return "No news API configured"
    try:
        url = "https://api.tavily.com/search"
        query = f"{ticker} stock news India market"
        resp = requests.post(url, json={"api_key": TAVILY_API_KEY, "query": query, "max_results": max_results}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        headlines = [f"• {r.get('title','')}" for r in results]
        return "\n".join(headlines) if headlines else "No recent news"
    except Exception as e:
        print(f"⚠️ News fetch error for {ticker}: {e}")
        return "Unable to fetch news"
