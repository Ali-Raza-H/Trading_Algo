# Trading Algo

This repository contains a MetaTrader 5 (MT5) **demo/paper** trading bot.

The Python project lives in `trading_bot/` (docs, config examples, source, scripts, tests).

## Quickstart (Windows / PowerShell)

```powershell
cd trading_bot
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -e ".[dev]"
cp config\config.example.yaml config\config.yaml
cp config\symbols.example.yaml config\symbols.yaml
cp .env.example .env
python scripts\doctor.py --config config\config.yaml
python -m trading_bot.main --config config\config.yaml
```

For full docs (including Linux/Wine notes and a systemd example), see `trading_bot/README.md`.

