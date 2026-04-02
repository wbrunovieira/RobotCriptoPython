# pares/ — universo de pares e utilitários de carteira
# Este pacote substitui o antigo pares.py (Python prefere o pacote ao .py homônimo)
from pares.brl import listar_pares
from pares.base import (
    TETO_PCT_PADRAO,
    arquivo_posicao,
    calcular_saldo_disponivel,
    pares_sem_posicao,
    consolidar_resumo,
)

__all__ = [
    "listar_pares",
    "TETO_PCT_PADRAO",
    "arquivo_posicao",
    "calcular_saldo_disponivel",
    "pares_sem_posicao",
    "consolidar_resumo",
]
