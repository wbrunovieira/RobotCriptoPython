import json
import os

ARQUIVO_POSICAO = "posicoes/posicao.json"


def salvar_posicao(
    posicao: bool,
    preco_entrada: float = None,
    preco_maximo: float = None,
    stop_price: float = None,
    arquivo: str = ARQUIVO_POSICAO,
):
    dados = {
        "posicao": posicao,
        "preco_entrada": preco_entrada,
        "preco_maximo": preco_maximo,
        "stop_price": stop_price,
    }
    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "w") as f:
        json.dump(dados, f)


def carregar_posicao(arquivo: str = ARQUIVO_POSICAO) -> dict:
    if not os.path.exists(arquivo):
        return {"posicao": False, "preco_entrada": None, "preco_maximo": None, "stop_price": None}
    dados = json.load(open(arquivo))
    dados.setdefault("preco_maximo", None)
    dados.setdefault("stop_price", None)
    return dados
