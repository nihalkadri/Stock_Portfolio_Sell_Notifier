import os
import time
import requests
from typing import Dict, Any

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(ticker: str,
                        stock_data: Dict[str, Any],
                        analysis_text: str,
                        reason_summary: str,
                        dry_run: bool = True) -> bool:
    message = (
        f"📉 *Sell Alert: {ticker}*\n\n"
        f"Price: ₹{stock_data.get('price')}\n"
        f"Change: {stock_data.get('change_pct')}%\n\n"
        f"*Reason:*\n{reason_summary}\n\n"
        f"*AI Analysis:*\n{analysis_text or 'N/A'}"
    )

    if dry_run:
        print("DRY RUN - Telegram message would be:")
        print(message)
        return True

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Telegram credentials not set; cannot send message.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            print(f"✅ Sell alert sent [{ticker}]")
            return True
        except requests.exceptions.Timeout:
            if attempt < 2:
                time.sleep(2)
                continue
        except Exception as e:
            print(f"⚠️ Telegram send error (attempt {attempt+1}): {e}")
            if attempt < 2:
                time.sleep(2)
                continue

    print(f"⚠️ Alert failed [{ticker}]")
    return False
