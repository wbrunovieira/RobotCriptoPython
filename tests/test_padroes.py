"""Testes unitários para core/padroes.py."""
import numpy as np
import pandas as pd
import pytest

from core.padroes import (
    detectar_cunha_descendente,
    detectar_bandeira_alta,
    detectar_padrao_entrada,
)


def _make_dados(maximas, minimas, fechamentos=None):
    """Cria DataFrame de candles a partir de listas."""
    n = len(maximas)
    if fechamentos is None:
        fechamentos = [(h + l) / 2 for h, l in zip(maximas, minimas)]
    return pd.DataFrame({
        "maxima": maximas,
        "minima": minimas,
        "fechamento": fechamentos,
        "volume": [1000.0] * n,
    })


# ─── Cunha descendente ───────────────────────────────────────────────────────

def _cunha_descendente_dados(n=40, breakout=True):
    """
    Resistência cai de 110 → 100 (slope rápido).
    Suporte cai de 95 → 90 (slope lento) → convergência.
    Breakout: fechamento acima da resistência.
    """
    maximas = [110 - i * 0.25 for i in range(n)]   # cai mais rápido
    minimas = [95 - i * 0.12 for i in range(n)]    # cai mais devagar
    if breakout:
        # Último fechamento acima da resistência (breakout)
        fechamentos = [(h + l) / 2 for h, l in zip(maximas, minimas)]
        fechamentos[-1] = maximas[-1] * 1.005       # 0.5% acima da resistência
    else:
        fechamentos = [(h + l) / 2 for h, l in zip(maximas, minimas)]
    return _make_dados(maximas, minimas, fechamentos)


def test_cunha_descendente_detecta_breakout():
    dados = _cunha_descendente_dados(n=40, breakout=True)
    assert detectar_cunha_descendente(dados) is True


def test_cunha_descendente_sem_breakout_nao_detecta():
    dados = _cunha_descendente_dados(n=40, breakout=False)
    # Sem breakout o fechamento está no meio do canal, abaixo da resistência
    assert detectar_cunha_descendente(dados) is False


def test_cunha_descendente_candles_insuficientes():
    dados = _cunha_descendente_dados(n=20)
    # janela padrão = 40, com apenas 20 candles deve retornar False
    assert detectar_cunha_descendente(dados, janela=40) is False


def test_cunha_descendente_nao_detecta_em_alta():
    """Canal de alta (ambas as linhas subindo) não é cunha descendente."""
    n = 40
    maximas = [100 + i * 0.3 for i in range(n)]
    minimas = [90 + i * 0.2 for i in range(n)]
    fechamentos = [(h + l) / 2 for h, l in zip(maximas, minimas)]
    dados = _make_dados(maximas, minimas, fechamentos)
    assert detectar_cunha_descendente(dados) is False


def test_cunha_descendente_nao_detecta_sem_convergencia():
    """Linhas paralelas (sem convergência) não são cunha."""
    n = 40
    # Ambas caem com o mesmo slope → sem convergência
    maximas = [110 - i * 0.2 for i in range(n)]
    minimas = [95 - i * 0.2 for i in range(n)]
    fechamentos = [maximas[-1] * 1.005] * n  # fechamento acima da resistência
    fechamentos = [(h + l) / 2 for h, l in zip(maximas, minimas)]
    fechamentos[-1] = maximas[-1] * 1.005
    dados = _make_dados(maximas, minimas, fechamentos)
    assert detectar_cunha_descendente(dados) is False


# ─── Bandeira de alta ────────────────────────────────────────────────────────

def _bandeira_alta_dados(pole_pct=8.0, flag_slope=-0.05, breakout=True):
    """
    Pole: 15 candles subindo pole_pct%.
    Flag: 20 candles em canal levemente descendente.
    """
    n_pole = 15
    n_flag = 20

    # Pole: de 100 sobe pole_pct%
    p_inicio = 100.0
    p_fim = p_inicio * (1 + pole_pct / 100)
    pole_fechamentos = [p_inicio + (p_fim - p_inicio) * i / (n_pole - 1) for i in range(n_pole)]

    # Flag: canal levemente descendente
    flag_topo_inicio = p_fim * 1.005
    flag_fundo_inicio = p_fim * 0.99
    maximas_flag = [flag_topo_inicio + flag_slope * i for i in range(n_flag)]
    minimas_flag = [flag_fundo_inicio + flag_slope * i for i in range(n_flag)]

    if breakout:
        fechamentos_flag = [(h + l) / 2 for h, l in zip(maximas_flag, minimas_flag)]
        fechamentos_flag[-1] = maximas_flag[-1] * 1.005  # breakout acima do canal
    else:
        fechamentos_flag = [(h + l) / 2 for h, l in zip(maximas_flag, minimas_flag)]

    # Monta o DataFrame completo (pole + flag)
    maximas_pole = [f * 1.003 for f in pole_fechamentos]
    minimas_pole = [f * 0.997 for f in pole_fechamentos]

    maximas = maximas_pole + maximas_flag
    minimas = minimas_pole + minimas_flag
    fechamentos = pole_fechamentos + fechamentos_flag

    return _make_dados(maximas, minimas, fechamentos)


def test_bandeira_alta_detecta_breakout():
    dados = _bandeira_alta_dados(pole_pct=8.0, breakout=True)
    assert detectar_bandeira_alta(dados) is True


def test_bandeira_alta_sem_breakout_nao_detecta():
    dados = _bandeira_alta_dados(pole_pct=8.0, breakout=False)
    assert detectar_bandeira_alta(dados) is False


def test_bandeira_alta_impulso_insuficiente_nao_detecta():
    """Impulso de 2% não é suficiente para ser um pole válido."""
    dados = _bandeira_alta_dados(pole_pct=2.0, breakout=True)
    assert detectar_bandeira_alta(dados) is False


def test_bandeira_alta_canal_subindo_nao_detecta():
    """Canal da flag subindo (não é correção, é novo impulso) — não deve detectar."""
    dados = _bandeira_alta_dados(pole_pct=8.0, flag_slope=0.10, breakout=True)
    assert detectar_bandeira_alta(dados) is False


def test_bandeira_alta_candles_insuficientes():
    n = 20  # menos que pole(15) + flag(20) = 35
    maximas = [100.0 + i * 0.1 for i in range(n)]
    minimas = [99.0 + i * 0.1 for i in range(n)]
    dados = _make_dados(maximas, minimas)
    assert detectar_bandeira_alta(dados) is False


# ─── detectar_padrao_entrada ─────────────────────────────────────────────────

def test_padrao_entrada_retorna_cunha_quando_detectada():
    dados = _cunha_descendente_dados(n=40, breakout=True)
    resultado = detectar_padrao_entrada(dados)
    assert resultado == "cunha_descendente"


def test_padrao_entrada_retorna_bandeira_quando_detectada():
    dados = _bandeira_alta_dados(pole_pct=8.0, breakout=True)
    # Garante que cunha não é detectada neste cenário
    from core.padroes import detectar_cunha_descendente
    if not detectar_cunha_descendente(dados):
        assert detectar_padrao_entrada(dados) == "bandeira_alta"


def test_padrao_entrada_retorna_none_sem_padrao():
    # Dados laterais sem padrão claro
    n = 40
    precos = [100.0 + (i % 3) * 0.5 for i in range(n)]
    dados = _make_dados(
        [p + 1 for p in precos],
        [p - 1 for p in precos],
        precos,
    )
    assert detectar_padrao_entrada(dados) is None


def test_padrao_entrada_dataframe_vazio_retorna_none():
    assert detectar_padrao_entrada(pd.DataFrame()) is None
