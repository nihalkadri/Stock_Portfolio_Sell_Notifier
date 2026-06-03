from dotenv import load_dotenv
from pathlib import Path
import os
import sys
import time as tm
from datetime import datetime, date, time
from typing import Dict
import json

# Load .env from repo root
load_dotenv(dotenv_path=Path('.') / '.env')

from data_fetch import get_stock_data, fetch_market_news, TAVILY_API_KEY
from ai_client import analyze_with_groq, parse_ai_decision
from telegram_notifier import send_telegram_alert
from config.portfolio import MY_PORTFOLIO

DRY_RUN = "--dry-run" in sys.argv

# Holiday file path
HOLIDAYS_FILE = Path("config/nse_holidays.json")

def is_market_hours() -> bool:
    # Market hours: 09:15 to 15:30 IST
    now = datetime.now().time()
    # 03:45 UTC is 09:15 IST, 10:00 UTC is 15:30 IST
    market_open = time(3, 45) 
    market_close = time(10, 0)
    return market_open <= now <= market_close
    
def is_market_holiday(today: date) -> bool:
    if not HOLIDAYS_FILE.exists():
        return False
    try:
        with open(HOLIDAYS_FILE, "r", encoding="utf-8") as f:
            holidays = json.load(f)
        return today.isoformat() in set(holidays)
    except Exception:
        return False

def technical_signal(stock_data: Dict) -> str:
    ma50 = stock_data.get("ma_50")
    ma200 = stock_data.get("ma_200")
    price = stock_data.get("price")
    if ma50 is None or ma200 is None or price is None:
        return "NEUTRAL"
    if price < ma50 and price < ma200:
        return "SELL"
    if price > ma50 and price > ma200:
        return "BUY"
    return "NEUTRAL"

def fundamental_signal(stock_data: Dict) -> str:
    pe = stock_data.get("pe")
    try:
        pe_val = float(pe) if pe not in (None, "N/A") else None
    except Exception:
        pe_val = None
    if pe_val is None:
        return "NEUTRAL"
    if pe_val > 40:
        return "WEAK"
    if pe_val < 8:
        return "STRONG"
    return "NEUTRAL"

def should_send_alert(ai_decision: str, technical: str, fundamental: str) -> (bool, str):
    # Conservative rule: prefer AI; fallback only when AI missing
    if ai_decision == "SELL":
        return True, "AI recommended SELL."
    if not ai_decision:  # AI not available
        if technical == "SELL" and fundamental == "WEAK":
            return True, "Technical SELL and Fundamental WEAK signals detected (no AI)."
    return False, f"AI decision: {ai_decision or 'N/A'}; Technical: {technical}; Fundamental: {fundamental}"

def analyze_ticker(ticker: str):
    print(f"📈 Analyzing {ticker}...")
    stock_data = get_stock_data(ticker)
    import math
    if not stock_data or stock_data.get("price") is None or (isinstance(stock_data.get("price"), float) and math.isnan(stock_data.get("price"))):
        print(f"⚠️ Skipping {ticker}: no valid price (None/NaN).")
        return {
            "ticker": ticker,
            "price": None,
            "technical": "NEUTRAL",
            "fundamental": "NEUTRAL",
            "ai_decision": "N/A",
            "ai_analysis": "No price data",
            "alert_sent": False,
            "alert_reason": "No price data"
        }
    technical = technical_signal(stock_data)
    fundamental = fundamental_signal(stock_data)

    # Fetch news only if Tavily key present
    news = fetch_market_news(ticker) if TAVILY_API_KEY else "No news API configured"

    ai_text = analyze_with_groq(ticker, stock_data, news)  # may be None
    ai_decision = parse_ai_decision(ai_text) if ai_text else ""

    send_alert, reason = should_send_alert(ai_decision, technical, fundamental)

    alert_result = False
    if send_alert:
        alert_result = send_telegram_alert(
            ticker=ticker,
            stock_data=stock_data,
            analysis_text=ai_text or "N/A",
            reason_summary=reason,
            dry_run=DRY_RUN
        )

    return {
        "ticker": ticker,
        "price": stock_data.get("price"),
        "change_pct": stock_data.get("change_pct"),
        "technical": technical,
        "fundamental": fundamental,
        "ai_decision": ai_decision or "N/A",
        "ai_analysis": ai_text or "N/A",
        "alert_sent": bool(send_alert and alert_result),
        "alert_reason": reason
    }

def main():
    today = date.today()
    # Skip weekends
    if today.weekday() >= 5:
        print("Weekend detected; exiting.")
        return

    # Skip exchange holidays
    if is_market_holiday(today):
        print("Market holiday today; exiting.")
        return

    # if not DRY_RUN and not is_market_hours():
    #     print("Outside market hours; exiting.")
    #     return

    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_file = Path("outputs") / f"analysis_{ts}.txt"
    print("="*60)
    print("Stock Analysis Started -", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)
    results = []
    for ticker in MY_PORTFOLIO.keys():
        res = analyze_ticker(ticker)
        results.append(res)
        # polite pause
        tm.sleep(1)

    # write summary
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("="*60 + "\n")
        f.write(f"Stock Analysis Started - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*60 + "\n\n")
        for r in results:
            f.write(f"TICKER: {r['ticker']}\n")
            f.write(f"  Price: ₹{r.get('price')} ({r.get('change_pct')}%)\n")
            f.write(f"  Technical signal: {r.get('technical')}\n")
            f.write(f"  Fundamental signal: {r.get('fundamental')}\n")
            f.write(f"  AI decision: {r.get('ai_decision')}\n")
            f.write("  AI analysis:\n")
            f.write(f"  {r.get('ai_analysis')}\n")
            f.write(f"  Alert sent: {r.get('alert_sent')}\n")
            f.write(f"  Alert reason: {r.get('alert_reason')}\n")
            f.write("-"*60 + "\n")
            if r.get("alert_sent"):
                f.write("  Telegram send result: True\n")
            else:
                f.write("  No alert sent.\n")
    print("\n✅ Complete! Log:", out_file)

if __name__ == "__main__":
    main()
