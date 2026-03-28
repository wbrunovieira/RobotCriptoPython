import os
import pytest
from persistencia import salvar_posicao, carregar_posicao


def test_salvar_e_carregar_posicao(tmp_path):
    arquivo = str(tmp_path / "posicao.json")
    salvar_posicao(True, 430.5, arquivo=arquivo)
    resultado = carregar_posicao(arquivo=arquivo)
    assert resultado["posicao"] is True
    assert resultado["preco_entrada"] == 430.5


def test_carregar_posicao_inexistente(tmp_path):
    arquivo = str(tmp_path / "nao_existe.json")
    resultado = carregar_posicao(arquivo=arquivo)
    assert resultado["posicao"] is False
    assert resultado["preco_entrada"] is None


def test_salvar_posicao_sem_preco(tmp_path):
    arquivo = str(tmp_path / "posicao.json")
    salvar_posicao(False, None, arquivo=arquivo)
    resultado = carregar_posicao(arquivo=arquivo)
    assert resultado["posicao"] is False
    assert resultado["preco_entrada"] is None
