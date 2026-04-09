"""Detecção algorítmica de padrões gráficos.

Funções puras — sem I/O, sem Binance.
Complementa core/sinais.py com sinais de entrada antecipada (pré-crossover MA).

Padrões implementados:
  - Cunha descendente (falling wedge): reversão de alta em fundos de mercado
  - Bandeira de alta (bull flag): continuação de alta após impulso

Uso:
    from core.padroes import detectar_padrao_entrada
    padrao = detectar_padrao_entrada(dados)  # "cunha_descendente" | "bandeira_alta" | None
"""
import numpy as np
import pandas as pd


def _regredir(values: np.ndarray) -> tuple[float, float]:
    """Regressão linear nos valores originais. Retorna (slope, intercept)."""
    n = len(values)
    if n < 2:
        return 0.0, float(values[0]) if n == 1 else 0.0
    slope, intercept = np.polyfit(np.arange(n, dtype=float), values, 1)
    return float(slope), float(intercept)


def _slope_rel(slope: float, values: np.ndarray) -> float:
    """Normaliza slope pelo preço médio → adimensional (% por candle)."""
    base = float(np.mean(values))
    return slope / base if base > 0 else 0.0


def detectar_cunha_descendente(dados: pd.DataFrame, janela: int = 40) -> bool:
    """Cunha descendente (falling wedge) — reversão de alta.

    Padrão típico de fundo após queda forte. Ambas as linhas de tendência
    (resistência e suporte) caem, mas o suporte cai menos — comprimindo o range.
    Sinal de entrada: fechamento acima ou muito próximo da linha de resistência.

    Critérios:
    1. Resistência (linha dos topos) com slope negativo
    2. Suporte (linha dos fundos) com slope negativo, mas MENOS inclinado
    3. Diferença de slopes (convergência) acima do limiar mínimo
    4. Fechamento atual >= 98.5% do nível de resistência (breakout iminente)
    """
    if len(dados) < janela:
        return False

    trecho = dados.tail(janela)
    maximas = trecho["maxima"].astype(float).values
    minimas = trecho["minima"].astype(float).values
    n = len(maximas)

    slope_max, icept_max = _regredir(maximas)
    slope_min, _ = _regredir(minimas)

    sr_max = _slope_rel(slope_max, maximas)
    sr_min = _slope_rel(slope_min, minimas)

    # Ambas as linhas devem estar caindo (slope relativo negativo)
    if sr_max >= -0.0001 or sr_min >= -0.0001:
        return False

    # Suporte cai menos que resistência → convergência das linhas
    if sr_min <= sr_max:
        return False

    # Convergência deve ser significativa (não apenas ruído)
    if (sr_min - sr_max) < 0.0003:
        return False

    # Fechamento acima ou próximo da linha de resistência (breakout)
    resist_nivel = slope_max * (n - 1) + icept_max
    fechamento = float(dados["fechamento"].iloc[-1])
    return fechamento >= resist_nivel * 0.985


def detectar_bandeira_alta(
    dados: pd.DataFrame,
    janela_pole: int = 15,
    janela_flag: int = 20,
    impulso_min_pct: float = 5.0,
) -> bool:
    """Bandeira de alta (bull flag) — continuação de tendência.

    Pole: impulso forte (alta rápida) antes da consolidação.
    Flag: canal paralelo levemente descendente (pausa/correção).
    Sinal de entrada: fechamento acima da linha de topo do canal.

    Critérios:
    1. Impulso >= impulso_min_pct% nos janela_pole candles antes da flag
    2. Canal da flag com slope levemente negativo ou neutro (não subindo)
    3. Slopes do topo e do fundo do canal são próximos (canal paralelo)
    4. Fechamento atual acima da linha de topo do canal
    """
    min_candles = janela_pole + janela_flag
    if len(dados) < min_candles:
        return False

    fechamentos = dados["fechamento"].astype(float)

    # Detecta o pole: alta forte antes da flag
    p_inicio = float(fechamentos.iloc[-(janela_pole + janela_flag)])
    p_fim = float(fechamentos.iloc[-janela_flag])
    if p_inicio <= 0:
        return False

    impulso_pct = (p_fim - p_inicio) / p_inicio * 100
    if impulso_pct < impulso_min_pct:
        return False

    # Analisa o canal da flag
    flag = dados.tail(janela_flag)
    maximas_f = flag["maxima"].astype(float).values
    minimas_f = flag["minima"].astype(float).values
    n = len(maximas_f)

    slope_topo, icept_topo = _regredir(maximas_f)
    slope_fundo, _ = _regredir(minimas_f)

    sr_topo = _slope_rel(slope_topo, maximas_f)
    sr_fundo = _slope_rel(slope_fundo, minimas_f)

    # Canal não pode estar subindo (seria um novo impulso, não consolidação)
    if sr_topo > 0.0003:
        return False

    # Canal paralelo: slopes do topo e fundo devem ser próximos
    if abs(sr_topo - sr_fundo) > 0.002:
        return False

    # Breakout: fechamento acima da linha de topo do canal
    nivel_topo = slope_topo * (n - 1) + icept_topo
    return float(fechamentos.iloc[-1]) > nivel_topo


def detectar_padrao_entrada(dados: pd.DataFrame) -> str | None:
    """Verifica se há padrão de entrada ativo nos dados.

    Retorna o nome do padrão detectado ou None.
    Prioridade: cunha_descendente > bandeira_alta.
    """
    if detectar_cunha_descendente(dados):
        return "cunha_descendente"
    if detectar_bandeira_alta(dados):
        return "bandeira_alta"
    return None
