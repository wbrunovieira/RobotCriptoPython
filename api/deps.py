"""Dependências e utilidades compartilhadas entre os routers da API."""
import json
import os
import tempfile
from datetime import date

from binance import Client as BinanceClient
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(_ROOT, ".env"))

_BOT_PID_FILE = os.path.join(_ROOT, "run", "bot.pid")
_BOT_LOG_FILE = os.path.join(_ROOT, "logs", "bot.log")

_security = HTTPBearer()


def _verificar_token(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or credentials.credentials != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")
    return credentials.credentials


def _stats_dir() -> str:
    return os.getenv("STATS_DIR", os.path.join(_ROOT, "stats"))


def _aportes_file() -> str:
    return os.path.join(_stats_dir(), "aportes.json")


def _posicao_dir() -> str:
    return os.getenv("POSICAO_DIR", os.path.join(_ROOT, "posicoes"))


def _reserva_file() -> str:
    return os.getenv("RESERVA_FILE", os.path.join(_ROOT, "reserva/estado.json"))


def _status_file() -> str:
    return os.getenv("STATUS_FILE", os.path.join(_ROOT, "run", "status.json"))


def _arquivo_posicao_par(simbolo: str) -> str:
    base = _posicao_dir()
    return os.path.join(base, f"posicao_{simbolo}.json")


def _arquivo_stats(data: str) -> str:
    return os.path.join(_stats_dir(), f"{data}.json")


def _carregar_dados_aportes() -> dict:
    """Retorna {"confirmados": [...], "rejeitados": [...]}."""
    f = _aportes_file()
    if not os.path.exists(f):
        return {"confirmados": [], "rejeitados": []}
    with open(f) as fp:
        dados = json.load(fp)
    if isinstance(dados, list):
        return {"confirmados": dados, "rejeitados": []}
    return dados


def _salvar_dados_aportes(dados: dict) -> None:
    dir_ = _stats_dir()
    os.makedirs(dir_, exist_ok=True)
    dados["confirmados"] = sorted(dados["confirmados"], key=lambda x: x["data"])
    arquivo = _aportes_file()
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as fp:
            json.dump(dados, fp, indent=2)
        os.replace(tmp, arquivo)
    except Exception:
        os.unlink(tmp)
        raise


def _carregar_aportes() -> list:
    return _carregar_dados_aportes()["confirmados"]


def _buscar_depositos_binance() -> list:
    """Retorna depósitos BRL bem-sucedidos da Binance."""
    api_key = os.getenv("KEY_BINANCE", "")
    api_secret = os.getenv("SECRET_BINANCE", "")
    cliente = BinanceClient(api_key, api_secret)
    resp = cliente.get_fiat_deposit_withdraw_history(transactionType=0)
    depositos = resp.get("data", [])
    resultado = []
    for dep in depositos:
        if dep.get("fiatCurrency") != "BRL":
            continue
        if dep.get("status") not in ("Successful", "Success"):
            continue
        order_no = dep.get("orderNo", "")
        ts = int(dep.get("createTime", 0))
        data_str = date.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        valor = float(dep.get("indicatedAmount") or dep.get("amount") or 0)
        if valor <= 0:
            continue
        resultado.append({"order_no": order_no, "data": data_str, "valor_brl": round(valor, 2)})
    return resultado


def _bot_pid():
    if not os.path.exists(_BOT_PID_FILE):
        return None
    try:
        with open(_BOT_PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _bot_rodando() -> bool:
    pid = _bot_pid()
    if pid is not None:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            pass

    try:
        arquivo = _status_file()
        if os.path.exists(arquivo):
            with open(arquivo) as f:
                dados = json.load(f)
            if dados.get("rodando") is False:
                return False
            if dados.get("rodando") is True:
                pid_status = dados.get("pid")
                if pid_status:
                    try:
                        os.kill(int(pid_status), 0)
                        return True
                    except (ProcessLookupError, PermissionError, TypeError):
                        return False
                else:
                    return True
    except Exception:
        pass

    return False


def _bot_pid_efetivo():
    pid = _bot_pid()
    if pid is not None:
        return pid
    try:
        arquivo = _status_file()
        if os.path.exists(arquivo):
            with open(arquivo) as f:
                dados = json.load(f)
            return dados.get("pid")
    except Exception:
        pass
    return None


class BotParams(BaseModel):
    bot_id: str = "MACross1"
    take_profit_pct: float = 0.03
    stop_pct: float = 0.015
    teto_saldo_pct: float = 0.60
    periodo_candle: str = "1h"
    intervalo_monitoramento: int = 60
    intervalo_estrategia_min: int = 60
    max_posicoes: int = 2
