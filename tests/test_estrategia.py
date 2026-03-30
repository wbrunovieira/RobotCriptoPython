import pandas as pd
import numpy as np
import pytest
from estrategia import (
    calcular_rsi, verificar_stop_loss, calcular_quantidade, avaliar_sinal,
    verificar_lucro_minimo, atualizar_trailing_stop, verificar_trailing_stop,
    detectar_reversao_rsi, verificar_take_profit,
    calcular_atr, stop_pct_por_atr, verificar_breakeven,
)


def _make_dados(n=60, tendencia="alta"):
    """Gera DataFrame com fechamentos simulando tendência de alta ou baixa."""
    if tendencia == "alta":
        precos = [400.0 + i * 2 for i in range(n)]
    elif tendencia == "baixa":
        precos = [500.0 - i * 2 for i in range(n)]
    else:
        precos = [450.0 + (i % 5) for i in range(n)]
    return pd.DataFrame({"fechamento": precos})


# --- RSI ---

def test_calcular_rsi_retorna_valor_entre_0_e_100():
    precos = pd.Series([400 + (i % 3) * 1.5 for i in range(30)])
    rsi = calcular_rsi(precos, periodo=14)
    assert 0 <= rsi <= 100


def test_calcular_rsi_tendencia_alta_deve_ser_alto():
    precos = pd.Series([float(i) for i in range(1, 31)])
    rsi = calcular_rsi(precos, periodo=14)
    assert rsi > 50


def test_calcular_rsi_tendencia_baixa_deve_ser_baixo():
    precos = pd.Series([float(30 - i) for i in range(30)])
    rsi = calcular_rsi(precos, periodo=14)
    assert rsi < 50


# --- Stop Loss ---

def test_stop_loss_ativado():
    assert verificar_stop_loss(preco_atual=400.0, preco_entrada=450.0, limite_pct=0.05) is True


def test_stop_loss_nao_ativado():
    assert verificar_stop_loss(preco_atual=440.0, preco_entrada=450.0, limite_pct=0.05) is False


def test_stop_loss_sem_preco_entrada():
    assert verificar_stop_loss(preco_atual=400.0, preco_entrada=None, limite_pct=0.05) is False


def test_stop_loss_no_limite_exato():
    # Exatamente no limite (427.5 = 450 * 0.95) — não deve ativar
    assert verificar_stop_loss(preco_atual=427.5, preco_entrada=450.0, limite_pct=0.05) is False


# --- Quantidade Dinâmica ---

def test_calcular_quantidade_dinamica():
    resultado = calcular_quantidade(saldo_brl=100.0, preco_atual=500.0, percentual=0.90)
    assert resultado == 0.18  # 90 / 500 = 0.18


def test_calcular_quantidade_arredondamento():
    resultado = calcular_quantidade(saldo_brl=100.0, preco_atual=300.0, percentual=0.90)
    assert resultado == 0.3  # 90 / 300 = 0.3 → 3 casas


def test_calcular_quantidade_nao_excede_saldo():
    preco = 450.0
    saldo = 59.30
    resultado = calcular_quantidade(saldo_brl=saldo, preco_atual=preco, percentual=0.90)
    assert resultado * preco <= saldo


# --- Avaliação de Sinal ---

def test_sinal_compra_tendencia_alta():
    # Alta consistente: +3.0 / -2.0 → RSI ≈ 60, separação MA9/MA21 > 0.5%
    precos = []
    base = 400.0
    for i in range(60):
        base += 3.0 if i % 2 == 0 else -2.0
        precos.append(base)
    dados = pd.DataFrame({"fechamento": precos})
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal == "COMPRAR"


def test_sinal_venda_tendencia_baixa():
    dados = _make_dados(60, tendencia="baixa")
    sinal = avaliar_sinal(dados, posicao=True)
    assert sinal == "VENDER"


def test_sem_sinal_quando_nao_comprado_e_tendencia_baixa():
    dados = _make_dados(60, tendencia="baixa")
    sinal = avaliar_sinal(dados, posicao=False)
    assert sinal is None


def test_sem_sinal_quando_comprado_e_tendencia_alta():
    dados = _make_dados(60, tendencia="alta")
    sinal = avaliar_sinal(dados, posicao=True)
    assert sinal is None


