"""Testes de configuração do bot Meme."""
import pytest
from bots.meme.config import (
    BOT_ID,
    PERIODO_CANDLE,
    CANDLES_HISTORICO,
    INTERVALO_SCANNER_S,
    CAPITAL_USDT,
    PERCENTUAL_COMPRA,
    TAKE_PROFIT_PCT,
    STOP_PCT_MIN,
    ATR_MULTIPLICADOR,
    BREAKEVEN_GATILHO,
    BREAKEVEN_FOLGA,
    SCORE_MINIMO,
    SEP_MA_MINIMA_PCT,
    RSI_MIN,
    RSI_MAX,
    RSI_SOBREVENDIDO,
    ADX_MINIMO,
    VOLUME_MULTIPLICADOR,
    STOP_PORTFOLIO_PCT,
    LIMITE_DIARIO_PCT,
    MAX_POSICOES,
    MAX_TENTATIVAS,
    MEME_UNIVERSE,
    POSICAO_FILE,
    STATS_DIR,
    APORTES_FILE,
    RESERVA_FILE,
    BLOQUEIO_FILE,
    STATUS_FILE,
    LOG_FILE,
)


def test_bot_id_e_string():
    assert isinstance(BOT_ID, str)
    assert len(BOT_ID) > 0


def test_periodo_candle_valido():
    assert isinstance(PERIODO_CANDLE, str)
    assert PERIODO_CANDLE in ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d")


def test_candles_historico_positivo():
    assert isinstance(CANDLES_HISTORICO, int)
    assert CANDLES_HISTORICO > 0


def test_intervalo_scanner_positivo():
    assert isinstance(INTERVALO_SCANNER_S, int)
    assert INTERVALO_SCANNER_S > 0


def test_capital_usdt_positivo():
    assert isinstance(CAPITAL_USDT, float)
    assert CAPITAL_USDT > 0


def test_percentual_compra_range():
    assert isinstance(PERCENTUAL_COMPRA, float)
    assert 0 < PERCENTUAL_COMPRA <= 0.95


def test_take_profit_maior_que_stop():
    assert TAKE_PROFIT_PCT > STOP_PCT_MIN


def test_take_profit_pct_range():
    assert isinstance(TAKE_PROFIT_PCT, float)
    assert 0 < TAKE_PROFIT_PCT < 1.0


def test_stop_pct_min_range():
    assert isinstance(STOP_PCT_MIN, float)
    assert 0 < STOP_PCT_MIN < 1.0


def test_atr_multiplicador_maior_que_1():
    assert isinstance(ATR_MULTIPLICADOR, float)
    assert ATR_MULTIPLICADOR > 1.0


def test_breakeven_gatilho_positivo():
    assert isinstance(BREAKEVEN_GATILHO, float)
    assert BREAKEVEN_GATILHO > 0


def test_breakeven_folga_positiva():
    assert isinstance(BREAKEVEN_FOLGA, float)
    assert BREAKEVEN_FOLGA > 0


def test_score_minimo_range():
    assert isinstance(SCORE_MINIMO, int)
    assert 5 <= SCORE_MINIMO <= 10


def test_rsi_min_menor_que_rsi_max():
    assert RSI_MIN < RSI_MAX


def test_rsi_sobrevendido_menor_que_rsi_min():
    assert RSI_SOBREVENDIDO < RSI_MIN


def test_adx_minimo_positivo():
    assert isinstance(ADX_MINIMO, (int, float))
    assert ADX_MINIMO > 0


def test_volume_multiplicador_maior_que_1():
    assert isinstance(VOLUME_MULTIPLICADOR, float)
    assert VOLUME_MULTIPLICADOR > 1.0


def test_stop_portfolio_pct_range():
    assert isinstance(STOP_PORTFOLIO_PCT, float)
    assert 0 < STOP_PORTFOLIO_PCT < 1.0


def test_limite_diario_pct_range():
    assert isinstance(LIMITE_DIARIO_PCT, float)
    assert 0 < LIMITE_DIARIO_PCT < 1.0


def test_max_posicoes_positivo():
    assert isinstance(MAX_POSICOES, int)
    assert MAX_POSICOES >= 1


def test_max_tentativas_positivo():
    assert isinstance(MAX_TENTATIVAS, int)
    assert MAX_TENTATIVAS >= 1


def test_meme_universe_nao_vazio():
    assert isinstance(MEME_UNIVERSE, list)
    assert len(MEME_UNIVERSE) > 0


def test_meme_universe_todos_strings_usdt():
    for simbolo in MEME_UNIVERSE:
        assert isinstance(simbolo, str), f"{simbolo} não é string"
        assert simbolo.endswith("USDT"), f"{simbolo} não termina em USDT"


def test_arquivos_sao_strings():
    for path in (POSICAO_FILE, STATS_DIR, APORTES_FILE, RESERVA_FILE, BLOQUEIO_FILE, STATUS_FILE, LOG_FILE):
        assert isinstance(path, str)
        assert len(path) > 0
