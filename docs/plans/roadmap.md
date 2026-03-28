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

### 1. Relatório Fiscal
- [ ] Calcular lucro/prejuízo por operação (preço de compra vs venda)
- [ ] Calcular imposto devido (15% a 22,5% sobre ganhos acima de R$35.000/mês)
- [ ] Exportar CSV mensal organizado para declaração do IR
- [ ] Alertar via WhatsApp quando o volume mensal se aproximar do limite de isenção

### 2. Dashboard no Terminal
- [ ] Exibir resumo do dia ao iniciar: saldo inicial vs atual
- [ ] Total de operações realizadas no dia/mês
- [ ] Lucro acumulado em BRL e percentual
- [ ] Taxa de acerto da estratégia (% de operações lucrativas)
- [ ] Maior ganho e maior perda registrados

### 3. Backtesting
- [ ] Baixar dados históricos da Binance (candles SOLBRL)
- [ ] Simular a estratégia atual em dados passados
- [ ] Exibir resultado: lucro/prejuízo acumulado, drawdown máximo, % de acerto
- [ ] Comparar diferentes períodos de médias para encontrar o mais rentável

### 4. Múltiplos Pares
- [ ] Suporte a BTCBRL e ETHBRL em paralelo com SOLBRL
- [ ] Gerenciar posição e trailing stop independente por par
- [ ] Distribuir saldo BRL entre os pares ativos
- [ ] Relatório consolidado de todos os pares

### 5. Ajuste Automático de Parâmetros
- [ ] Testar combinações de períodos de médias via backtesting (ex: 5/20, 7/40, 10/50)
- [ ] Testar diferentes níveis de RSI sobrecomprado/sobrevendido
- [ ] Testar diferentes percentuais de stop loss
- [ ] Selecionar automaticamente os parâmetros com melhor resultado histórico