# --- Lucro Mínimo (cobertura de taxa) ---

def test_lucro_minimo_atingido():
    # Comprou a 440, vendendo a 441 → variação de 0,23% > 0,2% de taxa
    assert verificar_lucro_minimo(preco_atual=441.0, preco_entrada=440.0) is True


def test_lucro_minimo_nao_atingido():
    # Comprou a 440, vendendo a 440.5 → variação de 0,11% < 0,2% de taxa
    assert verificar_lucro_minimo(preco_atual=440.5, preco_entrada=440.0) is False


def test_lucro_minimo_prejuizo():
    # Vendendo abaixo do preço de entrada → não cobre taxa
    assert verificar_lucro_minimo(preco_atual=438.0, preco_entrada=440.0) is False


def test_lucro_minimo_sem_preco_entrada():
    # Sem preço de entrada salvo → permite vender (segurança)
    assert verificar_lucro_minimo(preco_atual=441.0, preco_entrada=None) is True


def test_lucro_minimo_exatamente_no_limite():
    # Exatamente 0,2% acima → não atingido (precisa ser estritamente maior)
    preco_entrada = 440.0
    preco_minimo = preco_entrada * 1.002  # = 440.88
    assert verificar_lucro_minimo(preco_atual=preco_minimo, preco_entrada=preco_entrada) is False


def test_lucro_minimo_taxa_customizada():
    # Taxa customizada de 0,075% (com BNB) → round trip 0,15%
    assert verificar_lucro_minimo(preco_atual=440.67, preco_entrada=440.0, taxa_pct=0.00075) is True


# --- Trailing Stop Loss ---

def test_trailing_stop_atualiza_quando_preco_sobe():
    # Preço subiu acima do máximo → max e stop devem subir
    novo_maximo, novo_stop = atualizar_trailing_stop(
        preco_atual=470.0, preco_maximo=460.0, stop_atual=437.0, stop_pct=0.05
    )
    assert novo_maximo == 470.0
    assert novo_stop == pytest.approx(470.0 * 0.95)


def test_trailing_stop_nao_atualiza_quando_preco_cai():
    # Preço caiu abaixo do máximo → max e stop permanecem
    novo_maximo, novo_stop = atualizar_trailing_stop(
        preco_atual=450.0, preco_maximo=460.0, stop_atual=437.0, stop_pct=0.05
    )
    assert novo_maximo == 460.0
    assert novo_stop == 437.0


def test_trailing_stop_nao_atualiza_quando_preco_igual_ao_maximo():
    novo_maximo, novo_stop = atualizar_trailing_stop(
        preco_atual=460.0, preco_maximo=460.0, stop_atual=437.0, stop_pct=0.05
    )
    assert novo_maximo == 460.0
    assert novo_stop == 437.0


def test_trailing_stop_inicializa_quando_sem_maximo():
    # Primeira verificação após compra: preco_maximo e stop_atual são None
    novo_maximo, novo_stop = atualizar_trailing_stop(
        preco_atual=440.0, preco_maximo=None, stop_atual=None, stop_pct=0.05
    )
    assert novo_maximo == 440.0
    assert novo_stop == pytest.approx(440.0 * 0.95)


def test_verificar_trailing_stop_ativado():
    # Preço caiu até ou abaixo do stop → deve vender
    assert verificar_trailing_stop(preco_atual=435.0, stop_price=437.0) is True


def test_verificar_trailing_stop_nao_ativado():
    # Preço ainda acima do stop → aguarda
    assert verificar_trailing_stop(preco_atual=450.0, stop_price=437.0) is False


def test_verificar_trailing_stop_sem_stop_price():
    # Stop não configurado → não dispara
    assert verificar_trailing_stop(preco_atual=435.0, stop_price=None) is False


def test_trailing_stop_sobe_conforme_preco_sobe():
    # Simula sequência de altas: stop deve subir junto
    preco_maximo, stop = None, None
    for preco in [440.0, 450.0, 460.0, 470.0]:
        preco_maximo, stop = atualizar_trailing_stop(preco, preco_maximo, stop, stop_pct=0.05)
    assert preco_maximo == 470.0
    assert stop == pytest.approx(470.0 * 0.95)


