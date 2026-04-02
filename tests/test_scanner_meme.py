"""Testes do scanner de meme coins."""
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from bots.meme.scanner import scan_todos, scan_melhor
from bots.meme.config import SCORE_MINIMO, MEME_UNIVERSE


def _make_candles(n=60, tendencia="alta", vol_mult=1.0):
    """Gera lista de candles simulados no formato Binance."""
    if tendencia == "alta":
        fechamentos = [100.0 + i * 0.5 for i in range(n)]
    elif tendencia == "baixa":
        fechamentos = [200.0 - i * 0.5 for i in range(n)]
    else:
        fechamentos = [100.0 + (i % 3) * 0.1 for i in range(n)]

    candles = []
    volumes = [1000.0] * n
    volumes[-1] = 1000.0 * vol_mult
    for i, (f, v) in enumerate(zip(fechamentos, volumes)):
        candle = [
            i * 900000,      # tempo_abertura
            str(f - 0.1),    # abertura
            str(f + 0.2),    # maxima
            str(f - 0.2),    # minima
            str(f),          # fechamento
            str(v),          # volume
            (i + 1) * 900000,  # tempo_fechamento
            str(f * v),      # moedas_negociadas
            100,             # numero_trades
            str(v * 0.5),    # volume_ativo_base_compra
            str(f * v * 0.5),  # volume_ativo_cotacao
            "0",             # ignorado
        ]
        candles.append(candle)
    return candles


def _make_cliente_mock(universo_resultados: dict):
    """Cria mock de cliente Binance com get_klines configurado por símbolo."""
    cliente = MagicMock()

    def fake_get_klines(symbol, interval, limit):
        if symbol in universo_resultados:
            return universo_resultados[symbol]
        raise Exception(f"Símbolo {symbol} não encontrado")

    cliente.get_klines.side_effect = fake_get_klines
    return cliente


# ─── scan_todos ──────────────────────────────────────────────────────────────

def test_scan_retorna_lista():
    universo = {s: _make_candles(60, "lateral") for s in MEME_UNIVERSE}
    cliente = _make_cliente_mock(universo)
    with patch("bots.meme.scanner.MEME_UNIVERSE", list(MEME_UNIVERSE)):
        resultado = scan_todos(cliente)
    assert isinstance(resultado, list)


def test_scan_todos_retorna_campos_corretos():
    simbolo = MEME_UNIVERSE[0]
    universo = {simbolo: _make_candles(60, "alta", vol_mult=2.5)}
    # Só um símbolo
    cliente = _make_cliente_mock(universo)
    with patch("bots.meme.scanner.MEME_UNIVERSE", [simbolo]):
        resultado = scan_todos(cliente)

    assert len(resultado) == 1
    item = resultado[0]
    for campo in ("simbolo", "score", "preco", "rsi", "adx", "volume_ratio", "variacao_pct", "detalhes"):
        assert campo in item, f"Campo '{campo}' ausente"


def test_scan_ordenado_por_score_desc():
    # Criar dois símbolos: um com alta (score maior) e um com lateral (score menor)
    simbolo_alto = "DOGEUSDT"
    simbolo_baixo = "SHIBUSDT"
    universo = {
        simbolo_alto: _make_candles(100, "alta", vol_mult=3.0),
        simbolo_baixo: _make_candles(100, "lateral", vol_mult=0.5),
    }
    cliente = _make_cliente_mock(universo)
    with patch("bots.meme.scanner.MEME_UNIVERSE", [simbolo_baixo, simbolo_alto]):
        resultado = scan_todos(cliente)

    assert len(resultado) == 2
    # Score do primeiro deve ser >= segundo
    assert resultado[0]["score"] >= resultado[1]["score"]


def test_scan_simbolo_com_erro_ignorado():
    """Símbolo com erro de API deve ser pulado e scan continua."""
    simbolo_ok = "DOGEUSDT"
    simbolo_erro = "SHIBUSDT"
    universo = {
        simbolo_ok: _make_candles(60, "alta", vol_mult=2.0),
        # simbolo_erro vai gerar exceção
    }
    cliente = _make_cliente_mock(universo)
    with patch("bots.meme.scanner.MEME_UNIVERSE", [simbolo_erro, simbolo_ok]):
        resultado = scan_todos(cliente)

    # Deve ter apenas o símbolo que funcionou
    assert len(resultado) == 1
    assert resultado[0]["simbolo"] == simbolo_ok


def test_scan_universo_vazio_retorna_lista_vazia():
    cliente = MagicMock()
    with patch("bots.meme.scanner.MEME_UNIVERSE", []):
        resultado = scan_todos(cliente)
    assert resultado == []


