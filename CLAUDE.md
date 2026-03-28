# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Bot

```bash
source venv/bin/activate
python robo_cripto.py
```

Requires a `.env` file with:
```
KEY_BINANCE=<api_key>
SECRET_BINANCE=<api_secret>
```

## Architecture

This is a live cryptocurrency trading bot for the SOLBRL pair on Binance. There is no simulation mode — all orders are real.

**Single main file: `robo_cripto.py`**

Execution flow (infinite loop, 1-hour cadence):
1. Display non-zero account balances
2. `pegando_dados()` — fetches 1000 hourly OHLCV candles from Binance
3. `estrategia_trade()` — computes 7-period (fast) and 40-period (slow) moving averages; buys when fast > slow (if not already in position), sells when fast < slow (if in position)
4. `log_operacao()` — appends trade events to `log_operacoes.txt` with São Paulo timezone timestamps
5. `time.sleep(3600)`

**Position state** is held in the `posicao_atual` boolean in the main loop and passed into/returned from `estrategia_trade()` each cycle. It is not persisted to disk, so restarting the bot resets the position to `False` (not bought).

**Trade sizing**: buys use the fixed `quantidade = 0.015` SOL; sells use the actual free balance retrieved from the account at execution time (rounded down to 4 decimal places).

**`robo_cripto_parte_1.py`** is a one-off test script for verifying API connectivity and account balances — not part of the main bot flow.

## Dependencies

Managed via `venv/`. Key packages:
- `python-binance` 1.0.25
- `pandas` 2.3.2
- `python-dotenv` 0.21.1
