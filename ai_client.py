import os
import requests
from typing import Optional
import re
import json
from dotenv import load_dotenv
from pathlib import Path

# ensure .env loaded if present
load_dotenv(dotenv_path=Path('.') / '.env')

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

def parse_ai_decision(ai_text: str) -> str:
    if not ai_text:
        return ""
    m = re.search(r"DECISION\s*:\s*\[?\s*(BUY|HOLD|SELL)\s*\]?", ai_text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    if re.search(r"\bSELL\b", ai_text, re.IGNORECASE):
        return "SELL"
    if re.search(r"\bBUY\b", ai_text, re.IGNORECASE):
        return "BUY"
    if re.search(r"\bHOLD\b", ai_text, re.IGNORECASE):
        return "HOLD"
    return ""

def build_prompt(ticker: str, stock_data: dict, news: str) -> str:
    prompt = (
        "You are an expert stock market analyst. Be concise and provide DECISION, TREND, and REASONING.\n\n"
        f"STOCK: {ticker}\n"
        f"Current Price: ₹{stock_data.get('price')} ({stock_data.get('change_pct')}% today)\n"
        f"50-Day MA: ₹{stock_data.get('ma_50')} | 200-Day MA: ₹{stock_data.get('ma_200')}\n"
        f"52-Week Range: ₹{stock_data.get('low_52w')} - ₹{stock_data.get('high_52w')}\n"
        f"P/E Ratio: {stock_data.get('pe')}\n\n"
        "Recent News:\n"
        f"{news}\n\n"
        "Provide your analysis in this exact format:\n"
        "DECISION: [BUY/HOLD/SELL]\n"
        "TREND: [Bullish/Bearish/Sideways]\n"
        "REASONING: [2-3 sentences]\n"
    )
    return prompt

def analyze_with_groq(ticker: str, stock_data: dict, news: str, timeout: int = 30) -> Optional[str]:
    if not LLM_API_KEY:
        print("⚠️ LLM_API_KEY not set; skipping AI analysis.")
        return None

    prompt = build_prompt(ticker, stock_data, news)
    url = f"{LLM_BASE_URL}/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are an expert stock market analyst. Be concise."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": 400
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            print(f"⚠️ LLM returned no choices for {ticker}: {data}")
            return None
        message = choices[0].get("message") or {}
        text = message.get("content") if isinstance(message, dict) else None
        if not text:
            text = choices[0].get("text")
        try:
            os.makedirs("outputs", exist_ok=True)
            with open(f"outputs/ai_raw_{ticker}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return text.strip() if text else None
    except Exception as e:
        print(f"❌ AI error [{ticker}]: {e}")
        return None
