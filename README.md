# Cripto Robot

Bot de trading automatizado para Binance (SOLBRL, BTCBRL, ETHBRL) com dashboard web.

## Pré-requisitos

- Python 3.11+
- Node.js 18+ e pnpm
- Conta na Binance com API Key habilitada para trading

---

## Configuração inicial

### 1. Variáveis de ambiente

Crie o arquivo `.env` na raiz do projeto:

```env
KEY_BINANCE=sua_api_key
SECRET_BINANCE=sua_api_secret
API_TOKEN=cripto2026
```

### 2. Ambiente Python

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install fastapi uvicorn
```

### 3. Dependências do frontend

```bash
cd frontend
pnpm install
```

---

## Executando os serviços

São **3 processos independentes**, cada um em um terminal separado.

### Terminal 1 — Bot de trading

```bash
source venv/bin/activate
python robo_cripto.py
```

Executa ordens reais na Binance. Avalia sinais a cada 15 minutos e monitora stops a cada 1 minuto.

### Terminal 2 — API backend

```bash
cd api
source ../venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

Serve os dados do bot para o dashboard. Roda em `http://localhost:8000`.

### Terminal 3 — Frontend (desenvolvimento)

```bash
cd frontend
pnpm dev
```

Dashboard disponível em `http://localhost:3000`. Login com o `API_TOKEN` definido no `.env`.

---

## Testes

```bash
source venv/bin/activate
pytest tests/
```

Para rodar um arquivo específico:

```bash
pytest tests/test_estrategia.py -v
```

---

## Estrutura dos dados

Os serviços se comunicam via arquivos JSON gravados na raiz do projeto:

| Arquivo | Conteúdo |
|---|---|
| `posicao_SOLBRL.json` | Posição atual, preço de entrada, topo e stop |
| `posicao_BTCBRL.json` | Idem para BTC |
| `posicao_ETHBRL.json` | Idem para ETH |
| `stats/YYYY-MM-DD.json` | Operações e lucro do dia |
| `reserva/estado.json` | Saldo USDC acumulado |
| `status.json` | Status do bot (último ciclo, versão) |