def test_trailing_stop_nao_cai_quando_preco_recua():
    # Após alta, preço recua mas stop não deve cair
    preco_maximo, stop = atualizar_trailing_stop(470.0, None, None, stop_pct=0.05)
    preco_maximo2, stop2 = atualizar_trailing_stop(455.0, preco_maximo, stop, stop_pct=0.05)
    assert stop2 == stop  # stop não recua


# --- Reversão RSI (reentrada após queda) ---

def _make_precos_queda_e_reversao():
    """Simula queda forte (RSI vai abaixo de 30) seguida de início de recuperação."""
    # 40 candles de queda forte → RSI fica sobrevendido
    precos = [500.0 - i * 4 for i in range(40)]
    # 3 candles de recuperação → RSI começa subir
    precos += [precos[-1] + i * 6 for i in range(1, 4)]
    return pd.Series(precos)


def test_detectar_reversao_rsi_subindo_de_sobrevendido():
    precos = _make_precos_queda_e_reversao()
    assert detectar_reversao_rsi(precos) is True


def test_detectar_reversao_rsi_ainda_caindo():
    # Queda contínua sem reversão → RSI sobrevendido mas ainda caindo
    precos = pd.Series([500.0 - i * 4 for i in range(43)])
    assert detectar_reversao_rsi(precos) is False


def test_detectar_reversao_rsi_zona_neutra():
    # Mercado lateral → RSI neutro, não é reversão de sobrevendido
    precos = pd.Series([450.0 + (i % 5) for i in range(43)])
    assert detectar_reversao_rsi(precos) is False


def test_detectar_reversao_rsi_dados_insuficientes():
    # Menos candles que o período mínimo → False por segurança
    precos = pd.Series([440.0] * 10)
    assert detectar_reversao_rsi(precos) is False


def test_avaliar_sinal_compra_por_reversao_rsi():
    # MA9 ainda abaixo da MA21 (queda), mas RSI sinalizando reversão → COMPRAR
    precos = _make_precos_queda_e_reversao()
    dados = pd.DataFrame({"fechamento": precos})
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal == "COMPRAR"


# --- Take-Profit ---

def test_take_profit_ativado():
    # Comprou a 100, preço chegou a 105 → +5% → ativado
    assert verificar_take_profit(preco_atual=105.0, preco_entrada=100.0, take_pct=0.05) is True


def test_take_profit_nao_ativado_abaixo_do_alvo():
    # Comprou a 100, preço está em 104 → +4% → não ativado ainda
    assert verificar_take_profit(preco_atual=104.0, preco_entrada=100.0, take_pct=0.05) is False


def test_take_profit_nao_ativado_no_limite_exato():
    # Exatamente 5% acima → não ativado (precisa ultrapassar)
    assert verificar_take_profit(preco_atual=105.0, preco_entrada=100.0, take_pct=0.05) is True


def test_take_profit_sem_preco_entrada():
    # Sem preço de entrada registrado → não ativa por segurança
    assert verificar_take_profit(preco_atual=105.0, preco_entrada=None, take_pct=0.05) is False


def test_take_profit_com_prejuizo():
    # Preço caiu abaixo da entrada → não deve ativar take-profit
    assert verificar_take_profit(preco_atual=95.0, preco_entrada=100.0, take_pct=0.05) is False


def test_take_profit_pct_customizado():
    # Take-profit de 3%: comprou a 100, preço a 103.5 → ativado
    assert verificar_take_profit(preco_atual=103.5, preco_entrada=100.0, take_pct=0.03) is True


def test_take_profit_pct_customizado_abaixo():
    # Take-profit de 3%: comprou a 100, preço a 102.9 → não ativado
    assert verificar_take_profit(preco_atual=102.9, preco_entrada=100.0, take_pct=0.03) is False


def test_take_profit_btc_valores_reais():
    # BTC comprado a R$350.000, alvo de +5% = R$367.500
    assert verificar_take_profit(preco_atual=367_500.0, preco_entrada=350_000.0, take_pct=0.05) is True
    assert verificar_take_profit(preco_atual=360_000.0, preco_entrada=350_000.0, take_pct=0.05) is False


# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 30, tendencia: float = 0.5, volatilidade: float = 5.0) -> pd.DataFrame:
    """Gera DataFrame OHLCV determinístico. tendencia = ganho por candle."""
    fechamentos = [400.0 + i * tendencia for i in range(n)]
    return pd.DataFrame({
        "fechamento": fechamentos,
        "maxima":    [f + volatilidade for f in fechamentos],
        "minima":    [f - volatilidade for f in fechamentos],
    })


def _make_dados_alta_forte(n: int = 60) -> pd.DataFrame:
    """Alta com oscilação: MA9>MA21 (sep>0.5%), preço>MA50, RSI 55-65, MA50 subindo."""
    precos = []
    base = 400.0
    for i in range(n):
        # +3.0 / -2.0 alternado → net +0.5/candle, RSI ≈ 60
        base += 3.0 if i % 2 == 0 else -2.0
        precos.append(base)
    return pd.DataFrame({
        "fechamento": precos,
        "maxima":    [p + 5.0 for p in precos],
        "minima":    [p - 5.0 for p in precos],
    })


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def test_calcular_atr_retorna_positivo():
    dados = _make_ohlcv(30, volatilidade=5.0)
    assert calcular_atr(dados) > 0


def test_calcular_atr_maior_volatilidade_gera_maior_atr():
    baixa = _make_ohlcv(30, volatilidade=2.0)
    alta  = _make_ohlcv(30, volatilidade=10.0)
    assert calcular_atr(alta) > calcular_atr(baixa)


def test_calcular_atr_dados_insuficientes_retorna_zero():
    dados = _make_ohlcv(5)
    assert calcular_atr(dados, periodo=14) == 0.0


def test_calcular_atr_sem_colunas_ohlcv_retorna_zero():
    # Só tem fechamento (sem maxima/minima) → retorna 0
    dados = pd.DataFrame({"fechamento": [400.0 + i for i in range(20)]})
    assert calcular_atr(dados) == 0.0


# ---------------------------------------------------------------------------
# Stop dinâmico por ATR
# ---------------------------------------------------------------------------

def test_stop_pct_por_atr_nunca_abaixo_do_minimo():
    # Mesmo com baixa volatilidade, stop não cai abaixo de stop_pct_min
    dados = _make_ohlcv(30, volatilidade=0.1)  # quase sem range
    resultado = stop_pct_por_atr(dados, stop_pct_min=0.015)
    assert resultado >= 0.015


def test_stop_pct_por_atr_maior_para_ativo_mais_volatil():
    baixa = _make_ohlcv(30, tendencia=0.5, volatilidade=2.0)
    alta  = _make_ohlcv(30, tendencia=0.5, volatilidade=20.0)
    assert stop_pct_por_atr(alta) > stop_pct_por_atr(baixa)


def test_stop_pct_por_atr_sem_ohlcv_retorna_minimo():
    # Sem colunas maxima/minima → fallback para stop mínimo
    dados = pd.DataFrame({"fechamento": [400.0 + i for i in range(20)]})
    assert stop_pct_por_atr(dados, stop_pct_min=0.015) == 0.015


def test_stop_pct_por_atr_retorna_float():
    dados = _make_ohlcv(30)
    assert isinstance(stop_pct_por_atr(dados), float)


# ---------------------------------------------------------------------------
# Break-even automático
# ---------------------------------------------------------------------------

def test_breakeven_ativa_quando_lucro_atinge_threshold():
    # Entrada 100, preço 115.5 (+1.5%) → move stop para 100.10 (entrada + 0.1%)
    novo_stop = verificar_breakeven(
        preco_atual=101.6, preco_entrada=100.0, stop_price=98.5,
        ativacao_pct=0.015, margem_pct=0.001,
    )
    assert novo_stop == pytest.approx(100.0 * 1.001)


def test_breakeven_nao_ativa_quando_lucro_insuficiente():
    # Preço apenas +1% — ainda não atingiu os 1.5%
    novo_stop = verificar_breakeven(
        preco_atual=101.0, preco_entrada=100.0, stop_price=98.5,
        ativacao_pct=0.015,
    )
    assert novo_stop is None


