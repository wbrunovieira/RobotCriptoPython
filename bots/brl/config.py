"""Configuração do bot BRL — lida via variáveis de ambiente."""
import os

BOT_ID = os.getenv("BOT_ID", "MACross1")
PERIODO_CANDLE = os.getenv("BOT_PERIODO_CANDLE", "1h")
STOP_PCT = float(os.getenv("BOT_STOP_PCT", "0.015"))
TAKE_PROFIT_PCT = float(os.getenv("BOT_TAKE_PROFIT_PCT", "0.02"))
TETO_SALDO_PCT = float(os.getenv("BOT_TETO_SALDO_PCT", "0.60"))
MAX_POSICOES = int(os.getenv("BOT_MAX_POSICOES", "3"))
PERCENTUAL_COMPRA = 0.90
STOP_PORTFOLIO_PCT = float(os.getenv("BOT_STOP_PORTFOLIO_PCT", "0.05"))
BLOQUEIO_PORTFOLIO_FILE = "run/bloqueio_portfolio.json"
BLOQUEIO_QUINTA_FEIRA = os.getenv("BOT_BLOQUEIO_QUINTA_FEIRA", "true").lower() == "true"
BLOQUEIO_QUARTA_DOMINGO = os.getenv("BOT_BLOQUEIO_QUARTA_DOMINGO", "true").lower() == "true"
COOLDOWN_STOP_HORAS = int(os.getenv("BOT_COOLDOWN_STOP_HORAS", "5"))
FILTRO_TENDENCIA_BTC = os.getenv("BOT_FILTRO_TENDENCIA_BTC", "true").lower() == "true"
MAX_TENTATIVAS = 3
INTERVALO_MONITORAMENTO = int(os.getenv("BOT_INTERVALO_MONITORAMENTO", "60"))
_intervalo_estrategia_min = int(os.getenv("BOT_INTERVALO_ESTRATEGIA_MIN", "15"))
INTERVALO_ESTRATEGIA = _intervalo_estrategia_min * 60
