"""Rotas da API para o bot Meme (USDT)."""
import asyncio
import json
import os
import signal
import subprocess
import sys
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)

from infra.stats_store import carregar_stats_do_dia, calcular_resumo
from api.deps import _verificar_token

router = APIRouter(prefix="/meme")

_MEME_PID_FILE = os.path.join(_ROOT, "run", "bot_meme.pid")
_MEME_LOG_FILE = os.path.join(_ROOT, "logs", "log_operacoes_meme.txt")
_MEME_STATUS_FILE = os.path.join(_ROOT, "run", "status_meme.json")
_MEME_STATS_DIR = os.path.join(_ROOT, "stats_meme")
_MEME_APORTES_FILE = os.path.join(_ROOT, "stats_meme", "aportes.json")
_MEME_POSICAO_FILE = os.path.join(_ROOT, "posicoes", "posicao_meme.json")


def _meme_pid():
    if not os.path.exists(_MEME_PID_FILE):
        return None
    try:
        with open(_MEME_PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def _meme_rodando() -> bool:
    pid = _meme_pid()
    if pid is not None:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            pass

    try:
        if os.path.exists(_MEME_STATUS_FILE):
            with open(_MEME_STATUS_FILE) as f:
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
                return True
    except Exception:
        pass

    return False


def _meme_pid_efetivo():
    pid = _meme_pid()
    if pid is not None:
        return pid
    try:
        if os.path.exists(_MEME_STATUS_FILE):
            with open(_MEME_STATUS_FILE) as f:
                dados = json.load(f)
            return dados.get("pid")
    except Exception:
        pass
    return None


def _carregar_dados_aportes_meme() -> dict:
    if not os.path.exists(_MEME_APORTES_FILE):
        return {"confirmados": [], "rejeitados": []}
    with open(_MEME_APORTES_FILE) as f:
        dados = json.load(f)
    if isinstance(dados, list):
        return {"confirmados": dados, "rejeitados": []}
    return dados


def _salvar_dados_aportes_meme(dados: dict) -> None:
    import tempfile
    dir_ = os.path.dirname(_MEME_APORTES_FILE)
    os.makedirs(dir_, exist_ok=True)
    dados["confirmados"] = sorted(dados["confirmados"], key=lambda x: x.get("data", ""))
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f, indent=2)
        os.replace(tmp, _MEME_APORTES_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def _arquivo_stats_meme(data: str) -> str:
    return os.path.join(_MEME_STATS_DIR, f"{data}.json")


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/status", dependencies=[Depends(_verificar_token)])
def get_status():
    if not os.path.exists(_MEME_STATUS_FILE):
        return {"rodando": False, "ultimo_ciclo": None, "versao": None, "bot": "meme"}
    with open(_MEME_STATUS_FILE) as f:
        dados = json.load(f)

    # Enriquecer com info de posição e saldo
    posicao = None
    if os.path.exists(_MEME_POSICAO_FILE):
        with open(_MEME_POSICAO_FILE) as f:
            posicao = json.load(f)

    dados["posicao"] = posicao
    return dados


@router.get("/scanner", dependencies=[Depends(_verificar_token)])
def get_scanner():
    """Executa scan ao vivo e retorna todos os scores."""
    import os as _os
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))

    from binance import Client as BinanceClient
    api_key = _os.getenv("KEY_BINANCE", "")
    api_secret = _os.getenv("SECRET_BINANCE", "")
    try:
        cliente = BinanceClient(api_key, api_secret)
        from bots.meme.scanner import scan_todos
        resultados = scan_todos(cliente)
        return {"total": len(resultados), "resultados": resultados}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar scanner: {e}")


