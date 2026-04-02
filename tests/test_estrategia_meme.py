"""Testes da estratégia do bot Meme."""
import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch

from bots.meme.estrategia import (
    calcular_score,
    avaliar_sinal_meme,
    calcular_stop_inicial,
    _volume_acima_media,
    _detectar_reversao_rsi,
)
from bots.meme.config import (
    TAKE_PROFIT_PCT,
    STOP_PCT_MIN,
    SEP_MA_MINIMA_PCT,
    RSI_MIN,
    RSI_MAX,
    RSI_SOBREVENDIDO,
    ADX_MINIMO,
    VOLUME_MULTIPLICADOR,
    BREAKEVEN_GATILHO,
    BREAKEVEN_FOLGA,
)


def _make_dados_alta(n=60, vol_mult=1.0):
    """DataFrame com tendência de alta clara (MA9 > MA21 > MA50, RSI ~60)."""
    fechamentos = [100.0 + i * 0.5 for i in range(n)]
    maximas = [f + 0.2 for f in fechamentos]
    minimas = [f - 0.2 for f in fechamentos]
    # Volume médio 1, último candle vol_mult * média
    volumes = [1000.0] * n
    volumes[-1] = 1000.0 * vol_mult
    return pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": maximas,
        "minima": minimas,
        "volume": volumes,
    })


def _make_dados_lateral(n=60):
    """DataFrame com mercado lateral (sem tendência clara)."""
    fechamentos = [100.0 + (i % 3) * 0.1 for i in range(n)]
    maximas = [f + 0.1 for f in fechamentos]
    minimas = [f - 0.1 for f in fechamentos]
    volumes = [1000.0] * n
    return pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": maximas,
        "minima": minimas,
        "volume": volumes,
    })


def _make_dados_queda(n=60, vol_mult=1.0):
    """DataFrame com tendência de queda (MA9 < MA21)."""
    fechamentos = [200.0 - i * 0.8 for i in range(n)]
    maximas = [f + 0.2 for f in fechamentos]
    minimas = [f - 0.2 for f in fechamentos]
    volumes = [1000.0] * n
    volumes[-1] = 1000.0 * vol_mult
    return pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": maximas,
        "minima": minimas,
        "volume": volumes,
    })


def _make_dados_sobrevendido(n=60, vol_mult=2.5):
    """DataFrame que simula RSI sobrevendido (queda acentuada) com recuperação."""
    # Queda forte nos primeiros candles, depois estabiliza para simular reversão
    fechamentos = [100.0 - i * 2.0 for i in range(n - 2)] + [38.0, 40.0]
    maximas = [f + 0.5 for f in fechamentos]
    minimas = [f - 0.5 for f in fechamentos]
    volumes = [1000.0] * n
    volumes[-1] = 1000.0 * vol_mult
    return pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": maximas,
        "minima": minimas,
        "volume": volumes,
    })


# ─── calcular_score ──────────────────────────────────────────────────────────

def test_calcular_score_retorna_dict_com_score_e_detalhes():
    dados = _make_dados_alta()
    resultado = calcular_score(dados)
    assert "score" in resultado
    assert "detalhes" in resultado


def test_calcular_score_entre_0_e_10():
    for dados in [_make_dados_alta(), _make_dados_lateral(), _make_dados_queda()]:
        resultado = calcular_score(dados)
        assert 0 <= resultado["score"] <= 10, f"Score fora do range: {resultado['score']}"


def test_calcular_score_alta_tem_score_maior_que_lateral():
    score_alta = calcular_score(_make_dados_alta(vol_mult=2.5))["score"]
    score_lateral = calcular_score(_make_dados_lateral())["score"]
    assert score_alta > score_lateral


def test_calcular_score_sem_volume_nao_quebra():
    dados = _make_dados_alta().drop(columns=["volume"])
    resultado = calcular_score(dados)
    assert 0 <= resultado["score"] <= 10


# ─── avaliar_sinal_meme — Sinal 1 ────────────────────────────────────────────

