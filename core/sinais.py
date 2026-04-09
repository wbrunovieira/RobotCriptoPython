"""Lógica de sinais de entrada e saída.

Avaliação de mercado e decisões de trading — sem I/O, sem Binance.
"""
import logging

import pandas as pd
from core.indicadores import calcular_rsi, calcular_adx

logger = logging.getLogger(__name__)

# Parâmetros do Sinal 1 (MA crossover)
_MIN_CROSSOVER_SEPARATION_PCT = 0.5   # % mínimo de separação MA9/MA21 para compra
_REENTRADA_SEP_MIN_PCT        = 0.2   # % mínimo de separação em modo reentrada
_VENDA_SEP_MIN_PCT            = 0.3   # % mínimo de separação para confirmar sinal de venda
_MA50_SLOPE_MAX_QUEDA_PCT     = -0.2  # % queda da MA50 em 3 candles para bloquear entrada
_ADX_TENDENCIA_MIN            = 20    # ADX mínimo para confirmar tendência

# Parâmetros de volume
_VOL_MULTIPLICADOR_NORMAL     = 1.0   # filtro de volume em dias úteis
_VOL_MULTIPLICADOR_FDS        = 1.5   # filtro de volume em fim de semana


def detectar_reversao_rsi(
    precos: pd.Series,
    periodo: int = 14,
    limite_sobrevendido: int = 30,
) -> bool:
    """Retorna True se o RSI estava abaixo do limite sobrevendido e começou a subir.
    Sinal de reentrada após queda brusca — detecta o início da recuperação."""
    if len(precos) < periodo + 2:
        return False
    rsi_atual = calcular_rsi(precos, periodo)
    rsi_anterior = calcular_rsi(precos.iloc[:-1], periodo)
    return rsi_anterior < limite_sobrevendido and rsi_atual > rsi_anterior


def calcular_quantidade(saldo_brl: float, preco_atual: float, percentual: float = 0.90) -> float:
    """Calcula a quantidade de ativo a comprar com base no saldo disponível."""
    return round((saldo_brl * percentual) / preco_atual, 3)


def _volume_acima_media(dados: pd.DataFrame, periodos: int = 20, multiplicador: float = 1.0) -> bool:
    """Retorna True se o volume do último candle está acima de `multiplicador` vezes a média.

    multiplicador=1.0 — comportamento padrão (dias úteis)
    multiplicador=1.5 — fim de semana: exige volume 50% acima da média
    """
    if "volume" not in dados.columns or len(dados) < periodos + 1:
        return True  # sem dados de volume, não bloqueia
    vol = dados["volume"].astype(float)
    return float(vol.iloc[-1]) > float(vol.rolling(periodos).mean().iloc[-1]) * multiplicador


def _horario_permitido(agora: pd.Timestamp = None) -> bool:
    """Retorna False no período de fim de semana (sexta 18h → segunda 09h, horário SP).
    Usado para detectar janela de baixa liquidez — não bloqueia mais, apenas sinaliza
    para que o filtro de volume seja mais rigoroso (1.5x em vez de 1.0x).
    """
    if agora is None:
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
    dia = agora.dayofweek  # 0=seg, 4=sex, 5=sab, 6=dom
    hora = agora.hour
    if dia == 4 and hora >= 18:   # sexta após 18h
        return False
    if dia == 5:                   # sábado
        return False
    if dia == 6:                   # domingo
        return False
    if dia == 0 and hora < 9:     # segunda antes das 9h
        return False
    return True


def _quinta_feira_bloqueada(agora: pd.Timestamp = None) -> bool:
    """Retorna True se hoje é quinta-feira e o bloqueio está ativo.

    Padrão observado nas últimas 5 semanas (mar–abr 2026):
    80% das quintas-feiras registraram queda média de -2% a -4% (todos os pares BRL),
    atribuída à incerteza geopolítica Trump/Irã — vendas preventivas antes do fim de semana.
    """
    if agora is None:
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
    return agora.dayofweek == 3  # 3 = quinta-feira


def btc_acima_ma50(dados_btc: pd.DataFrame) -> bool:
    """Retorna True se o BTC está acima da MA50 de 4h — tendência global de alta.

    Em caso de dados insuficientes ou erro, retorna True para não bloquear operações
    por falha de conectividade.
    """
    if dados_btc.empty or len(dados_btc) < 50:
        return True
    fechamento = dados_btc["fechamento"].astype(float)
    ma50 = fechamento.rolling(window=50).mean().iloc[-1]
    return bool(float(fechamento.iloc[-1]) > ma50)