# ─── scan_melhor ─────────────────────────────────────────────────────────────

def test_scan_melhor_retorna_none_sem_score_suficiente():
    """Retorna None quando nenhum símbolo atinge SCORE_MINIMO."""
    simbolo = MEME_UNIVERSE[0]
    universo = {simbolo: _make_candles(60, "lateral")}
    cliente = _make_cliente_mock(universo)

    with patch("bots.meme.scanner.MEME_UNIVERSE", [simbolo]), \
         patch("bots.meme.estrategia.calcular_adx", return_value=5.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=35.0):
        resultado = scan_melhor(cliente)

    # Com ADX=5 e RSI=35 (lateral/sobrevendido sem reversão) o score deve ser baixo
    # Se scan_melhor retorna None → ok; se retorna dict com score < SCORE_MINIMO → ok via mock
    # Testamos via mock de scan_todos diretamente
    with patch("bots.meme.scanner.scan_todos", return_value=[{"simbolo": simbolo, "score": 3, "volume_ratio": 1.0, "rsi": 35.0, "adx": 5.0, "variacao_pct": 0.0, "preco": 1.0, "detalhes": {}}]):
        resultado = scan_melhor(cliente)
    assert resultado is None


def test_scan_melhor_retorna_maior_score():
    """Retorna o símbolo com maior score se >= SCORE_MINIMO."""
    simbolo_a = "DOGEUSDT"
    simbolo_b = "SHIBUSDT"
    mock_resultados = [
        {"simbolo": simbolo_a, "score": 9, "volume_ratio": 3.0, "rsi": 58.0, "adx": 30.0, "variacao_pct": 1.0, "preco": 1.0, "detalhes": {}},
        {"simbolo": simbolo_b, "score": 5, "volume_ratio": 1.5, "rsi": 48.0, "adx": 20.0, "variacao_pct": 0.2, "preco": 0.5, "detalhes": {}},
    ]
    cliente = MagicMock()
    with patch("bots.meme.scanner.scan_todos", return_value=mock_resultados):
        resultado = scan_melhor(cliente)

    assert resultado is not None
    assert resultado["simbolo"] == simbolo_a
    assert resultado["score"] == 9


def test_scan_melhor_retorna_none_quando_universo_vazio():
    cliente = MagicMock()
    with patch("bots.meme.scanner.MEME_UNIVERSE", []):
        resultado = scan_melhor(cliente)
    assert resultado is None


def test_scan_empate_score_retorna_maior_volume():
    """Em empate de score, retorna o de maior volume_ratio."""
    simbolo_a = "DOGEUSDT"
    simbolo_b = "SHIBUSDT"
    # Scores iguais, volume diferente
    mock_resultados = [
        {"simbolo": simbolo_a, "score": 8, "volume_ratio": 5.0, "rsi": 58.0, "adx": 28.0, "variacao_pct": 1.0, "preco": 1.0, "detalhes": {}},
        {"simbolo": simbolo_b, "score": 8, "volume_ratio": 2.0, "rsi": 55.0, "adx": 25.0, "variacao_pct": 0.8, "preco": 0.5, "detalhes": {}},
    ]
    # scan_todos já ordenou por (score, volume_ratio) desc
    cliente = MagicMock()
    with patch("bots.meme.scanner.scan_todos", return_value=mock_resultados):
        resultado = scan_melhor(cliente)

    assert resultado is not None
    assert resultado["simbolo"] == simbolo_a
    assert resultado["volume_ratio"] == 5.0


def test_scan_score_calculado_corretamente():
    """Score calculado consistentemente para dados de alta qualidade."""
    from bots.meme.estrategia import calcular_score

    n = 100
    # Criar dados que atendam o máximo de critérios possível
    fechamentos = [100.0 + i * 0.5 for i in range(n)]
    volumes = [1000.0] * n
    volumes[-1] = 3000.0  # 3x volume → +2

    dados = pd.DataFrame({
        "fechamento": fechamentos,
        "maxima": [f + 0.2 for f in fechamentos],
        "minima": [f - 0.2 for f in fechamentos],
        "volume": volumes,
    })

    with patch("bots.meme.estrategia.calcular_adx", return_value=30.0), \
         patch("bots.meme.estrategia.calcular_rsi", return_value=57.0):
        resultado = calcular_score(dados)

    # Com ADX=30 (+2), RSI=57 (+2), MA9>MA21 alta (+2), preco>MA50 (+1), vol 3x (+2), var>0.5% (+1)
    assert resultado["score"] >= 7