def test_breakeven_nao_ativa_quando_stop_ja_acima_da_entrada():
    # Stop já está acima da entrada → break-even já foi ativado antes
    novo_stop = verificar_breakeven(
        preco_atual=103.0, preco_entrada=100.0, stop_price=100.2,
        ativacao_pct=0.015, margem_pct=0.001,
    )
    assert novo_stop is None


def test_breakeven_sem_preco_entrada_retorna_none():
    novo_stop = verificar_breakeven(
        preco_atual=105.0, preco_entrada=None, stop_price=98.0,
    )
    assert novo_stop is None


def test_breakeven_sem_stop_price_retorna_none():
    novo_stop = verificar_breakeven(
        preco_atual=105.0, preco_entrada=100.0, stop_price=None,
    )
    assert novo_stop is None


def test_breakeven_valores_reais_btc():
    # BTC entrada R$351.168, subiu para R$357k (+1.7%), stop em R$334k
    novo_stop = verificar_breakeven(
        preco_atual=357_000.0, preco_entrada=351_168.0, stop_price=334_000.0,
        ativacao_pct=0.015, margem_pct=0.001,
    )
    assert novo_stop == pytest.approx(351_168.0 * 1.001)


# ---------------------------------------------------------------------------
# Filtro de separação mínima do crossover
# ---------------------------------------------------------------------------

def test_sinal_bloqueado_crossover_fraco():
    """MA9 apenas 0.2% acima da MA21 → separação insuficiente, não deve comprar."""
    # Gera série quase flat com leve tendência → separação MA9/MA21 < 0.5%
    n = 60
    base = 440.0
    precos = []
    for i in range(n):
        # Oscila em banda estreita, net +0.08/candle → separação < 0.3%
        base += 0.08 if i % 2 == 0 else -0.06
        precos.append(base)
    dados = pd.DataFrame({
        "fechamento": precos,
        "maxima":    [p + 1.0 for p in precos],
        "minima":    [p - 1.0 for p in precos],
    })
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal is None


def test_sinal_permitido_crossover_forte():
    """MA9 claramente acima da MA21 (> 0.5%) → deve comprar."""
    dados = _make_dados_alta_forte(60)
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal == "COMPRAR"


# ---------------------------------------------------------------------------
# Filtro slope da MA50
# ---------------------------------------------------------------------------

def test_sinal_bloqueado_ma50_caindo():
    """MA50 em queda forte → não deve entrar mesmo com crossover válido."""
    # Cria série que começa alto e cai — MA50 vai estar caindo no final
    n = 60
    # Primeira metade: tendência de alta (para criar MA50 alta)
    # Segunda metade: lateraliza/cai levemente enquanto MA9/MA21 ainda cruzam para cima brevemente
    # A chave: MA50 calculada na janela vai incluir muitos candles altos → slope negativo
    precos = [500.0 - i * 1.5 for i in range(n)]  # queda constante: MA50 em queda
    # Adiciona micro-bounce no final para ter MA9 > MA21 mas MA50 ainda caindo
    precos[-10:] = [precos[-11] + j * 1.0 for j in range(10)]
    dados = pd.DataFrame({
        "fechamento": precos,
        "maxima":    [p + 5.0 for p in precos],
        "minima":    [p - 5.0 for p in precos],
    })
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal is None


def test_sinal_permitido_ma50_subindo():
    """MA50 em alta consistente → filtro slope não bloqueia."""
    dados = _make_dados_alta_forte(60)
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal == "COMPRAR"


# ---------------------------------------------------------------------------
# Filtro MA50: aplicado ao crossover mas NÃO à reversão RSI
# ---------------------------------------------------------------------------

def test_reversao_rsi_nao_bloqueada_por_filtro_regime():
    """RSI reversal é sinal counter-trend — não deve ser bloqueado por MA50.
    Com 43 candles a MA50 não é calculada (< 50), garantindo que RSI reversal passe.
    """
    precos = [500.0 - i * 4 for i in range(40)]
    precos += [precos[-1] + i * 6 for i in range(1, 4)]
    dados = pd.DataFrame({"fechamento": precos})
    segunda_manha = pd.Timestamp("2026-03-30 10:00:00", tz="America/Sao_Paulo")
    sinal = avaliar_sinal(dados, posicao=False, agora=segunda_manha)
    assert sinal == "COMPRAR"
