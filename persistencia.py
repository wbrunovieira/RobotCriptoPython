import json
import os

ARQUIVO_POSICAO = "posicao.json"

def salvar_posicao(posicao: bool, preco_entrada: float = None, arquivo: str = ARQUIVO_POSICAO):
    dados = {"posicao": posicao, "preco_entrada": preco_entrada}
    with open(arquivo, "w") as f:
        json.dump(dados, f)

def carregar_posicao(arquivo: str = ARQUIVO_POSICAO) -> dict:
    if not os.path.exists(arquivo):
        return {"posicao": False, "preco_entrada": None}
    with open(arquivo, "r") as f:
        return json.load(f)
