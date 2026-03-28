import pandas as pd
import numpy as np
import pytest
from estrategia import calcular_rsi, verificar_stop_loss, calcular_quantidade, avaliar_sinal, verificar_lucro_minimo, atualizar_trailing_stop, verificar_trailing_stop, detectar_reversao_rsi


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
    # Simula alta moderada: alternando +2.0 / -1.5 → RSI ≈ 57, MA7 > MA40
    precos = []
    base = 400.0
    for i in range(60):
        base += 2.0 if i % 2 == 0 else -1.5
        precos.append(base)
    dados = pd.DataFrame({"fechamento": precos})
    sinal = avaliar_sinal(dados, posicao=False)
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
    # MA7 ainda abaixo da MA40 (queda), mas RSI sinalizando reversão → COMPRAR
    precos = _make_precos_queda_e_reversao()
    dados = pd.DataFrame({"fechamento": precos})
    sinal = avaliar_sinal(dados, posicao=False)
    assert sinal == "COMPRAR"
