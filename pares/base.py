"""Utilitários de universo de pares — agnósticos de moeda base."""
from infra.persistencia import carregar_posicao

TETO_PCT_PADRAO = 0.60


def arquivo_posicao(simbolo: str) -> str:
    """Retorna o caminho do arquivo de estado de posição para o par."""
    return f"posicoes/posicao_{simbolo}.json"


def calcular_saldo_disponivel(saldo_brl: float, teto_pct: float = TETO_PCT_PADRAO) -> float:
    """Retorna o máximo que um par pode usar (teto_pct do saldo disponível)."""
    return round(saldo_brl * teto_pct, 2)


def pares_sem_posicao(estados: dict) -> list:
    """Retorna lista de símbolos que não têm posição aberta.

    estados = {"SOLBRL": {"posicao": True}, "BTCBRL": {"posicao": False}, ...}
    """
    return [simbolo for simbolo, estado in estados.items() if not estado.get("posicao")]


def contar_posicoes_abertas(pares: list) -> int:
    """Conta quantos pares estão com posição aberta no momento."""
    return sum(
        1 for par in pares
        if carregar_posicao(arquivo=arquivo_posicao(par["simbolo"])).get("posicao")
    )


def consolidar_resumo(resumos: list) -> dict:
    """Agrega métricas de múltiplos pares em um resumo consolidado."""
    if not resumos:
        return {
            "total_operacoes": 0,
            "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0,
            "taxa_acerto_pct": 0.0,
            "por_par": {},
        }

    total_ops = sum(r.get("total_operacoes", 0) for r in resumos)
    lucrativas = sum(r.get("operacoes_lucrativas", 0) for r in resumos)
    lucro_total = round(sum(r.get("lucro_total_brl", 0.0) for r in resumos), 2)
    taxa_acerto = round(lucrativas / total_ops * 100, 1) if total_ops > 0 else 0.0

    return {
        "total_operacoes": total_ops,
        "operacoes_lucrativas": lucrativas,
        "lucro_total_brl": lucro_total,
        "taxa_acerto_pct": taxa_acerto,
        "por_par": {r["par"]: r for r in resumos if "par" in r},
    }
