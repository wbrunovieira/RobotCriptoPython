import pandas as pd
import numpy as np
import pytest
from estrategia import calcular_rsi, verificar_stop_loss, calcular_quantidade, avaliar_sinal


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
    assert resultado == 0.18


def test_calcular_quantidade_arredondamento():
    resultado = calcular_quantidade(saldo_brl=100.0, preco_atual=300.0, percentual=0.90)
    assert resultado == 0.3


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