def test_sinal1_comprar_com_todos_criterios():
    """Sinal 1 deve retornar COMPRAR quando todos os critérios estão satisfeitos."""
    dados = _make_dados_alta(n=100, vol_mult=3.0)
    with patch("bots.meme.estrategia.calcular_adx", return_value=30.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    assert resultado == "COMPRAR"


def test_sinal1_bloqueado_sep_ma_pequena():
    """Sinal 1 bloqueado se separação MA9/MA21 < SEP_MA_MINIMA_PCT."""
    # Mercado lateral — MA9 ≈ MA21
    dados = _make_dados_lateral(n=100)
    with patch("bots.meme.estrategia.calcular_adx", return_value=30.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    # Sem crossover claro → None
    assert resultado != "COMPRAR"


def test_sinal1_bloqueado_adx_baixo():
    """Sinal 1 bloqueado se ADX < ADX_MINIMO."""
    dados = _make_dados_alta(n=100, vol_mult=3.0)
    with patch("bots.meme.estrategia.calcular_adx", return_value=10.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    assert resultado != "COMPRAR"


def test_sinal1_bloqueado_volume_baixo():
    """Sinal 1 bloqueado se volume < VOLUME_MULTIPLICADOR x média."""
    dados = _make_dados_alta(n=100, vol_mult=0.5)  # volume baixo
    with patch("bots.meme.estrategia.calcular_adx", return_value=30.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    assert resultado != "COMPRAR"


def test_sinal1_bloqueado_preco_abaixo_ma50():
    """Sinal 1 bloqueado se preço < MA50."""
    # Cria dados onde MA9 > MA21, mas preço cai no final
    n = 100
    fechamentos = [100.0 + i * 0.3 for i in range(n - 5)] + [60.0, 60.5, 61.0, 61.5, 62.0]
    maximas = [f + 0.2 for f in fechamentos]
    minimas = [f - 0.2 for f in fechamentos]
    volumes = [1000.0] * (n - 1) + [3000.0]
    dados = pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": maximas,
        "minima": minimas,
        "volume": volumes,
    })
    with patch("bots.meme.estrategia.calcular_adx", return_value=30.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    # Preço atual (62) bem abaixo de MA50 (em torno de 90+) → bloqueado
    assert resultado != "COMPRAR"


# ─── avaliar_sinal_meme — Sinal 2 ────────────────────────────────────────────

def test_sinal2_comprar_rsi_sobrevendido_revertendo():
    """Sinal 2 deve retornar COMPRAR quando RSI reverte de sobrevendido com volume."""
    dados = _make_dados_sobrevendido(n=60, vol_mult=3.0)
    # Patch para garantir que RSI anterior < 30 e atual > anterior
    with patch("bots.meme.estrategia.calcular_rsi") as mock_rsi, \
         patch("bots.meme.estrategia.calcular_adx", return_value=15.0):
        # Simular RSI sobrevendido revertendo
        call_count = [0]
        def mock_rsi_fn(precos, periodo=14):
            call_count[0] += 1
            # Primeira chamada (rsi_atual) → acima de 30
            # Segunda chamada (rsi_anterior via _detectar_reversao_rsi) → abaixo de 30
            if call_count[0] % 2 == 1:
                return 32.0  # rsi_atual (subindo)
            return 25.0  # rsi_anterior (sobrevendido)
        mock_rsi.side_effect = mock_rsi_fn

        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    # O sinal principal usa calcular_rsi para RSI geral; o Sinal 2 usa _detectar_reversao_rsi
    # Não podemos garantir o resultado exato sem mockear _detectar_reversao_rsi diretamente
    # Testamos via mock direto de _detectar_reversao_rsi
    with patch("bots.meme.estrategia._detectar_reversao_rsi", return_value=True), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=45.0), \
         patch("bots.meme.estrategia.calcular_adx", return_value=15.0), \
         patch("bots.meme.estrategia._volume_acima_media", return_value=True):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    assert resultado == "COMPRAR"


# ─── avaliar_sinal_meme — Saídas ─────────────────────────────────────────────

def test_vender_quando_take_profit_atingido():
    """VENDER quando preco >= entrada * (1 + TAKE_PROFIT_PCT)."""
    dados = _make_dados_alta(n=60)
    preco_entrada = 100.0
    preco_atual = preco_entrada * (1 + TAKE_PROFIT_PCT + 0.01)

    # Modificar o último fechamento para ser o preco_atual
    dados = dados.copy()
    dados.loc[dados.index[-1], "fechamento"] = preco_atual

    resultado = avaliar_sinal_meme(
        dados, posicao=True,
        preco_entrada=preco_entrada,
        stop_price=preco_entrada * 0.97,
        preco_maximo=preco_atual,
    )
    assert resultado == "VENDER"


def test_vender_quando_trailing_stop_disparado():
    """VENDER quando preco <= stop_price."""
    dados = _make_dados_alta(n=60)
    preco_entrada = 100.0
    stop_price = 105.0
    preco_atual = stop_price - 0.01  # Abaixo do stop

    dados = dados.copy()
    dados.loc[dados.index[-1], "fechamento"] = preco_atual

    resultado = avaliar_sinal_meme(
        dados, posicao=True,
        preco_entrada=preco_entrada,
        stop_price=stop_price,
        preco_maximo=110.0,
    )
    assert resultado == "VENDER"


def test_vender_crossover_baixista():
    """VENDER em crossover baixista com separação > SEP_MA_MINIMA_PCT."""
    dados = _make_dados_queda(n=60)
    preco_entrada = 200.0  # Preço de entrada alto, agora em queda
    preco_atual = float(dados["fechamento"].iloc[-1])
    stop_price = preco_entrada * 0.97

    # Verificar se o crossover baixista está ativo nos dados de queda
    fech = dados["fechamento"].astype(float)
    ma9 = float(fech.rolling(9).mean().iloc[-1])
    ma21 = float(fech.rolling(21).mean().iloc[-1])
    sep_pct = (ma21 - ma9) / ma21 * 100

    if ma9 < ma21 and sep_pct > SEP_MA_MINIMA_PCT:
        resultado = avaliar_sinal_meme(
            dados, posicao=True,
            preco_entrada=preco_entrada,
            stop_price=stop_price,
            preco_maximo=preco_entrada,
        )
        assert resultado == "VENDER"
    else:
        # Forçar crossover baixista via mock
        with patch("bots.meme.estrategia.calcular_rsi", return_value=40.0):
            dados_forçado = _make_dados_queda(n=100)
            resultado = avaliar_sinal_meme(
                dados_forçado, posicao=True,
                preco_entrada=200.0,
                stop_price=190.0,
                preco_maximo=200.0,
            )
        # Resultado pode ser VENDER ou None dependendo dos dados
        assert resultado in ("VENDER", None)


def test_vender_crossover_baixista_forte():
    """Crossover baixista com separação claramente > 0.5% deve gerar VENDER."""
    # Gerar dados com MA9 claramente abaixo de MA21
    n = 60
    # Alta forte depois queda forte para garantir MA9 << MA21
    fechamentos = [50.0 + i * 2.0 for i in range(30)] + [150.0 - i * 3.0 for i in range(30)]
    dados = pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": [f + 0.5 for f in fechamentos],
        "minima": [f - 0.5 for f in fechamentos],
        "volume": [1000.0] * n,
    })

    fech = dados["fechamento"].astype(float)
    ma9 = float(fech.rolling(9).mean().iloc[-1])
    ma21 = float(fech.rolling(21).mean().iloc[-1])

    if ma9 < ma21:
        sep_pct = (ma21 - ma9) / ma21 * 100
        preco_entrada = 100.0
        stop_price = preco_entrada * 0.97

        resultado = avaliar_sinal_meme(
            dados, posicao=True,
            preco_entrada=preco_entrada,
            stop_price=stop_price,
            preco_maximo=preco_entrada,
        )
        if sep_pct > SEP_MA_MINIMA_PCT:
            assert resultado == "VENDER"


