"""Testes do sistema de cooldown por par após trailing stop."""
import json
import os
import tempfile

import pandas as pd
import pytest


def _make_cooldown_funcs(tmp_path):
    """Retorna versões de _registrar_cooldown e _par_em_cooldown apontando para tmp_path."""
    cooldown_file = str(tmp_path / "cooldown_pares.json")

    def registrar(simbolo: str, horas: int = 5) -> None:
        cooldowns = {}
        if os.path.exists(cooldown_file):
            with open(cooldown_file) as f:
                cooldowns = json.load(f)
        bloqueio_ate = (
            pd.Timestamp.now(tz="America/Sao_Paulo") + pd.Timedelta(hours=horas)
        ).isoformat()
        cooldowns[simbolo] = bloqueio_ate
        with open(cooldown_file, "w") as f:
            json.dump(cooldowns, f)

    def em_cooldown(simbolo: str) -> bool:
        if not os.path.exists(cooldown_file):
            return False
        with open(cooldown_file) as f:
            cooldowns = json.load(f)
        if simbolo not in cooldowns:
            return False
        bloqueio_ate = pd.Timestamp(cooldowns[simbolo])
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
        if bloqueio_ate.tzinfo is None:
            bloqueio_ate = bloqueio_ate.tz_localize("America/Sao_Paulo")
        return agora < bloqueio_ate

    return registrar, em_cooldown


def test_par_sem_cooldown_nao_bloqueado(tmp_path):
    _, em_cooldown = _make_cooldown_funcs(tmp_path)
    assert em_cooldown("BNBBRL") is False


def test_par_apos_stop_fica_bloqueado(tmp_path):
    registrar, em_cooldown = _make_cooldown_funcs(tmp_path)
    registrar("BNBBRL", horas=5)
    assert em_cooldown("BNBBRL") is True


def test_outros_pares_nao_afetados(tmp_path):
    registrar, em_cooldown = _make_cooldown_funcs(tmp_path)
    registrar("BNBBRL", horas=5)
    assert em_cooldown("SOLBRL") is False
    assert em_cooldown("BTCBRL") is False


def test_cooldown_expirado_nao_bloqueia(tmp_path):
    cooldown_file = str(tmp_path / "cooldown_pares.json")
    # Grava expiração no passado
    bloqueio_ate = (
        pd.Timestamp.now(tz="America/Sao_Paulo") - pd.Timedelta(hours=1)
    ).isoformat()
    with open(cooldown_file, "w") as f:
        json.dump({"BNBBRL": bloqueio_ate}, f)

    _, em_cooldown = _make_cooldown_funcs(tmp_path)
    assert em_cooldown("BNBBRL") is False


def test_multiplos_pares_independentes(tmp_path):
    registrar, em_cooldown = _make_cooldown_funcs(tmp_path)
    registrar("BNBBRL", horas=5)
    registrar("XRPBRL", horas=5)
    assert em_cooldown("BNBBRL") is True
    assert em_cooldown("XRPBRL") is True
    assert em_cooldown("SOLBRL") is False
