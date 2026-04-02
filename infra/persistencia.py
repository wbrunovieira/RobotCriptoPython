import json
import os
import tempfile

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
    dir_ = os.path.dirname(arquivo) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f)
        os.replace(tmp, arquivo)
    except Exception:
        os.unlink(tmp)
        raise


def carregar_posicao(arquivo: str = ARQUIVO_POSICAO) -> dict:
    if not os.path.exists(arquivo):
        return {"posicao": False, "preco_entrada": None, "preco_maximo": None, "stop_price": None}
    with open(arquivo) as f:
        dados = json.load(f)
    dados.setdefault("preco_maximo", None)
    dados.setdefault("stop_price", None)
    return dados
