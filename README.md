# Telegram Cleaner Bot

A Telegram bot that helps users clean and analyze their browser cookies for better privacy.

## Features

- **Cookie Cleaning**: Upload your cookies file (Edge format) and get a cleaned version with only essential auth cookies
- **Privacy Analysis**: Get detailed statistics about your cookie profile, including privacy score and tracking detection
- **ID Tools**: Get your Telegram ID or extract IDs from forwarded messages
- **Monitoring**: Built-in Prometheus metrics and Grafana dashboards

## Architecture

- `cleaner/` - Core package containing bot logic, cookie cleaning algorithms, and configuration
- `monitoring/` - Prometheus and Grafana configurations for metrics collection
- `main.py` - CLI tool for local cookie analysis

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`:
   ```
   BOT_TOKEN=your_telegram_bot_token_here
   METRICS_PORT=8000
   GF_SECURITY_ADMIN_PASSWORD=admin
   ```

3. Run with Docker:
   ```bash
   docker-compose up
   ```

Or run locally:
```bash
python -m cleaner.bot
```

## Usage

1. Start a chat with the bot
2. Use `/start` to see available options
3. Upload your cookies file for cleaning
4. Get detailed analysis and privacy insights

![Bot Interface](image.png)
