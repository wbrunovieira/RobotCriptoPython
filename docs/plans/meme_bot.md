# Plano — Meme Coin Bot (USDT)

## Visão Geral

Bot paralelo ao bot atual (BRL), operando exclusivamente em pares USDT de meme coins.
Capital inicial: **$100 USDT**. Scanner a cada 15 minutos. Máximo 1 posição por vez.
Parâmetros centralizados em `config_meme.py` para fácil ajuste.

---

## Diferenças em relação ao bot atual

| Aspecto | Bot atual (BRL) | Bot meme (USDT) |
|---|---|---|
| Moeda base | BRL | USDT |
| Pares | 5 fixos | 12+ dinâmicos (scanner) |
| Candle | 1h | 15min |
| Ciclo de estratégia | 60 min | 15 min |
| Take profit | 2% | 5% (padrão) |
| Stop loss mín | 1.5% | 3% |
| ATR multiplicador | 2.2x | 3.5x |
| Volume mínimo | 1x média | 2x média |
| Posições simultâneas | 2 | 1 |
| Capital por trade | até 60% | até 80% do saldo USDT |

---

## Arquivos novos

```
robo_meme.py          — loop principal do bot meme
config_meme.py        — todos os parâmetros em um lugar
scanner_meme.py       — busca e ranqueia oportunidades
estrategia_meme.py    — sinais, indicadores, scoring
posicao_meme.json     — estado da posição atual
stats_meme/           — stats diários YYYY-MM-DD.json
api/rotas_meme.py     — endpoints FastAPI do bot meme
tests/
  test_scanner_meme.py
  test_estrategia_meme.py
  test_config_meme.py
frontend/app/meme/
  page.tsx             — dashboard aba Meme
frontend/components/
  TabsNav.tsx          — navegação entre abas
  MemeScanner.tsx      — tabela de score ao vivo
  MemePosicaoCard.tsx  — card da posição aberta
```

---

## Fase 1 — Backend Python

### 1.1 `config_meme.py` — parâmetros centralizados

```python
# Universe de moedas monitoradas
MEME_UNIVERSE = [
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT",
    "BONKUSDT", "FLOKIUSDT", "PNUTUSDT", "TRUMPUSDT",
    "NEIROUSDT", "MEMEUSDT", "ACTUSDT", "BOMEUSDT",
]

# Candle
PERIODO_CANDLE       = "15m"
CANDLES_HISTORICO    = 200      # candles para cálculo de indicadores
INTERVALO_SCANNER_S  = 900      # 15 minutos

# Sizing
CAPITAL_USDT         = 100.0    # capital total do bot
PERCENTUAL_COMPRA    = 0.80     # usa 80% do capital por trade

# Saída
TAKE_PROFIT_PCT      = 0.05     # 5%
STOP_PCT_MIN         = 0.03     # 3% mínimo
ATR_MULTIPLICADOR    = 3.5      # trailing stop = ATR × 3.5
BREAKEVEN_GATILHO    = 0.025    # move stop para entrada após +2.5%
BREAKEVEN_FOLGA      = 0.001    # stop em entrada + 0.1%

# Filtros de entrada (scoring)
SCORE_MINIMO         = 7        # score mínimo para entrar
SEP_MA_MINIMA_PCT    = 0.5      # separação mínima MA9/MA21
RSI_MIN              = 50       # RSI mínimo para Signal 1
RSI_MAX              = 65       # RSI máximo para Signal 1
RSI_SOBREVENDIDO     = 30       # RSI para Signal 2 (reversão)
ADX_MINIMO           = 20       # mercado com tendência
VOLUME_MULTIPLICADOR = 2.0      # volume mínimo vs média 20 candles

# Proteções
STOP_PORTFOLIO_PCT   = 0.08     # -8% do capital fecha tudo
LIMITE_DIARIO_PCT    = 0.05     # -5% do capital bloqueia o dia
MAX_POSICOES         = 1
```

### 1.2 `scanner_meme.py` — motor de busca

**Responsabilidades:**
- Busca candles de todos os pares do `MEME_UNIVERSE`
- Calcula MA9, MA21, MA50, RSI, ADX, ATR, volume ratio, variação 1h
- Atribui score 0–10 a cada par
- Retorna o par com maior score (se ≥ `SCORE_MINIMO`)

**Tabela de scoring:**

| Critério | Pontos |
|---|---|
| MA9 > MA21 e sep > 0.5% | +2 |
| Preço > MA50 | +1 |
| RSI entre 50–65 | +2 |
| RSI entre 45–50 | +1 |
| ADX > 25 | +2 |
| ADX 20–25 | +1 |
| Volume ≥ 2x média | +2 |
| Volume 1.5–2x média | +1 |
| Variação 15min > +0.5% | +1 |

**Saída:** `{"simbolo": "DOGEUSDT", "score": 8, "preco": 0.0901, "rsi": 57.3, ...}`

### 1.3 `estrategia_meme.py` — sinais de entrada e saída

Reutiliza funções de `estrategia.py` (`calcular_rsi`, `calcular_adx`, `calcular_atr`).
Adiciona lógica específica para meme:

- **Signal 1:** MA9 > MA21 (sep > 0.5%), RSI 50–65, ADX > 20, volume > 2x, preço > MA50
- **Signal 2:** RSI < 30 revertendo para cima, volume > 2x (reversão de dump)
- **Saída:** trailing stop ATR-based, TP 5%, MA crossover bearish (sep > 0.5%)
- **Breakeven:** após +2.5%, stop sobe para entrada + 0.1%

