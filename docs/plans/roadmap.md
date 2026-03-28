# Roadmap — Cripto Robot

## Funcionalidades Implementadas

- [x] Estratégia de cruzamento de médias móveis (MA7 / MA40)
- [x] Filtro RSI (evita compra sobrecomprada, detecta reversão de queda)
- [x] Trailing stop loss com monitoramento a cada 1 minuto
- [x] Verificação de lucro mínimo (cobre taxas de 0,2%)
- [x] Persistência de posição em disco (sobrevive reinicializações)
- [x] Verificação de posição real na Binance (detecta divergências)
- [x] Notificações WhatsApp via Evolution API
- [x] Quantidade dinâmica de compra (90% do saldo BRL)
- [x] Log de operações com preço e timestamp
- [x] Soft stop (Ctrl+C encerra limpo após ciclo atual)
- [x] Sincronização automática de timestamp com servidor Binance
- [x] Testes automatizados TDD (97 testes)
- [x] Stats diários em `stats/YYYY-MM-DD.json` (base para dashboard e fiscal)

---

## Próximas Funcionalidades

### 1. Relatório Fiscal
> Gerado a partir dos stats diários.

- [x] Calcular imposto devido (15% sobre ganhos quando volume mensal > R$35.000)
- [x] Exportar CSV mensal organizado para declaração do IR
- [x] Alertar via WhatsApp quando o volume mensal se aproximar do limite de isenção

### 2. Reserva em USDC

- [x] Acumular lucros em BRL até atingir R$30 mínimo para conversão
- [x] Converter 50% do lucro acumulado de BRL para USDC automaticamente
- [x] Registrar reserva acumulada em USDC no log e no relatório fiscal
- [x] Alertar via WhatsApp o valor convertido e reserva total em USDC

### 3. Backtesting

- [ ] Baixar dados históricos da Binance (candles SOLBRL)
- [ ] Simular a estratégia atual em dados passados
- [ ] Exibir resultado: lucro/prejuízo acumulado, drawdown máximo, % de acerto
- [ ] Comparar diferentes períodos de médias para encontrar o mais rentável

### 4. Ajuste Automático de Parâmetros
> Depende do backtesting (item 3).

- [ ] Testar combinações de períodos de médias (ex: 5/20, 7/40, 10/50)
- [ ] Testar diferentes níveis de RSI sobrecomprado/sobrevendido
- [ ] Testar diferentes percentuais de stop loss
- [ ] Selecionar automaticamente os parâmetros com melhor resultado histórico

### 5. Múltiplos Pares

- [ ] Suporte a BTCBRL e ETHBRL em paralelo com SOLBRL
- [ ] Gerenciar posição e trailing stop independente por par
- [ ] Distribuir saldo BRL entre os pares ativos
- [ ] Relatório consolidado de todos os pares

### 6. Frontend Web
> Dashboard principal do bot — substitui o terminal. Alimentado pelos stats diários.

- [ ] API REST em FastAPI expondo: status do bot, saldo, posição atual, histórico de operações
- [ ] Dashboard em Next.js com atualização em tempo real (WebSocket ou polling)
- [ ] Página principal: status, saldo BRL/USDC/SOL, lucro do dia e acumulado
- [ ] Resumo do dia: operações realizadas, % acerto, maior ganho, maior perda
- [ ] Gráfico de preço da SOL com marcações de compra/venda do bot
- [ ] Indicadores em tempo real: MA7, MA40, RSI, trailing stop atual
- [ ] Histórico de operações com filtro por data e par
- [ ] Relatório fiscal exportável direto pelo painel
- [ ] Autenticação simples (login/senha) para proteger o painel
- [ ] Deploy em subdomínio: `cripto.wbdigitalsolutions.com`

### 7. Deploy no Servidor 24h

- [ ] Containerizar o bot em Docker
- [ ] Docker Compose com bot + API FastAPI + frontend Next.js
- [ ] Nginx reverse proxy para `cripto.wbdigitalsolutions.com` com SSL Let's Encrypt
- [ ] Stats e logs em volume Docker persistente
- [ ] Ao reiniciar container, carregar histórico do dia e retomar operações
- [ ] Healthcheck: se o bot ficar mais de 2h sem ciclo, notifica via WhatsApp
- [ ] Servidor: Contabo VPS 45.90.123.190 (6 cores, 11GB RAM, 100GB NVMe)
- [ ] Diretório do projeto: `/opt/cripto-robot/`

---

## Decisões de Arquitetura

- **Moeda operacional:** BRL (compra/venda de SOL)
- **Reserva de valor:** USDC (50% do lucro acumulado acima de R$30)
- **Caixa de SOL:** zero entre operações — SOL só quando bot sinalizar compra
- **Capital inicial:** R$1.000 (R$900 operacional + R$100 reserva emergência)
- **Stats:** um arquivo JSON por dia em `stats/YYYY-MM-DD.json`
- **Dashboard:** frontend web (não terminal) — bot roda 24h em servidor
- **Frontend stack:** FastAPI (backend) + Next.js (frontend)
- **Infraestrutura:** Docker + Nginx + Let's Encrypt no servidor Contabo existente