def avaliar_sinal(
    dados: pd.DataFrame,
    posicao: bool,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
    pares_abertos: int = 0,
    max_posicoes: int = 2,
    agora: pd.Timestamp = None,
    reentrada: bool = False,
    bloqueio_quinta: bool = False,
) -> str | None:
    """Avalia o sinal de compra ou venda com base em médias móveis e RSI.

    Sinal 1 — Crossover MA9/MA21 (trend-following):
      - MA9 > MA21, RSI 50–70, volume ok
      - Filtros: preço > MA50, MA50 não caindo, separação mínima do crossover

    Sinal 2 — Reversão RSI sobrevendido (counter-trend):
      - RSI estava abaixo de 30 e começou a subir
      - Sem filtros de regime (por design — é entrada contra-tendência)
    """
    fechamento = dados["fechamento"].astype(float)

    media_rapida = fechamento.rolling(window=9).mean().iloc[-1]
    media_devagar = fechamento.rolling(window=21).mean().iloc[-1]
    rsi = calcular_rsi(fechamento, periodo=14)

    logger.debug("Média Rápida (9): %.4f | Média Devagar (21): %.4f | RSI: %.2f",
                 media_rapida, media_devagar, rsi)

    if posicao:
        if media_rapida < media_devagar:
            separacao_venda_pct = (media_devagar - media_rapida) / media_devagar * 100
            if separacao_venda_pct < _VENDA_SEP_MIN_PCT:
                logger.info("Filtro de saída: crossover fraco (%.2f%% < %.1f%%). Aguardando trailing stop.",
                            separacao_venda_pct, _VENDA_SEP_MIN_PCT)
                return None
            return "VENDER"
        return None

    # Filtros comuns a todos os sinais de compra
    if pares_abertos >= max_posicoes:
        logger.info("Filtro: %d/%d posições abertas. Entrada bloqueada.", pares_abertos, max_posicoes)
        return None

    # Quinta-feira: bloqueia novas entradas (padrão de queda ~80% das quintas, mar-abr 2026)
    if bloqueio_quinta and _quinta_feira_bloqueada(agora):
        logger.info("Filtro quinta-feira: novas compras bloqueadas (BOT_BLOQUEIO_QUINTA_FEIRA=true).")
        return None

    # Fim de semana: permite entrada, mas exige volume 1.5x acima da média
    fim_de_semana = not _horario_permitido(agora)
    vol_multiplicador = _VOL_MULTIPLICADOR_FDS if fim_de_semana else _VOL_MULTIPLICADOR_NORMAL
    if fim_de_semana:
        logger.warning("Fim de semana — volume mínimo elevado para %.1fx da média.", _VOL_MULTIPLICADOR_FDS)

    # --- Sinal 1: Crossover MA9 > MA21 (trend-following) ---
    if media_rapida > media_devagar and 50 < rsi < rsi_sobrecomprado:
        if len(fechamento) >= 50:
            ma50_series = fechamento.rolling(window=50).mean()
            ma50 = ma50_series.iloc[-1]
            preco_atual_val = float(fechamento.iloc[-1])
            if preco_atual_val < ma50:
                logger.info("Filtro de regime: preço (%.2f) abaixo da MA50 (%.2f). Entrada bloqueada.",
                            preco_atual_val, ma50)
                return None
            if not reentrada and len(fechamento) >= 53:
                ma50_3h_atras = ma50_series.iloc[-4]
                slope_pct = (ma50 - ma50_3h_atras) / ma50_3h_atras * 100
                if slope_pct < _MA50_SLOPE_MAX_QUEDA_PCT:
                    logger.info("Filtro: MA50 caindo (%.2f%%). Entrada bloqueada.", slope_pct)
                    return None
        limiar_separacao = _REENTRADA_SEP_MIN_PCT if reentrada else _MIN_CROSSOVER_SEPARATION_PCT
        separacao_pct = (media_rapida - media_devagar) / media_devagar * 100
        if separacao_pct < limiar_separacao:
            logger.info("Filtro: crossover fraco (%.2f%% < %.1f%%). Entrada bloqueada.",
                        separacao_pct, limiar_separacao)
            return None
        if not _volume_acima_media(dados, multiplicador=vol_multiplicador):
            logger.info("Filtro: volume abaixo de %.1fx da média. Entrada bloqueada.", vol_multiplicador)
            return None
        adx = calcular_adx(dados)
        if adx < _ADX_TENDENCIA_MIN:
            logger.info("Filtro: mercado lateral (ADX=%.1f < %d). Entrada Signal 1 bloqueada.",
                        adx, _ADX_TENDENCIA_MIN)
            return None
        logger.info("ADX=%.1f — tendência confirmada.", adx)
        return "COMPRAR"

    # --- Sinal 2: Reversão RSI sobrevendido (counter-trend) ---
    if detectar_reversao_rsi(fechamento, periodo=14, limite_sobrevendido=rsi_sobrevendido):
        if not _volume_acima_media(dados, multiplicador=vol_multiplicador):
            logger.info("Filtro: volume abaixo de %.1fx da média (reversão RSI). Entrada bloqueada.",
                        vol_multiplicador)
            return None
        logger.info("Sinal de reversão RSI detectado (RSI subindo de sobrevendido).")
        return "COMPRAR"

    return None
