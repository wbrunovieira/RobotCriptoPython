TETO_PCT_PADRAO = 0.60

_PARES = [
    {"simbolo": "SOLBRL", "ativo": "SOL", "step_size": "0.001"},
    {"simbolo": "BTCBRL", "ativo": "BTC", "step_size": "0.00001"},
    {"simbolo": "ETHBRL", "ativo": "ETH", "step_size": "0.0001"},
    {"simbolo": "XRPBRL", "ativo": "XRP", "step_size": "0.1"},
    {"simbolo": "BNBBRL", "ativo": "BNB", "step_size": "0.001"},
]


def listar_pares() -> list:
    """Retorna a lista de pares configurados para operação."""
    return _PARES


def arquivo_posicao(simbolo: str) -> str:
    """Retorna o caminho do arquivo de estado de posição para o par."""
    return f"posicao_{simbolo}.json"


def calcular_saldo_disponivel(saldo_brl: float, teto_pct: float = TETO_PCT_PADRAO) -> float:
    """Retorna o máximo que um par pode usar (teto_pct do saldo BRL atual).

    Regra Opção C: cada par pode usar até 60% do BRL disponível no momento
    da compra. Isso permite múltiplas posições simultâneas sem esvaziar o
    caixa completamente.

    Exemplo:
      - BRL=R$1000 → SOL pode usar até R$600
      - Após SOL comprar: BRL=R$400 → BTC pode usar até R$240
    """
    return round(saldo_brl * teto_pct, 2)


def pares_sem_posicao(estados: dict) -> list:
    """Retorna lista de símbolos que não têm posição aberta.

    estados = {"SOLBRL": {"posicao": True}, "BTCBRL": {"posicao": False}, ...}
    """
    return [simbolo for simbolo, estado in estados.items() if not estado.get("posicao")]


def consolidar_resumo(resumos: list) -> dict:
    """Agrega métricas de múltiplos pares em um resumo consolidado.

    Cada item de resumos deve ter: par, total_operacoes, operacoes_lucrativas,
    lucro_total_brl.
    """
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
