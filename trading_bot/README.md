# MT5 Paper Trading Bot (Textual TUI)

Production-style **demo/paper** trading bot for MetaTrader 5 with:
- MT5 connectivity (official `MetaTrader5` package) + auto-reconnect
- Dynamic symbol discovery + canonical mapping (suffix variants supported)
- Multi-asset ranking → correlation-diversified **top 5**
- Strategy registry + manual or ADX regime selection
- Safe execution with **idempotency**, retries, and risk controls
- Full persistence to SQLite (decisions/trades/errors/settings/heartbeats)
- Telegram notifications to **two chat IDs** (optional)
- Textual TUI: Dashboard, Trades, Decisions, Settings, Resources (CPU/RAM/Disk/Net/Temps)

## Important: MT5 on Linux
The official `MetaTrader5` Python package is **Windows-native**. For Linux Mint, run MT5 + the Python runtime under **Wine** (Windows Python inside the same Wine prefix), and run this bot there. Everything else in the codebase is OS-agnostic.

## Install
Create a venv and install editable:

```bash
cd trading_bot
python -m venv .venv
source .venv/bin/activate  # (Linux)  or  .venv\\Scripts\\activate  (Windows)
pip install -U pip
pip install -e ".[dev]"
```

> Note: This project uses a `src/` layout. If you see `ModuleNotFoundError: No module named 'trading_bot'`,
> you likely skipped the `pip install -e ...` step (or you installed into a different Python/venv than the one you're running).

## Configure
1) Copy examples:

```bash
cp config/config.example.yaml config/config.yaml
cp config/symbols.example.yaml config/symbols.yaml  # optional aliases
cp .env.example .env
```

2) Edit `.env`:
- `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID_USER` + `TELEGRAM_CHAT_ID_DAD` (optional)

3) Safety gates:
- `execution.trading_enabled` is **false by default** (read-only).
- Even when enabled, the bot **refuses to send orders** unless MT5 reports a **DEMO/CONTEST** account trade mode.

## Run diagnostics
```bash
python scripts/doctor.py --config config/config.yaml
```

## Run the bot
TUI:
```bash
python -m trading_bot.main --config config/config.yaml
```

Headless:
```bash
python -m trading_bot.main --config config/config.yaml --no-ui
```

If you want to run without installing editable, you can also do:
- PowerShell: `$env:PYTHONPATH="src"; python -m trading_bot.main --config config/config.yaml`
- bash/zsh: `PYTHONPATH=src python -m trading_bot.main --config config/config.yaml`

### TUI controls
- `1..5`: switch screens
- `P`: pause/resume (manual)
- `S`: save settings (Settings screen)
- `R`: refresh
- `Q`: quit

## Two-pole oscillator (deterministic)
We use an Ehlers-style **2-pole Super Smoother** filter:
- `smooth = SS2(close, period)`
- `osc = close - smooth`
- `signal = EMA(osc, signal_period)`

Recursive filter:
```
a1 = exp(-1.414*pi/period)
b1 = 2*a1*cos(1.414*pi/period)
c2 = b1
c3 = -a1^2
c1 = 1 - c2 - c3
y[t] = c1*(x[t] + x[t-1])/2 + c2*y[t-1] + c3*y[t-2]
```

## Systemd (Linux Mint)
See `systemd/trading-bot.service.example` (runs **headless** via `--no-ui`). Typical workflow:
1) Install under `/opt/trading-bot`
2) Put `.env` in the working directory (or referenced `EnvironmentFile`)
3) Enable/start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo journalctl -u trading-bot -f
```

## Extend to other brokers later
The rest of the bot depends on `trading_bot.connectors.base.BrokerConnector`.
To add a new broker:
1) Implement the interface
2) Return candles as a pandas DataFrame with UTC-aware timestamps
3) Fill positions/deals consistently
4) Populate `account_info.trade_mode` so paper-trading safety gates remain correct

## Quickstart commands
```bash
cd trading_bot
python -m venv .venv
source .venv/bin/activate  # (Linux)  or  .venv\\Scripts\\activate  (Windows)
pip install -e ".[dev]"
cp config/config.example.yaml config/config.yaml
cp .env.example .env
python scripts/doctor.py --config config/config.yaml
python -m trading_bot.main --config config/config.yaml
```

## Verification checklist
1) `doctor.py` passes
2) symbols discovered
3) ranking shows top 5
4) demo/paper order placed (set `execution.trading_enabled: true`)
5) trade appears in TUI + SQLite (`./data/bot.sqlite` by default)
6) Telegram message received (if configured)
7) Resources screen shows CPU/RAM/Net/Temps (temps may be N/A on some systems)
