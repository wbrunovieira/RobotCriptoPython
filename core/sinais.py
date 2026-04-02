"""Lógica de sinais de entrada e saída.

Avaliação de mercado e decisões de trading — sem I/O, sem Binance.
"""
import pandas as pd
from core.indicadores import calcular_rsi, calcular_adx

_MIN_CROSSOVER_SEPARATION_PCT = 0.5   # % mínimo de separação MA9/MA21
_MA50_SLOPE_MAX_QUEDA_PCT     = -0.2  # % queda da MA50 em 3 candles para bloquear


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


def contar_posicoes_abertas(pares: list) -> int:
    """Conta quantos pares estão com posição aberta no momento."""
    from infra.persistencia import carregar_posicao
    from pares import arquivo_posicao
    abertas = 0
    for par in pares:
        estado = carregar_posicao(arquivo=arquivo_posicao(par["simbolo"]))
        if estado.get("posicao"):
            abertas += 1
    return abertas


def avaliar_sinal(
    dados: pd.DataFrame,
    posicao: bool,
    rsi_sobrecomprado: int = 70,
    rsi_sobrevendido: int = 30,
    pares_abertos: int = 0,
    max_posicoes: int = 2,
    agora: pd.Timestamp = None,
    reentrada: bool = False,
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

    print(f"Média Rápida (9): {media_rapida:.4f} | Média Devagar (21): {media_devagar:.4f} | RSI: {rsi:.2f}")

    if posicao:
        if media_rapida < media_devagar:
            separacao_venda_pct = (media_devagar - media_rapida) / media_devagar * 100
            if separacao_venda_pct < 0.3:
                print(f"Filtro de saída: crossover fraco ({separacao_venda_pct:.2f}% < 0.3%). Aguardando trailing stop.")
                return None
            return "VENDER"
        return None

    # Filtros comuns a todos os sinais de compra
    if pares_abertos >= max_posicoes:
        print(f"Filtro: {pares_abertos}/{max_posicoes} posições abertas. Entrada bloqueada.")
        return None

    # Fim de semana: permite entrada, mas exige volume 1.5x acima da média
    fim_de_semana = not _horario_permitido(agora)
    vol_multiplicador = 1.5 if fim_de_semana else 1.0
    if fim_de_semana:
        print("Aviso: fim de semana — volume mínimo elevado para 1.5x da média.")

    # --- Sinal 1: Crossover MA9 > MA21 (trend-following) ---
    if media_rapida > media_devagar and 50 < rsi < rsi_sobrecomprado:
        if len(fechamento) >= 50:
            ma50_series = fechamento.rolling(window=50).mean()
            ma50 = ma50_series.iloc[-1]
            preco_atual_val = float(fechamento.iloc[-1])
            if preco_atual_val < ma50:
                print(f"Filtro de regime: preço ({preco_atual_val:.2f}) abaixo da MA50 ({ma50:.2f}). Entrada bloqueada.")
                return None
            if not reentrada and len(fechamento) >= 53:
                ma50_3h_atras = ma50_series.iloc[-4]
                slope_pct = (ma50 - ma50_3h_atras) / ma50_3h_atras * 100
                if slope_pct < _MA50_SLOPE_MAX_QUEDA_PCT:
                    print(f"Filtro: MA50 caindo ({slope_pct:.2f}%). Entrada bloqueada.")
                    return None
        limiar_separacao = 0.2 if reentrada else _MIN_CROSSOVER_SEPARATION_PCT
        separacao_pct = (media_rapida - media_devagar) / media_devagar * 100
        if separacao_pct < limiar_separacao:
            print(f"Filtro: crossover fraco ({separacao_pct:.2f}% < {limiar_separacao}%). Entrada bloqueada.")
            return None
        if not _volume_acima_media(dados, multiplicador=vol_multiplicador):
            print(f"Filtro: volume abaixo de {vol_multiplicador}x da média. Entrada bloqueada.")
            return None
        adx = calcular_adx(dados)
        if adx < 20:
            print(f"Filtro: mercado lateral (ADX={adx:.1f} < 20). Entrada Signal 1 bloqueada.")
            return None
        print(f"ADX={adx:.1f} — tendência confirmada.")
        return "COMPRAR"

    # --- Sinal 2: Reversão RSI sobrevendido (counter-trend) ---
    if detectar_reversao_rsi(fechamento, periodo=14, limite_sobrevendido=rsi_sobrevendido):
        if not _volume_acima_media(dados, multiplicador=vol_multiplicador):
            print(f"Filtro: volume abaixo de {vol_multiplicador}x da média (reversão RSI). Entrada bloqueada.")
            return None
        print("Sinal de reversao RSI detectado (RSI subindo de sobrevendido)")
        return "COMPRAR"

    return None
