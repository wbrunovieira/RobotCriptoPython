"""Universo de pares BRL negociados pelo bot principal."""

_PARES = [
    {"simbolo": "SOLBRL", "ativo": "SOL", "step_size": "0.001"},
    {"simbolo": "BTCBRL", "ativo": "BTC", "step_size": "0.00001"},
    {"simbolo": "ETHBRL", "ativo": "ETH", "step_size": "0.0001"},
    {"simbolo": "XRPBRL", "ativo": "XRP", "step_size": "0.1"},
    # BNBBRL removido: -R$48,25 em 13 trades (31% acerto) — pior par da carteira
]


def listar_pares() -> list:
    """Retorna a lista de pares BRL configurados para operação."""
    return _PARES
