# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Services

Three independent processes — each needs `source venv/bin/activate` first.

```bash
python robo_cripto.py          # BRL bot (real orders on Binance)
python robo_meme.py            # Meme bot (USDT pairs, real orders)
uvicorn api.main:app --host 0.0.0.0 --port 8000   # REST API
```

Frontend (Node.js/pnpm):
```bash
cd frontend && pnpm dev        # dashboard at http://localhost:3000
cd frontend && pnpm build      # production build
```

Requires a `.env` file with:
```
KEY_BINANCE=<api_key>
SECRET_BINANCE=<api_secret>
API_TOKEN=<api_token>

# WhatsApp notifications via Evolution API (optional)
EVOLUTION_URL=<evolution_api_base_url>
EVOLUTION_API_KEY=<evolution_api_key>
EVOLUTION_INSTANCE=<instance_name>
WHATSAPP_NUMBER=<phone_with_country_code>
```

Frontend requires `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000   # points to FastAPI backend
```

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -q           # all tests (unit only)
python -m pytest tests/test_foo.py   # single file
python -m pytest -m e2e              # E2E tests — require real Binance credentials
```

All non-E2E tests must pass before any merge. E2E tests (`tests/e2e/`) hit the real Binance API and require valid `.env` credentials; they are skipped in CI unless explicitly marked.

## Architecture

Layered architecture for multi-bot support. All production orders are real (no simulation mode).

```
core/           — Pure domain logic (no I/O, 100% testable)
  indicadores.py    RSI, ATR, ADX calculations
  risco.py          stop-loss, trailing stop, take-profit, break-even
  sinais.py         MA crossover + RSI reversal signal evaluation
  padroes.py        chart pattern detection (falling wedge, bull flag) — pre-crossover entry signals

infra/          — All I/O and external services
  binance_client.py   Binance API client (sync clock)
  persistencia.py     position state JSON files
  stats_store.py      daily trade stats JSON files
  reserva_store.py    USDC reserve + P&L tracking
  notificacao.py      WhatsApp via Evolution API
  fiscal.py           fiscal/tax helpers (monthly stats, CSV export)

pares/          — Trading pair universe
  brl.py            BRL pairs list (SOL/BTC/ETH/XRP/BNB)
  base.py           pair utilities (arquivo_posicao, calcular_saldo_disponivel)

bots/brl/       — BRL bot orchestration
  config.py         env-var config constants
  robo.py           full bot logic (ciclo, executar_compra, executar_venda, etc.)

bots/meme/      — Meme-coin bot (USDT) orchestration
  config.py         env-var config constants + MEME_UNIVERSE coin list
  scanner.py        ranks coins by momentum score (scan_melhor / scan_todos)
  estrategia.py     avaliar_sinal_meme + calcular_stop_inicial
  robo.py           full bot logic (mirrors brl/robo.py structure)

api/            — FastAPI REST API
  main.py           thin app entry + router registration
  deps.py           shared helpers and auth dependency
  rotas/
    brl.py          BRL trading routes (status, posicoes, stats, saldos, bot control)
    meme.py         Meme bot routes (mirrors brl.py)
    aportes.py      portfolio/aporte CRUD
    fiscal.py       fiscal CSV export + monthly stats

analysis/       — Offline tools (not used in production)
  backtesting.py      simulation backtesting
  backtest_real.py    real-data backtesting (buscar_candles_periodo)
  backtest_runner.py  CLI: --dias, --par, --comparar, --salvar fixtures/
  otimizador.py
```

**Backward-compat wrappers** (kept for `from X import Y` compatibility):
`estrategia.py`, `persistencia.py`, `conexao.py`, `notificacao.py`, `stats.py`, `reserva.py` — all thin re-exports from their `core/` or `infra/` counterparts.

**Entry points**: `robo_cripto.py` → `bots/brl/robo.py`; `robo_meme.py` → `bots/meme/robo.py` — both run infinite loops.

**Position state**: BRL bot persists to `posicoes/posicao_{SIMBOLO}.json`; Meme bot to `posicoes/posicao_meme.json`. Stats directories: `stats/` (BRL) and `stats_meme/` (Meme). Runtime files: `run/status.json` (PID + last cycle), `run/bloqueio_portfolio.json`, `run/cooldown_pares.json`. Reserve: `reserva/estado.json`.

**Bot runtime loop**: `ciclo()` runs full strategy every `INTERVALO_ESTRATEGIA`; between cycles, a tighter loop checks stops every `INTERVALO_MONITORAMENTO` (60s) without re-evaluating signals. SIGINT/SIGTERM sets `_parar` flag — the bot finishes its current cycle before exiting. On network/Binance errors the bot retries with exponential backoff (up to 300s) and sends a WhatsApp alert after 3 consecutive failures.

**Binance client**: `criar_cliente_sincronizado()` (`infra/binance_client.py`) syncs the local clock against Binance server time to prevent `-1022` signature errors. Always use this factory instead of instantiating `Client` directly.

**API auth**: all FastAPI routes require `Authorization: Bearer {API_TOKEN}` (single shared token from env).

**BRL strategy**: MA9/MA21 crossover + RSI reversal, ADX filter, ATR-based trailing stop, break-even, take-profit, weekend volume filter, daily loss limit, portfolio stop.

**Meme strategy**: Scanner scores coins (MA sep, RSI range, ADX, volume spike) → `SCORE_MINIMO` threshold → enter with ATR-based stop; max 1 concurrent position (`MAX_POSICOES=1`).

**Multi-pair (BRL)**: SOL/BTC/ETH/XRP/BNB; up to `MAX_POSICOES` concurrent positions; each pair limited to `TETO_SALDO_PCT` (60%) of available BRL.

## Key Config (env vars)

**BRL bot** (`BOT_*`):

| Var | Default | Meaning |
|-----|---------|---------|
| `BOT_STOP_PCT` | 0.015 | Trailing stop % |
| `BOT_TAKE_PROFIT_PCT` | 0.02 | Take-profit target |
| `BOT_TETO_SALDO_PCT` | 0.60 | Max BRL per pair |
| `BOT_MAX_POSICOES` | 3 | Max concurrent positions |
| `BOT_INTERVALO_MONITORAMENTO` | 60 | Stop-check interval (s) |
| `BOT_INTERVALO_ESTRATEGIA_MIN` | 15 | Strategy cycle interval (min) |

**Meme bot** (`MEME_*`):

| Var | Default | Meaning |
|-----|---------|---------|
| `MEME_CAPITAL_USDT` | 100.0 | Total USDT capital |
| `MEME_TAKE_PROFIT_PCT` | 0.05 | Take-profit target |
| `MEME_STOP_PCT_MIN` | 0.03 | Minimum stop % |
| `MEME_ATR_MULT` | 3.5 | ATR multiplier for stop |
| `MEME_SCORE_MINIMO` | 7 | Min scanner score to enter |
| `MEME_STOP_PORTFOLIO_PCT` | 0.08 | Portfolio stop loss % |
| `MEME_LIMITE_DIARIO_PCT` | 0.05 | Daily loss limit % |
| `MEME_INTERVALO_S` | 900 | Scanner cycle interval (s) |
| `MEME_BOT_ID` | MemeCoin1 | Bot identifier |

## Dependencies

Managed via `venv/`. Key packages:
- `python-binance` 1.0.25
- `pandas` 2.3.2
- `fastapi` + `uvicorn`
- `python-dotenv` 0.21.1
