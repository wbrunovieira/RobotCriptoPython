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
- [x] Testes automatizados TDD (49 testes)

---

## Próximas Funcionalidades

### ~~1. Stats Diários~~ ✅
> Base para dashboard, relatório fiscal e frontend web. Cada dia gera um arquivo `stats/YYYY-MM-DD.json`.

- [x] Criar `stats/YYYY-MM-DD.json` por dia com saldo inicial, operações e resumo
- [x] Registrar compra: preço, quantidade, total BRL, timestamp
- [x] Registrar venda: preço, quantidade, lucro BRL, lucro %, timestamp
- [x] Calcular resumo: total operações, % acerto, maior ganho, maior perda
- [x] Ao reiniciar, carregar stats do dia atual e retomar sem perder histórico
- [x] Persistir saldo inicial apenas na primeira execução do dia

### 2. Dashboard no Terminal
> Alimentado pelos stats diários (item 1).

- [ ] Exibir resumo do dia ao iniciar: saldo inicial vs atual
- [ ] Total de operações realizadas no dia e no mês
- [ ] Lucro acumulado em BRL e percentual
- [ ] Taxa de acerto da estratégia (% de operações lucrativas)
- [ ] Maior ganho e maior perda registrados

### 3. Relatório Fiscal
> Gerado a partir dos stats diários (item 1).

- [ ] Calcular lucro/prejuízo por operação (preço de compra vs venda)
- [ ] Calcular imposto devido (15% a 22,5% sobre ganhos acima de R$35.000/mês)
- [ ] Exportar CSV mensal organizado para declaração do IR
- [ ] Alertar via WhatsApp quando o volume mensal se aproximar do limite de isenção

### 4. Reserva em USDC

- [ ] Calcular lucro real após cada venda (preço venda - preço compra - taxas)
- [ ] Acumular lucros em BRL até atingir R$30 mínimo para conversão
- [ ] Converter 50% do lucro acumulado de BRL para USDC automaticamente
- [ ] Registrar reserva acumulada em USDC no log e no relatório fiscal
- [ ] Alertar via WhatsApp o valor convertido e reserva total em USDC

### 5. Backtesting

- [ ] Baixar dados históricos da Binance (candles SOLBRL)
- [ ] Simular a estratégia atual em dados passados
- [ ] Exibir resultado: lucro/prejuízo acumulado, drawdown máximo, % de acerto
- [ ] Comparar diferentes períodos de médias para encontrar o mais rentável

### 6. Ajuste Automático de Parâmetros
> Depende do backtesting (item 5).

- [ ] Testar combinações de períodos de médias (ex: 5/20, 7/40, 10/50)
- [ ] Testar diferentes níveis de RSI sobrecomprado/sobrevendido
- [ ] Testar diferentes percentuais de stop loss
- [ ] Selecionar automaticamente os parâmetros com melhor resultado histórico

### 7. Múltiplos Pares

- [ ] Suporte a BTCBRL e ETHBRL em paralelo com SOLBRL
- [ ] Gerenciar posição e trailing stop independente por par
- [ ] Distribuir saldo BRL entre os pares ativos
- [ ] Relatório consolidado de todos os pares

### 8. Frontend Web

- [ ] API REST em FastAPI expondo: status do bot, saldo, posição atual, histórico de operações
- [ ] Dashboard em Next.js com atualização em tempo real (WebSocket ou polling)
- [ ] Página principal: status, saldo BRL/USDC/SOL, lucro do dia e acumulado
- [ ] Gráfico de preço da SOL com marcações de compra/venda do bot
- [ ] Indicadores em tempo real: MA7, MA40, RSI, trailing stop atual
- [ ] Histórico de operações com filtro por data e par
- [ ] Relatório fiscal exportável direto pelo painel
- [ ] Autenticação simples (login/senha) para proteger o painel
- [ ] Deploy em subdomínio: `cripto.wbdigitalsolutions.com`

### 9. Deploy no Servidor 24h

- [ ] Containerizar o bot em Docker
- [ ] Docker Compose com bot + API FastAPI + frontend Next.js
- [ ] Nginx reverse proxy para `cripto.wbdigitalsolutions.com` com SSL Let's Encrypt
- [ ] Logs e stats em volume Docker persistente
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
- **Frontend stack:** FastAPI (backend) + Next.js (frontend)
- **Infraestrutura:** Docker + Nginx + Let's Encrypt no servidor Contabo existente