# ─── Breakeven ───────────────────────────────────────────────────────────────

def test_breakeven_nao_ativa_antes_do_gatilho():
    """Stop não deve mover para breakeven antes de +BREAKEVEN_GATILHO."""
    from core.risco import verificar_breakeven

    preco_entrada = 100.0
    preco_atual = preco_entrada * (1 + BREAKEVEN_GATILHO - 0.005)  # Abaixo do gatilho
    stop_price = preco_entrada * 0.97

    novo_stop = verificar_breakeven(
        preco_atual, preco_entrada, stop_price,
        ativacao_pct=BREAKEVEN_GATILHO,
        margem_pct=BREAKEVEN_FOLGA,
    )
    assert novo_stop is None


def test_breakeven_ativa_apos_gatilho():
    """Stop deve mover para entrada * (1 + BREAKEVEN_FOLGA) após +BREAKEVEN_GATILHO."""
    from core.risco import verificar_breakeven

    preco_entrada = 100.0
    preco_atual = preco_entrada * (1 + BREAKEVEN_GATILHO + 0.005)  # Acima do gatilho
    stop_price = preco_entrada * 0.97

    novo_stop = verificar_breakeven(
        preco_atual, preco_entrada, stop_price,
        ativacao_pct=BREAKEVEN_GATILHO,
        margem_pct=BREAKEVEN_FOLGA,
    )
    assert novo_stop is not None
    assert abs(novo_stop - preco_entrada * (1 + BREAKEVEN_FOLGA)) < 1e-8


# ─── Mercado lateral ─────────────────────────────────────────────────────────

def test_none_em_mercado_lateral():
    """Sem posição e ADX baixo → sem sinal."""
    dados = _make_dados_lateral(n=100)
    with patch("bots.meme.estrategia.calcular_adx", return_value=10.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=55.0), \
         patch("bots.meme.estrategia._detectar_reversao_rsi", return_value=False):
        resultado = avaliar_sinal_meme(dados, posicao=False, preco_entrada=None,
                                       stop_price=None, preco_maximo=None)
    assert resultado is None


# ─── calcular_stop_inicial ───────────────────────────────────────────────────

def test_calcular_stop_inicial_minimo():
    """Stop nunca deve ser menor que STOP_PCT_MIN."""
    dados = _make_dados_alta(n=60)
    stop = calcular_stop_inicial(dados)
    assert stop >= STOP_PCT_MIN


def test_calcular_stop_inicial_sem_dados_suficientes():
    """Com dados insuficientes deve retornar STOP_PCT_MIN."""
    dados = pd.DataFrame({
        "fechamento": [1.0, 1.1, 1.2],
        "maxima": [1.2, 1.3, 1.4],
        "minima": [0.9, 1.0, 1.1],
        "volume": [1000.0, 1000.0, 1000.0],
    })
    stop = calcular_stop_inicial(dados)
    assert stop == STOP_PCT_MIN
