"""Configuração centralizada do bot Meme (USDT)."""
import os

BOT_ID = os.getenv("MEME_BOT_ID", "MemeCoin1")
PERIODO_CANDLE = "15m"
CANDLES_HISTORICO = 200
INTERVALO_SCANNER_S = int(os.getenv("MEME_INTERVALO_S", "900"))

CAPITAL_USDT = float(os.getenv("MEME_CAPITAL_USDT", "100.0"))
PERCENTUAL_COMPRA = 0.80

TAKE_PROFIT_PCT = float(os.getenv("MEME_TAKE_PROFIT_PCT", "0.05"))
STOP_PCT_MIN = float(os.getenv("MEME_STOP_PCT_MIN", "0.03"))
ATR_MULTIPLICADOR = float(os.getenv("MEME_ATR_MULT", "3.5"))
BREAKEVEN_GATILHO = 0.025
BREAKEVEN_FOLGA = 0.001

SCORE_MINIMO = int(os.getenv("MEME_SCORE_MINIMO", "7"))
SEP_MA_MINIMA_PCT = 0.5
RSI_MIN = 50
RSI_MAX = 65
RSI_SOBREVENDIDO = 30
ADX_MINIMO = 20
VOLUME_MULTIPLICADOR = 2.0

STOP_PORTFOLIO_PCT = float(os.getenv("MEME_STOP_PORTFOLIO_PCT", "0.08"))
LIMITE_DIARIO_PCT = float(os.getenv("MEME_LIMITE_DIARIO_PCT", "0.05"))
MAX_POSICOES = 1
MAX_TENTATIVAS = 3

MEME_UNIVERSE = [
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT",
    "BONKUSDT", "FLOKIUSDT", "PNUTUSDT", "TRUMPUSDT",
    "NEIROUSDT", "MEMEUSDT", "ACTUSDT", "BOMEUSDT",
]

POSICAO_FILE = "posicoes/posicao_meme.json"
STATS_DIR = "stats_meme"
APORTES_FILE = "stats_meme/aportes.json"
RESERVA_FILE = "stats_meme/reserva_meme.json"
BLOQUEIO_FILE = "run/bloqueio_meme.json"
STATUS_FILE = "run/status_meme.json"
LOG_FILE = "logs/log_operacoes_meme.txt"
