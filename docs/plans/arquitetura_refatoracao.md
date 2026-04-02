# Arquitetura — Refatoração para múltiplos bots

> Análise de engenheiro sênior. Objetivo: suportar múltiplos bots sem quebrar produção.

---

## 1. Diagnóstico — problemas atuais

- **`robo_cripto.py` faz tudo:** busca dados, calcula risco, executa ordens, gerencia bloqueios, lê arquivos — responsabilidades demais num único arquivo
- **`estrategia.py` mistura:** funções matemáticas puras (RSI, ATR, ADX) + lógica de negócio com filtros + orquestração de posições
- **`stats.py`:** mistura persistência (I/O) com cálculo de métricas
- **Paths hardcoded por toda parte:** `reserva/estado.json`, `stats/aportes.json`, `posicao_{SIMBOLO}.json` — dois bots colidiriam nos mesmos arquivos
- **`backtesting.py` e `otimizador.py`** no mesmo namespace de produção — ferramentas offline misturadas com código que roda 24h
- **`api/main.py`** gigante — um arquivo para tudo, sem separação por domínio

---

## 2. Estrutura proposta

```
cripto_robot/
│
├── bots/                          # Cada bot é um pacote auto-contido
│   ├── brl/                       # Bot atual (BRL, MA-crossover)
│   │   ├── __init__.py
│   │   ├── robo.py                # Loop principal (era robo_cripto.py)
│   │   └── config.py              # Constantes do bot BRL
│   │
│   └── meme/                      # Bot novo (USDT, scanner)
│       ├── __init__.py
│       ├── robo.py
│       ├── config.py              # Era config_meme.py
│       └── scanner.py             # Era scanner_meme.py
│
├── core/                          # Domínio puro — sem I/O, sem Binance, 100% testável
│   ├── __init__.py
│   ├── indicadores.py             # calcular_rsi, calcular_atr, calcular_adx
│   ├── sinais.py                  # avaliar_sinal, _horario_permitido, _volume_acima_media
│   ├── risco.py                   # trailing stop, take_profit, breakeven, stop_pct_por_atr
│   ├── sizing.py                  # calcular_quantidade, calcular_saldo_disponivel
│   └── fiscal.py                  # calcular_imposto, resumo_mensal
│
├── infra/                         # Toda I/O fica aqui
│   ├── __init__.py
│   ├── binance_client.py          # criar_cliente_sincronizado (era conexao.py)
│   ├── persistencia.py            # salvar_posicao, carregar_posicao
│   ├── stats_store.py             # iniciar_stats_do_dia, registrar_compra/venda
│   ├── reserva_store.py           # registrar_resultado, deve_converter, etc.
│   ├── notificacao.py             # enviar_whatsapp
│   └── log_store.py               # log_operacao, bloqueio_portfolio
│
├── pares/                         # Universo de pares por bot
│   ├── __init__.py
│   ├── brl.py                     # _PARES lista BRL
│   ├── meme.py                    # MEME_UNIVERSE lista USDT
│   └── base.py                    # listar_pares, arquivo_posicao, consolidar_resumo
│
├── api/
│   ├── main.py                    # Monta app, registra routers (enxuto)
│   ├── deps.py                    # _verificar_token e dependências compartilhadas
│   └── rotas/
│       ├── brl.py                 # Endpoints do bot BRL
│       ├── meme.py                # Endpoints do bot meme
│       ├── aportes.py             # Endpoints de aportes
│       └── fiscal.py              # Relatório fiscal
│
├── analysis/                      # Ferramentas offline — nunca importadas em produção
│   ├── backtesting.py
│   └── otimizador.py
│
├── tests/
│   ├── core/
│   │   ├── test_indicadores.py
│   │   ├── test_sinais.py
│   │   └── test_risco.py
│   ├── infra/
│   │   ├── test_persistencia.py
│   │   ├── test_stats.py
│   │   └── test_reserva.py
│   └── bots/
│       ├── test_estrategia_brl.py
│       ├── test_scanner_meme.py
│       └── test_config_meme.py
│
├── stats/          # dados runtime — não é código, não mover
├── reserva/
├── config/
│
├── robo_cripto.py  # MANTIDO como thin wrapper (entry point não muda)
├── .env
├── requirements.txt
└── CLAUDE.md
```

