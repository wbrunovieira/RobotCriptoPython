"""Regras de proteção de capital e gestão de risco.

Funções puras — sem I/O, sem Binance.
Reutilizáveis por qualquer bot.
"""
import pandas as pd
from core.indicadores import calcular_atr


def stop_pct_por_atr(
    dados: pd.DataFrame,
    stop_pct_min: float = 0.015,
    multiplicador: float = 2.2,
    periodo: int = 14,
) -> float:
    """Retorna o percentual de stop baseado no ATR do ativo.

    stop = max(stop_pct_min, ATR_pct * multiplicador)
    Garante que o stop nunca seja menor que stop_pct_min.
    """
    atr = calcular_atr(dados, periodo)
    if atr == 0.0:
        return stop_pct_min
    preco = float(dados["fechamento"].iloc[-1])
    if preco == 0:
        return stop_pct_min
    atr_pct = atr / preco
    return max(stop_pct_min, atr_pct * multiplicador)


def verificar_breakeven(
    preco_atual: float,
    preco_entrada: float,
    stop_price: float,
    ativacao_pct: float = 0.015,
    margem_pct: float = 0.001,
) -> float | None:
    """Retorna o novo stop de break-even quando o lucro atinge `ativacao_pct`.

    Move o stop para preco_entrada * (1 + margem_pct) — eliminando risco de perda.
    Retorna None se:
    - preco_entrada ou stop_price forem None
    - o lucro ainda não atingiu o threshold
    - o stop já está acima do nível de break-even (já foi ativado)
    """
    if preco_entrada is None or stop_price is None:
        return None
    nivel_breakeven = preco_entrada * (1 + margem_pct)
    if stop_price >= nivel_breakeven:
        return None  # já está em break-even ou melhor
    if preco_atual >= preco_entrada * (1 + ativacao_pct):
        return nivel_breakeven
    return None


def verificar_stop_loss(preco_atual: float, preco_entrada: float, limite_pct: float = 0.05) -> bool:
    """Retorna True se o preço caiu mais do que limite_pct em relação ao preço de entrada."""
    if preco_entrada is None:
        return False
    return preco_atual < preco_entrada * (1 - limite_pct)


def atualizar_trailing_stop(
    preco_atual: float,
    preco_maximo: float,
    stop_atual: float,
    stop_pct: float = 0.015,
) -> tuple:
    """Atualiza o trailing stop conforme o preço sobe.
    Se o preço superar o máximo histórico, sobe o stop junto.
    O stop nunca recua — só avança quando o preço bate novo topo."""
    if preco_maximo is None or preco_atual > preco_maximo:
        novo_maximo = preco_atual
        novo_stop = preco_atual * (1 - stop_pct)
        return novo_maximo, novo_stop
    return preco_maximo, stop_atual


def verificar_trailing_stop(preco_atual: float, stop_price: float) -> bool:
    """Retorna True se o preço caiu até ou abaixo do trailing stop."""
    if stop_price is None:
        return False
    return preco_atual <= stop_price


def verificar_take_profit(preco_atual: float, preco_entrada: float, take_pct: float = 0.03) -> bool:
    """Retorna True se o preço atingiu ou superou o alvo de lucro take_pct acima do preço de entrada."""
    if preco_entrada is None:
        return False
    return preco_atual >= preco_entrada * (1 + take_pct)


def verificar_lucro_minimo(preco_atual: float, preco_entrada: float, taxa_pct: float = 0.001) -> bool:
    """Retorna True se o lucro cobre as taxas de compra + venda (round trip = 2 * taxa_pct).
    Se preco_entrada for None, permite a venda por segurança."""
    if preco_entrada is None:
        return True
    return preco_atual > preco_entrada * (1 + 2 * taxa_pct)