### 1.4 `robo_meme.py` — loop principal

```
Loop a cada 15 minutos:
  1. Verifica proteções (portfolio bloqueado, limite diário)
  2. Se posição aberta → checa trailing stop, TP, crossover bearish
  3. Se sem posição → roda scanner, pega melhor score
  4. Se score ≥ 7 → calcula stop ATR, executa compra
  5. Grava stats em stats_meme/YYYY-MM-DD.json
```

**Arquivos de estado:**
- `posicao_meme.json` — posição atual (simbolo, preco_entrada, stop, maximo)
- `stats_meme/YYYY-MM-DD.json` — mesmo formato do bot atual
- `portfolio_meme_bloqueado.json` — bloqueio de emergência

---

## Fase 2 — API FastAPI

Adicionar em `api/rotas_meme.py` (registrado no `main.py` existente):

| Endpoint | Método | Descrição |
|---|---|---|
| `/meme/status` | GET | posição atual, saldo USDT, P&L |
| `/meme/scanner` | GET | score de todos os pares agora |
| `/meme/operacoes` | GET | operações do dia |
| `/meme/stats/dia` | GET | resumo do dia |
| `/meme/stats/mes/{mes}` | GET | resumo mensal |
| `/meme/config` | GET | parâmetros atuais |
| `/meme/config` | PATCH | altera parâmetros em runtime |

O endpoint `PATCH /meme/config` permite mudar `TAKE_PROFIT_PCT`, `SCORE_MINIMO`, `VOLUME_MULTIPLICADOR` etc sem reiniciar o bot.

---

## Fase 3 — Frontend (abas)

### 3.1 Navegação por abas

Criar `frontend/components/TabsNav.tsx`:
- Aba **"Bot BRL"** → página atual (`/`)
- Aba **"Bot Meme"** → nova página (`/meme`)

O `layout.tsx` incluirá `<TabsNav />` acima do conteúdo, visível nas duas rotas.

### 3.2 Página `/meme` — `frontend/app/meme/page.tsx`

Seções (mesma estrutura visual da página atual):

1. **Status badge** — bot meme rodando/parado
2. **Card de posição aberta** — símbolo, entrada, stop, P&L atual, % desde entrada
3. **Scanner ao vivo** — tabela com score de cada meme coin (atualiza a cada 15s)
4. **Stats do dia** — operações, lucro, % acerto
5. **Tabela de operações** — compras e vendas do dia
6. **Evolução do capital USDT** — gráfico linha (igual ao GraficoEvolucao atual)

### 3.3 Componentes novos

- **`TabsNav.tsx`** — barra de abas no topo
- **`MemeScannerTabela.tsx`** — tabela de scores ao vivo com badge colorido por score
- **`MemePosicaoCard.tsx`** — card da posição meme (similar ao PosicaoCard atual)

---

## Fase 4 — Testes

### `tests/test_config_meme.py`
- Todos os parâmetros têm valores válidos (tipos, ranges)
- `SCORE_MINIMO` entre 5–10
- `TAKE_PROFIT_PCT` > `STOP_PCT_MIN`
- `PERCENTUAL_COMPRA` ≤ 0.95

### `tests/test_scanner_meme.py`
- Scanner retorna `None` quando nenhum par atinge score mínimo
- Scanner retorna o par de maior score quando há múltiplos válidos
- Score calculado corretamente para cada critério individualmente
- Empate de score: retorna o de maior volume
- Par com erro na API: ignorado, não quebra o scanner
- Universe vazio: retorna `None` sem exceção

### `tests/test_estrategia_meme.py`
- Signal 1 dispara com todos os critérios satisfeitos
- Signal 1 bloqueado se sep < 0.5%
- Signal 1 bloqueado se ADX < 20
- Signal 1 bloqueado se volume < 2x
- Signal 2 dispara com RSI < 30 revertendo + volume
- Saída por TP: retorna "VENDER" quando preço ≥ entrada × 1.05
- Saída por trailing stop: retorna "VENDER" quando preço cai abaixo do stop
- Saída por crossover bearish com sep > 0.5%
- Breakeven ativado após +2.5%: stop sobe para entrada + 0.1%
- Sem sinal em mercado lateral (ADX < 20)

---

## Ordem de implementação

1. `config_meme.py` + `tests/test_config_meme.py`
2. `estrategia_meme.py` + `tests/test_estrategia_meme.py`
3. `scanner_meme.py` + `tests/test_scanner_meme.py`
4. `robo_meme.py` (loop principal)
5. `api/rotas_meme.py` + integração no `main.py`
6. `frontend/components/TabsNav.tsx` + refactor `layout.tsx`
7. `frontend/app/meme/page.tsx` + componentes meme

---

## Critérios de aceite

- [ ] Todos os testes passando (`pytest tests/test_config_meme.py tests/test_scanner_meme.py tests/test_estrategia_meme.py`)
- [ ] Bot meme roda em paralelo sem interferir no bot BRL
- [ ] Parâmetros alteráveis via `config_meme.py` sem tocar em nenhum outro arquivo
- [ ] Dashboard exibe as duas abas funcionando
- [ ] Scanner atualiza ao vivo na aba Meme
- [ ] Capital USDT nunca ultrapassa `PERCENTUAL_COMPRA × CAPITAL_USDT` por trade
