import csv
import io
import json
import os
import signal
import subprocess
import sys
from datetime import date
from dotenv import load_dotenv
from binance import Client as BinanceClient

# Raiz do projeto (um nível acima de api/)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Permite importar módulos da raiz do projeto (stats, fiscal, etc.)
sys.path.insert(0, _ROOT)
load_dotenv(os.path.join(_ROOT, ".env"))
from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from stats import carregar_stats_do_dia, calcular_resumo
from fiscal import carregar_stats_do_mes, calcular_resumo_mensal, exportar_csv_mensal
from persistencia import carregar_posicao
from pares import listar_pares, arquivo_posicao
from reserva import estado_inicial

app = FastAPI(title="Cripto Robot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_security = HTTPBearer()


def _verificar_token(credentials: HTTPAuthorizationCredentials = Depends(_security)):
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or credentials.credentials != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")
    return credentials.credentials


def _stats_dir() -> str:
    return os.getenv("STATS_DIR", os.path.join(_ROOT, "stats"))


def _posicao_dir() -> str:
    return os.getenv("POSICAO_DIR", _ROOT)


def _reserva_file() -> str:
    return os.getenv("RESERVA_FILE", os.path.join(_ROOT, "reserva/estado.json"))


def _status_file() -> str:
    return os.getenv("STATUS_FILE", os.path.join(_ROOT, "status.json"))


def _arquivo_posicao_par(simbolo: str) -> str:
    base = _posicao_dir()
    return os.path.join(base, f"posicao_{simbolo}.json")


def _arquivo_stats(data: str) -> str:
    return os.path.join(_stats_dir(), f"{data}.json")


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@app.get("/status", dependencies=[Depends(_verificar_token)])
def get_status():
    arquivo = _status_file()
    if not os.path.exists(arquivo):
        return {"rodando": False, "ultimo_ciclo": None, "versao": None}
    with open(arquivo) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# GET /posicoes
# ---------------------------------------------------------------------------

@app.get("/posicoes", dependencies=[Depends(_verificar_token)])
def get_posicoes():
    resultado = {}
    for par in listar_pares():
        simbolo = par["simbolo"]
        arq = _arquivo_posicao_par(simbolo)
        if os.path.exists(arq):
            with open(arq) as f:
                estado = json.load(f)
        else:
            estado = {"posicao": False, "preco_entrada": None, "preco_maximo": None, "stop_price": None}
        resultado[simbolo] = estado
    return resultado


# ---------------------------------------------------------------------------
# GET /stats/dia
# ---------------------------------------------------------------------------

@app.get("/stats/dia", dependencies=[Depends(_verificar_token)])
def get_stats_dia(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats(data)
    if not os.path.exists(arquivo):
        return {
            "data": data, "total_operacoes": 0, "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0, "maior_ganho": 0.0, "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
        }
    with open(arquivo) as f:
        stats = json.load(f)
    resumo = calcular_resumo(stats)
    resumo["data"] = data
    return resumo


# ---------------------------------------------------------------------------
# GET /stats/mes
# ---------------------------------------------------------------------------

@app.get("/stats/mes", dependencies=[Depends(_verificar_token)])
def get_stats_mes(mes: str = Query(..., description="Formato: YYYY-MM")):
    stats_list = carregar_stats_do_mes(mes, diretorio=_stats_dir())
    resumo = calcular_resumo_mensal(stats_list)
    resumo["mes"] = mes
    return resumo


# ---------------------------------------------------------------------------
# GET /operacoes
# ---------------------------------------------------------------------------

@app.get("/operacoes", dependencies=[Depends(_verificar_token)])
def get_operacoes(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats(data)
    if not os.path.exists(arquivo):
        return []
    with open(arquivo) as f:
        stats = json.load(f)
    return stats.get("operacoes", [])


# ---------------------------------------------------------------------------
# GET /reserva
# ---------------------------------------------------------------------------

@app.get("/reserva", dependencies=[Depends(_verificar_token)])
def get_reserva():
    arquivo = _reserva_file()
    if not os.path.exists(arquivo):
        return estado_inicial()
    with open(arquivo) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# GET /saldos
# ---------------------------------------------------------------------------

@app.get("/saldos", dependencies=[Depends(_verificar_token)])
def get_saldos():
    api_key = os.getenv("KEY_BINANCE", "")
    api_secret = os.getenv("SECRET_BINANCE", "")
    cliente = BinanceClient(api_key, api_secret)

    cotacao_usd = float(cliente.get_symbol_ticker(symbol="USDTBRL")["price"])

    ativos = ["BRL", "SOL", "BTC", "ETH", "XRP", "BNB", "USDC", "USDT"]
    conta = cliente.get_account()
    saldos = {a: 0.0 for a in ativos}
    for item in conta["balances"]:
        if item["asset"] in saldos:
            saldos[item["asset"]] = float(item["free"]) + float(item["locked"])

    resultado = {}
    total_brl = saldos["BRL"]

    for ativo, quantidade in saldos.items():
        if quantidade == 0:
            continue
        if ativo == "BRL":
            resultado["BRL"] = {"quantidade": quantidade, "valor_brl": quantidade, "valor_usd": round(quantidade / cotacao_usd, 2)}
            continue
        if ativo in ("USDC", "USDT"):
            valor_brl = round(quantidade * cotacao_usd, 2)
            total_brl += valor_brl
            resultado[ativo] = {"quantidade": quantidade, "valor_brl": valor_brl, "valor_usd": round(quantidade, 2)}
            continue
        try:
            preco_brl = float(cliente.get_symbol_ticker(symbol=f"{ativo}BRL")["price"])
            valor_brl = round(quantidade * preco_brl, 2)
            total_brl += valor_brl
            resultado[ativo] = {
                "quantidade": quantidade,
                "preco_brl": preco_brl,
                "valor_brl": valor_brl,
                "valor_usd": round(valor_brl / cotacao_usd, 2),
            }
        except Exception:
            pass

    return {"total_brl": round(total_brl, 2), "total_usd": round(total_brl / cotacao_usd, 2), "ativos": resultado}


# ---------------------------------------------------------------------------
# GET /cotacao
# ---------------------------------------------------------------------------

@app.get("/cotacao", dependencies=[Depends(_verificar_token)])
def get_cotacao():
    api_key = os.getenv("KEY_BINANCE", "")
    api_secret = os.getenv("SECRET_BINANCE", "")
    cliente = BinanceClient(api_key, api_secret)
    ticker = cliente.get_symbol_ticker(symbol="USDTBRL")
    return {"usd_brl": float(ticker["price"])}


# ---------------------------------------------------------------------------
# GET /candles/{simbolo}
# ---------------------------------------------------------------------------

@app.get("/candles/{simbolo}", dependencies=[Depends(_verificar_token)])
def get_candles(simbolo: str, limite: int = Query(default=100)):
    api_key = os.getenv("KEY_BINANCE", "")
    api_secret = os.getenv("SECRET_BINANCE", "")
    cliente = BinanceClient(api_key, api_secret)
    klines = cliente.get_klines(symbol=simbolo.upper(), interval="15m", limit=limite)
    candles = [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
        }
        for k in klines
    ]
    return candles


# ---------------------------------------------------------------------------
# GET /fiscal/csv
# ---------------------------------------------------------------------------

@app.get("/fiscal/csv", dependencies=[Depends(_verificar_token)])
def get_fiscal_csv(mes: str = Query(..., description="Formato: YYYY-MM")):
    stats_list = carregar_stats_do_mes(mes, diretorio=_stats_dir())

    output = io.StringIO()
    campos = ["data", "tipo", "par", "preco", "quantidade", "total_brl", "lucro_brl", "lucro_pct", "timestamp"]
    writer = csv.DictWriter(output, fieldnames=campos)
    writer.writeheader()
    for stats in stats_list:
        data_dia = stats.get("data", "")
        for op in stats.get("operacoes", []):
            writer.writerow({
                "data": data_dia,
                "tipo": op.get("tipo", ""),
                "par": op.get("par", ""),
                "preco": op.get("preco", ""),
                "quantidade": op.get("quantidade", ""),
                "total_brl": op.get("total_brl", ""),
                "lucro_brl": op.get("lucro_brl", ""),
                "lucro_pct": op.get("lucro_pct", ""),
                "timestamp": op.get("timestamp", ""),
            })

    output.seek(0)
    filename = f"relatorio_fiscal_{mes}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Bot process control
# ---------------------------------------------------------------------------

_BOT_PID_FILE = os.path.join(_ROOT, "bot.pid")
_BOT_LOG_FILE = os.path.join(_ROOT, "bot.log")


def _bot_pid() -> Optional[int]:
    if not os.path.exists(_BOT_PID_FILE):
        return None
    try:
        with open(_BOT_PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _bot_rodando() -> bool:
    # 1) verifica pelo PID salvo (bot iniciado pelo painel)
    pid = _bot_pid()
    if pid is not None:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            pass

    # 2) fallback: verifica status.json (bot iniciado manualmente)
    try:
        arquivo = _status_file()
        if os.path.exists(arquivo):
            with open(arquivo) as f:
                dados = json.load(f)
            if dados.get("rodando") is True:
                # confirma que o processo ainda existe
                pid_status = dados.get("pid")
                if pid_status:
                    try:
                        os.kill(int(pid_status), 0)
                        return True
                    except (ProcessLookupError, PermissionError, TypeError):
                        pass
                else:
                    return True
    except Exception:
        pass

    return False


class BotParams(BaseModel):
    take_profit_pct: float = 0.01
    stop_pct: float = 0.05
    teto_saldo_pct: float = 0.60
    periodo_candle: str = "15m"
    intervalo_monitoramento: int = 60
    intervalo_estrategia_min: int = 15


@app.post("/bot/iniciar", dependencies=[Depends(_verificar_token)])
def bot_iniciar(params: BotParams):
    if _bot_rodando():
        raise HTTPException(status_code=409, detail="Bot já está rodando")

    env = os.environ.copy()
    env["BOT_TAKE_PROFIT_PCT"] = str(params.take_profit_pct)
    env["BOT_STOP_PCT"] = str(params.stop_pct)
    env["BOT_TETO_SALDO_PCT"] = str(params.teto_saldo_pct)
    env["BOT_PERIODO_CANDLE"] = params.periodo_candle
    env["BOT_INTERVALO_MONITORAMENTO"] = str(params.intervalo_monitoramento)
    env["BOT_INTERVALO_ESTRATEGIA_MIN"] = str(params.intervalo_estrategia_min)

    log_file = open(_BOT_LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(_ROOT, "robo_cripto.py")],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=_ROOT,
        env=env,
    )
    with open(_BOT_PID_FILE, "w") as f:
        f.write(str(proc.pid))

    return {"ok": True, "pid": proc.pid}


@app.post("/bot/parar", dependencies=[Depends(_verificar_token)])
def bot_parar():
    if not _bot_rodando():
        raise HTTPException(status_code=409, detail="Bot não está rodando")
    pid = _bot_pid()
    os.kill(pid, signal.SIGTERM)
    if os.path.exists(_BOT_PID_FILE):
        os.remove(_BOT_PID_FILE)
    return {"ok": True}


def _bot_pid_efetivo() -> Optional[int]:
    pid = _bot_pid()
    if pid is not None:
        return pid
    # fallback: PID do status.json
    try:
        arquivo = _status_file()
        if os.path.exists(arquivo):
            with open(arquivo) as f:
                dados = json.load(f)
            return dados.get("pid")
    except Exception:
        pass
    return None


@app.get("/bot/info", dependencies=[Depends(_verificar_token)])
def bot_info():
    return {"rodando": _bot_rodando(), "pid": _bot_pid_efetivo()}


@app.get("/bot/logs", dependencies=[Depends(_verificar_token)])
def bot_logs(linhas: int = Query(default=100)):
    if not os.path.exists(_BOT_LOG_FILE):
        return {"linhas": []}
    with open(_BOT_LOG_FILE) as f:
        todas = f.readlines()
    return {"linhas": [l.rstrip("\n") for l in todas[-linhas:]]}