@router.get("/operacoes", dependencies=[Depends(_verificar_token)])
def get_operacoes(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats_meme(data)
    if not os.path.exists(arquivo):
        return []
    with open(arquivo) as f:
        stats = json.load(f)
    return stats.get("operacoes", [])


@router.get("/stats/dia", dependencies=[Depends(_verificar_token)])
def get_stats_dia(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats_meme(data)
    if not os.path.exists(arquivo):
        return {
            "data": data,
            "total_operacoes": 0,
            "operacoes_lucrativas": 0,
            "lucro_total_brl": 0.0,
            "maior_ganho": 0.0,
            "maior_perda": 0.0,
            "taxa_acerto_pct": 0.0,
        }
    with open(arquivo) as f:
        stats = json.load(f)
    resumo = calcular_resumo(stats)
    resumo["data"] = data
    return resumo


@router.get("/aportes", dependencies=[Depends(_verificar_token)])
def get_aportes():
    dados = _carregar_dados_aportes_meme()
    return dados.get("confirmados", [])


@router.post("/aporte", dependencies=[Depends(_verificar_token)])
def post_aporte(body: dict):
    data_str = body.get("data")
    valor_usdt = body.get("valor_usdt")
    if not data_str or not valor_usdt or float(valor_usdt) <= 0:
        raise HTTPException(status_code=400, detail="data e valor_usdt são obrigatórios e positivos")
    dados = _carregar_dados_aportes_meme()
    dados["confirmados"].append({
        "data": data_str,
        "valor_usdt": round(float(valor_usdt), 6),
        "fonte": "manual",
    })
    _salvar_dados_aportes_meme(dados)
    return {"ok": True}


@router.delete("/aporte", dependencies=[Depends(_verificar_token)])
def delete_aporte(
    data: str = Query(default=""),
    valor_usdt: float = Query(default=0),
):
    dados = _carregar_dados_aportes_meme()
    for i, a in enumerate(dados["confirmados"]):
        if a.get("data") == data and abs(a.get("valor_usdt", 0) - valor_usdt) < 0.000001:
            dados["confirmados"].pop(i)
            _salvar_dados_aportes_meme(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")


@router.patch("/aporte", dependencies=[Depends(_verificar_token)])
def patch_aporte(body: dict):
    data_antiga = body.get("data_antiga", "")
    valor_usdt = float(body.get("valor_usdt", 0))
    nova_data = body.get("nova_data")
    if not nova_data:
        raise HTTPException(status_code=400, detail="nova_data é obrigatório")
    dados = _carregar_dados_aportes_meme()
    for a in dados["confirmados"]:
        if a.get("data") == data_antiga and abs(a.get("valor_usdt", 0) - valor_usdt) < 0.000001:
            a["data"] = nova_data
            _salvar_dados_aportes_meme(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")


@router.post("/bot/iniciar", dependencies=[Depends(_verificar_token)])
def bot_iniciar():
    if _meme_rodando():
        raise HTTPException(status_code=409, detail="Bot meme já está rodando")

    env = os.environ.copy()
    log_dir = os.path.join(_ROOT, "logs")
    run_dir = os.path.join(_ROOT, "run")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(run_dir, exist_ok=True)

    log_path = os.path.join(log_dir, "bot_meme.log")
    log_file = open(log_path, "a")
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(_ROOT, "robo_meme.py")],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=_ROOT,
        env=env,
        start_new_session=True,
    )
    log_file.close()

    with open(_MEME_PID_FILE, "w") as f:
        f.write(str(proc.pid))

    return {"ok": True, "pid": proc.pid}


@router.post("/bot/parar", dependencies=[Depends(_verificar_token)])
def bot_parar():
    if not _meme_rodando():
        raise HTTPException(status_code=409, detail="Bot meme não está rodando")
    pid = _meme_pid()
    if pid is None:
        # Tentar pelo status file
        try:
            with open(_MEME_STATUS_FILE) as f:
                dados = json.load(f)
            pid = dados.get("pid")
        except Exception:
            pass
    if pid is None:
        raise HTTPException(status_code=500, detail="Não foi possível obter PID do bot")
    os.kill(pid, signal.SIGTERM)
    if os.path.exists(_MEME_PID_FILE):
        os.remove(_MEME_PID_FILE)
    return {"ok": True}


@router.get("/bot/logs", dependencies=[Depends(_verificar_token)])
def bot_logs(linhas: int = Query(default=100)):
    if not os.path.exists(_MEME_LOG_FILE):
        return {"linhas": []}
    with open(_MEME_LOG_FILE) as f:
        todas = f.readlines()
    return {"linhas": [linha.rstrip("\n") for linha in todas[-linhas:]]}


@router.get("/bot/logs/stream")
async def bot_logs_stream(token: str = Query(...), historico: int = Query(default=100)):
    """SSE endpoint — token via query param."""
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or token != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")

    async def generator():
        with open(_MEME_LOG_FILE, "a+") as _:
            pass

        with open(_MEME_LOG_FILE) as f:
            todas = f.readlines()
            for linha in todas[-historico:]:
                texto = linha.rstrip("\n")
                if texto:
                    yield f"data: {texto}\n\n"

            f.seek(0, 2)
            while True:
                linha = f.readline()
                if linha:
                    texto = linha.rstrip("\n")
                    if texto:
                        yield f"data: {texto}\n\n"
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(1)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