---

## 3. Mapeamento arquivo atual → novo local

| Arquivo atual | Novo caminho | Motivo |
|---|---|---|
| `robo_cripto.py` | mantido raiz (thin) + `bots/brl/robo.py` | Entry point não muda no servidor |
| `estrategia.py` (indicadores) | `core/indicadores.py` | Funções matemáticas puras |
| `estrategia.py` (sinais) | `core/sinais.py` | Lógica de decisão da estratégia |
| `estrategia.py` (risco) | `core/risco.py` | Proteções de capital |
| `pares.py` | `pares/brl.py` + `pares/base.py` | Separar universo BRL de lógica compartilhada |
| `persistencia.py` | `infra/persistencia.py` | I/O puro |
| `conexao.py` | `infra/binance_client.py` | Infraestrutura de rede |
| `notificacao.py` | `infra/notificacao.py` | I/O externo |
| `stats.py` | `infra/stats_store.py` | Deixar claro que é storage |
| `reserva.py` | `infra/reserva_store.py` | I/O do estado de reserva |
| `fiscal.py` | `core/fiscal.py` (cálculos) | Separar lógica de leitura de disco |
| `backtesting.py` | `analysis/backtesting.py` | Ferramenta offline |
| `otimizador.py` | `analysis/otimizador.py` | Ferramenta offline |
| `api/main.py` | `api/rotas/*.py` + `api/main.py` enxuto | Separar rotas por domínio |

---

## 4. Princípios adotados

- **`core/` nunca faz I/O** — testável com pytest sem mock, sem Binance, sem disco
- **`infra/` concentra toda I/O** — trocar de exchange = mudar só `infra/binance_client.py`
- **Bots como pacotes** — configs isoladas, sem colisão de nomes globais
- **Entry points finos na raiz** — `robo_cripto.py` vira 3 linhas; comando no servidor não muda
- **`analysis/` fora do path de runtime** — backtesting não é importável acidentalmente
- **Sem over-engineering** — sem classes Strategy base, sem injeção de dependência. Só separação de arquivos.

---

## 5. Plano de migração gradual (ordem de risco crescente)

### Passo 1 — Sem risco (15 min)
Criar `analysis/` e mover `backtesting.py` e `otimizador.py`. Não são importados por ninguém em produção.

### Passo 2 — Baixo risco (30 min)
Criar `core/indicadores.py` com funções matemáticas de `estrategia.py`.
Em `estrategia.py`, substituir corpos por reexportes: `from core.indicadores import *`.
Todos os imports existentes continuam funcionando. Rodar testes.

### Passo 3 — Baixo risco (30 min)
Criar `core/risco.py` e `core/sinais.py`. Mesmo padrão de reexporte.

### Passo 4 — Médio risco (1-2h) — fazer quando criar bot meme
Criar pacote `bots/brl/` e mover lógica do loop principal para `bots/brl/robo.py`.
`robo_cripto.py` na raiz vira thin wrapper. **Testar localmente antes de deploy.**

### Passo 5 — Médio risco — após bot meme estável
Refatorar `api/main.py` em rotas separadas. API pública não muda.

---

## 6. O que NÃO mover agora

| Arquivo | Motivo |
|---|---|
| `robo_cripto.py` (entry point) | Processo no servidor configurado com este caminho |
| `persistencia.py` | Mudança quebra imports em cascata — migrar junto com Passo 4 |
| `stats.py` | Usado em prod e na API — migrar com cuidado no Passo 4/5 |
| `reserva.py` | Contém estado financeiro real — migrar por último com testes de integração |
| `pares.py` | Estável, sem ganho imediato — separar quando bot meme forçar a divisão |
| `stats/`, `reserva/`, `config/` | Não são código — mudar paths quebraria retrocompatibilidade |
