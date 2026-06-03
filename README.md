# Stock Notifier

A Python project that monitors a portfolio, fetches price and fundamental data, optionally fetches news, runs an LLM analysis, and sends Telegram alerts for sell signals.

## Features

- Fetches historical and current price data using `yfinance`.
- Computes simple technical signals (50-day and 200-day MA).
- Computes a basic fundamental signal from P/E ratio.
- Optionally fetches news via Tavily (if `TAVILY_API_KEY` is set).
- Calls an LLM (Groq/OpenAI-compatible endpoint) for concise analysis.
- Sends Telegram alerts (configurable; dry-run supported).
- Writes run logs to `outputs/analysis_*.txt` and raw AI responses to `outputs/ai_raw_<TICKER>.json`.

## File overview

- **`stock_agent.py`** — Main orchestrator. Iterates portfolio, computes signals, calls AI, and triggers alerts.
- **`data_fetch.py`** — Fetches price history and optional news. Exposes `get_stock_data()` and `fetch_market_news()`.
- **`ai_client.py`** — Builds prompt and calls LLM. Writes raw LLM JSON to `outputs/`.
- **`telegram_notifier.py`** — Sends Telegram messages; supports `dry_run=True` to avoid real sends.
- **`config/portfolio.py`** — Your portfolio mapping (tickers → qty/avg). Edit to match your holdings.
- **`requirements.txt`** — Python dependencies.
- **`.env.sample`** — Template for environment variables. Copy to `.env` and fill values.

## Quick start

1. **Clone repo** and `cd` into it.

2. **Create venv and activate** (PowerShell):
   ```powershell
   python -m venv .venv
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
   .\.venv\Scripts\Activate.ps1
