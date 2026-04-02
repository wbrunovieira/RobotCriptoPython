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
API_TOKEN=<api_token>
```

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q           # all tests
python -m pytest tests/test_foo.py   # single file
```

239 tests — must all pass before any merge.

## Architecture

Layered architecture for multi-bot support. All production orders are real (no simulation mode).

```
core/           — Pure domain logic (no I/O, 100% testable)
  indicadores.py    RSI, ATR, ADX calculations
  risco.py          stop-loss, trailing stop, take-profit, break-even
  sinais.py         MA crossover + RSI reversal signal evaluation

infra/          — All I/O and external services
  binance_client.py   Binance API client (sync clock)
  persistencia.py     position state JSON files
  stats_store.py      daily trade stats JSON files
  reserva_store.py    USDC reserve + P&L tracking
  notificacao.py      WhatsApp via Evolution API

pares/          — Trading pair universe
  brl.py            BRL pairs list (SOL/BTC/ETH/XRP/BNB)
  base.py           pair utilities (arquivo_posicao, calcular_saldo_disponivel)

bots/brl/       — BRL bot orchestration
  config.py         env-var config constants
  robo.py           full bot logic (ciclo, executar_compra, executar_venda, etc.)

api/            — FastAPI REST API
  main.py           thin app entry + router registration
  deps.py           shared helpers and auth dependency
  rotas/
    brl.py          trading routes (status, posicoes, stats, saldos, bot control)
    aportes.py      portfolio/aporte CRUD
    fiscal.py       fiscal CSV export + monthly stats

analysis/       — Offline tools (not used in production)
  backtesting.py
  otimizador.py
```

**Backward-compat wrappers** (kept for `from X import Y` compatibility):
`estrategia.py`, `persistencia.py`, `conexao.py`, `notificacao.py`, `stats.py`, `reserva.py` — all thin re-exports from their `core/` or `infra/` counterparts.

**Entry point**: `robo_cripto.py` → `bots/brl/robo.py` → runs the infinite loop.

**Position state**: persisted to `posicao_{SIMBOLO}.json` per pair (survives restarts).

**Strategy**: MA9/MA21 crossover + RSI reversal, with ADX filter, ATR-based trailing stop, break-even, take-profit, weekend volume filter, daily loss limit, portfolio stop.

**Multi-pair**: SOL/BTC/ETH/XRP/BNB all in BRL; up to `MAX_POSICOES` concurrent positions; each pair limited to `TETO_SALDO_PCT` (60%) of available BRL.

## Key Config (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `BOT_STOP_PCT` | 0.015 | Trailing stop % |
| `BOT_TAKE_PROFIT_PCT` | 0.02 | Take-profit target |
| `BOT_TETO_SALDO_PCT` | 0.60 | Max BRL per pair |
| `BOT_MAX_POSICOES` | 3 | Max concurrent positions |
| `BOT_INTERVALO_MONITORAMENTO` | 60 | Stop-check interval (s) |
| `BOT_INTERVALO_ESTRATEGIA_MIN` | 15 | Strategy cycle interval (min) |

## Dependencies

Managed via `venv/`. Key packages:
- `python-binance` 1.0.25
- `pandas` 2.3.2
- `fastapi` + `uvicorn`
- `python-dotenv` 0.21.1
