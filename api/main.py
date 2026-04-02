import asyncio
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


def _aportes_file() -> str:
    return os.path.join(_stats_dir(), "aportes.json")


def _carregar_dados_aportes() -> dict:
    """Retorna {"confirmados": [...], "rejeitados": [...]}."""
    f = _aportes_file()
    if not os.path.exists(f):
        return {"confirmados": [], "rejeitados": []}
    with open(f) as fp:
        dados = json.load(fp)
    # Retrocompatibilidade: arquivo antigo era uma lista plana
    if isinstance(dados, list):
        return {"confirmados": dados, "rejeitados": []}
    return dados


def _salvar_dados_aportes(dados: dict) -> None:
    os.makedirs(_stats_dir(), exist_ok=True)
    dados["confirmados"] = sorted(dados["confirmados"], key=lambda x: x["data"])
    with open(_aportes_file(), "w") as fp:
        json.dump(dados, fp, indent=2)


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
            # se bot gravou rodando=false ao sair, confia nesse valor
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


class BotParams(BaseModel):
    bot_id: str = "MACross1"
    take_profit_pct: float = 0.03
    stop_pct: float = 0.015
    teto_saldo_pct: float = 0.60
    periodo_candle: str = "1h"
    intervalo_monitoramento: int = 60
    intervalo_estrategia_min: int = 60
    max_posicoes: int = 2


@app.post("/bot/iniciar", dependencies=[Depends(_verificar_token)])
def bot_iniciar(params: BotParams):
    if _bot_rodando():
        raise HTTPException(status_code=409, detail="Bot já está rodando")

    env = os.environ.copy()
    env["BOT_ID"] = params.bot_id
    env["BOT_TAKE_PROFIT_PCT"] = str(params.take_profit_pct)
    env["BOT_STOP_PCT"] = str(params.stop_pct)
    env["BOT_TETO_SALDO_PCT"] = str(params.teto_saldo_pct)
    env["BOT_PERIODO_CANDLE"] = params.periodo_candle
    env["BOT_INTERVALO_MONITORAMENTO"] = str(params.intervalo_monitoramento)
    env["BOT_INTERVALO_ESTRATEGIA_MIN"] = str(params.intervalo_estrategia_min)
    env["BOT_MAX_POSICOES"] = str(params.max_posicoes)

    log_file = open(_BOT_LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(_ROOT, "robo_cripto.py")],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=_ROOT,
        env=env,
        start_new_session=True,  # isola o bot dos sinais do uvicorn
    )
    log_file.close()  # filho já herdou o fd; fecha cópia do pai

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


@app.get("/performance", dependencies=[Depends(_verificar_token)])
def get_performance(periodo: str = Query(default="mes")):
    import yfinance as yf
    from datetime import timedelta

    hoje = date.today()
    dias = {"dia": 1, "semana": 7, "mes": 30}.get(periodo, 30)
    inicio = hoje - timedelta(days=dias)

    # --- Bot: lucro acumulado por dia ---
    bot_series = []
    lucro_acumulado = 0.0
    saldo_inicial = None

    for i in range(dias + 1):
        d = inicio + timedelta(days=i)
        data_str = d.strftime("%Y-%m-%d")
        arquivo = os.path.join(_stats_dir(), f"{data_str}.json")
        if os.path.exists(arquivo):
            with open(arquivo) as f:
                stats = json.load(f)
            if saldo_inicial is None:
                saldo_inicial = stats.get("saldo_inicial_brl") or 1000.0
            resumo = calcular_resumo(stats)
            lucro_acumulado += resumo["lucro_total_brl"]
        pct = round((lucro_acumulado / saldo_inicial) * 100, 4) if saldo_inicial else 0.0
        bot_series.append({"data": data_str, "pct": pct})

    if saldo_inicial is None:
        saldo_inicial = 1000.0

    # --- CDI 115% sintético (~13.75% a.a.) ---
    cdi_anual = 0.1375
    cdi_115_diario = (1 + cdi_anual * 1.15) ** (1 / 252) - 1
    cdi_series, acum = [], 1.0
    for i, p in enumerate(bot_series):
        cdi_series.append({"data": p["data"], "pct": round((acum - 1) * 100, 4)})
        acum *= (1 + cdi_115_diario)

    # --- Benchmarks via yfinance ---
    start_str = inicio.strftime("%Y-%m-%d")
    end_str = (hoje + timedelta(days=1)).strftime("%Y-%m-%d")

    def yf_returns(ticker: str) -> list:
        try:
            df = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=True)
            if df.empty:
                return []
            closes = df["Close"].squeeze().dropna()
            base = float(closes.iloc[0])
            return [
                {"data": str(ts.date()), "pct": round((float(v) / base - 1) * 100, 4)}
                for ts, v in closes.items()
            ]
        except Exception:
            return []

    return {
        "periodo": periodo,
        "saldo_inicial": saldo_inicial,
        "series": {
            "bot": bot_series,
            "cdi_115": cdi_series,
            "ibovespa": yf_returns("^BVSP"),
            "btc": yf_returns("BTC-USD"),
        },
    }


# ---------------------------------------------------------------------------
# GET/POST /portfolio/aportes
# ---------------------------------------------------------------------------

@app.get("/portfolio/aportes", dependencies=[Depends(_verificar_token)])
def get_aportes():
    return _carregar_aportes()


@app.get("/portfolio/aportes/pendentes", dependencies=[Depends(_verificar_token)])
def get_aportes_pendentes():
    """Retorna depósitos BRL da Binance ainda não classificados (nem confirmados nem rejeitados)."""
    try:
        depositos = _buscar_depositos_binance()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro Binance: {e}")

    dados = _carregar_dados_aportes()
    order_nos_vistos = (
        {a.get("order_no") for a in dados["confirmados"] if a.get("order_no")}
        | set(dados["rejeitados"])
    )
    pendentes = [d for d in depositos if d["order_no"] not in order_nos_vistos]
    return pendentes


@app.post("/portfolio/aporte/confirmar", dependencies=[Depends(_verificar_token)])
def confirmar_aporte(body: dict):
    """Confirma um depósito como aporte para esta automação."""
    order_no = body.get("order_no")
    data_str = body.get("data")
    valor_brl = body.get("valor_brl")
    if not order_no or not data_str or not valor_brl:
        raise HTTPException(status_code=400, detail="order_no, data e valor_brl são obrigatórios")
    dados = _carregar_dados_aportes()
    if order_no not in {a.get("order_no") for a in dados["confirmados"]}:
        dados["confirmados"].append({
            "data": data_str,
            "valor_brl": round(float(valor_brl), 2),
            "order_no": order_no,
            "fonte": "binance",
        })
    _salvar_dados_aportes(dados)
    return {"ok": True}


@app.post("/portfolio/aporte/rejeitar", dependencies=[Depends(_verificar_token)])
def rejeitar_aporte(body: dict):
    """Marca um depósito como não pertencente a esta automação."""
    order_no = body.get("order_no")
    if not order_no:
        raise HTTPException(status_code=400, detail="order_no é obrigatório")
    dados = _carregar_dados_aportes()
    if order_no not in dados["rejeitados"]:
        dados["rejeitados"].append(order_no)
    _salvar_dados_aportes(dados)
    return {"ok": True}


@app.post("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def post_aporte(body: dict):
    """Registra um aporte manual (sem order_no da Binance)."""
    data_str = body.get("data")
    valor_brl = body.get("valor_brl")
    if not data_str or not valor_brl or float(valor_brl) <= 0:
        raise HTTPException(status_code=400, detail="data e valor_brl são obrigatórios")
    dados = _carregar_dados_aportes()
    dados["confirmados"].append({
        "data": data_str,
        "valor_brl": round(float(valor_brl), 2),
        "fonte": "manual",
    })
    _salvar_dados_aportes(dados)
    return {"ok": True}


@app.delete("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def delete_aporte(order_no: str = Query(default=""), data: str = Query(default=""), valor_brl: float = Query(default=0)):
    dados = _carregar_dados_aportes()
    for i, a in enumerate(dados["confirmados"]):
        if order_no and a.get("order_no") == order_no:
            dados["confirmados"].pop(i)
            _salvar_dados_aportes(dados)
            return {"ok": True}
        if not order_no and a["data"] == data and abs(a["valor_brl"] - valor_brl) < 0.01:
            dados["confirmados"].pop(i)
            _salvar_dados_aportes(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")


@app.patch("/portfolio/aporte", dependencies=[Depends(_verificar_token)])
def patch_aporte(body: dict):
    """Atualiza a data de um aporte (corrige data registrada pela Binance)."""
    order_no = body.get("order_no", "")
    data_antiga = body.get("data_antiga", "")
    valor_brl = float(body.get("valor_brl", 0))
    nova_data = body.get("nova_data")
    if not nova_data:
        raise HTTPException(status_code=400, detail="nova_data é obrigatório")
    dados = _carregar_dados_aportes()
    for a in dados["confirmados"]:
        if order_no and a.get("order_no") == order_no:
            a["data"] = nova_data
            _salvar_dados_aportes(dados)
            return {"ok": True}
        if not order_no and a["data"] == data_antiga and abs(a["valor_brl"] - valor_brl) < 0.01:
            a["data"] = nova_data
            _salvar_dados_aportes(dados)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Aporte não encontrado")


# PATCH /stats/{data}/saldo
# ---------------------------------------------------------------------------

@app.patch("/stats/{data_str}/saldo", dependencies=[Depends(_verificar_token)])
def patch_saldo_dia(data_str: str, body: dict):
    """Corrige o saldo_inicial_brl de um dia (para intra-day deposits não capturados pelo bot)."""
    novo_saldo = body.get("saldo_inicial_brl")
    if novo_saldo is None:
        raise HTTPException(status_code=400, detail="saldo_inicial_brl obrigatório")
    arquivo = _arquivo_stats(data_str)
    if not os.path.exists(arquivo):
        raise HTTPException(status_code=404, detail=f"Stats do dia {data_str} não encontrado")
    with open(arquivo) as f:
        stats = json.load(f)
    stats["saldo_inicial_brl"] = round(float(novo_saldo), 2)
    with open(arquivo, "w") as f:
        json.dump(stats, f, indent=2)
    return {"ok": True}


# GET /portfolio/evolucao
# ---------------------------------------------------------------------------

@app.get("/portfolio/evolucao", dependencies=[Depends(_verificar_token)])
def get_portfolio_evolucao():
    """Retorna a evolução diária do portfolio: BRL + posições abertas (custo ou mercado).

    Para dias históricos usa custo de entrada (conservador).
    Para o dia mais recente busca preços de mercado na Binance.
    """
    stats_dir = _stats_dir()
    if not os.path.exists(stats_dir):
        return {"capital_inicial": 0, "pontos": []}

    arquivos = sorted(
        f for f in os.listdir(stats_dir)
        if f.endswith(".json") and f != "aportes.json"
    )
    if not arquivos:
        return {"capital_inicial": 0, "pontos": []}

    # Reconstrói posições abertas acumulando compras/vendas de todos os dias
    posicoes: dict = {}  # {par: {quantidade, custo_total}}
    pontos = []

    for filename in arquivos:
        data_str = filename[:-5]
        with open(os.path.join(stats_dir, filename)) as f:
            stats = json.load(f)

        saldo_brl = stats.get("saldo_inicial_brl", 0.0)
        custo_posicoes = sum(p["custo_total"] for p in posicoes.values())
        valor_dia = round(saldo_brl + custo_posicoes, 2)

        pontos.append({"data": data_str, "valor_brl": valor_dia, "a_mercado": False})

        # Atualiza posições abertas com as operações do dia
        for op in stats.get("operacoes", []):
            par = op.get("par") or op.get("simbolo", "")
            if not par:
                continue
            if op["tipo"] == "COMPRA":
                if par not in posicoes:
                    posicoes[par] = {"quantidade": 0.0, "custo_total": 0.0}
                posicoes[par]["quantidade"] += float(op["quantidade"])
                posicoes[par]["custo_total"] += float(op["total_brl"])
            elif op["tipo"] == "VENDA" and par in posicoes:
                pos = posicoes[par]
                if pos["quantidade"] > 0:
                    frac = min(float(op["quantidade"]) / pos["quantidade"], 1.0)
                    pos["custo_total"] -= pos["custo_total"] * frac
                    pos["quantidade"] -= float(op["quantidade"])
                    if pos["quantidade"] < 0.0001:
                        del posicoes[par]

    # Ponto atual com preços de mercado (sobrescreve o último se for hoje)
    hoje = date.today().strftime("%Y-%m-%d")
    saldo_brl_atual = 0.0
    try:
        api_key = os.getenv("KEY_BINANCE", "")
        api_secret = os.getenv("SECRET_BINANCE", "")
        cliente = BinanceClient(api_key, api_secret)

        conta = cliente.get_account()
        saldo_brl_atual = next(
            (float(b["free"]) + float(b["locked"])
             for b in conta["balances"] if b["asset"] == "BRL"), 0.0
        )

        valor_posicoes_mercado = 0.0
        for par, pos in posicoes.items():
            if pos["quantidade"] > 0.0001:
                try:
                    preco = float(cliente.get_symbol_ticker(symbol=par)["price"])
                    valor_posicoes_mercado += pos["quantidade"] * preco
                except Exception:
                    valor_posicoes_mercado += pos["custo_total"]  # fallback: custo

        valor_mercado = round(saldo_brl_atual + valor_posicoes_mercado, 2)

        if pontos and pontos[-1]["data"] == hoje:
            pontos[-1]["valor_brl"] = valor_mercado
            pontos[-1]["a_mercado"] = True
        else:
            pontos.append({"data": hoje, "valor_brl": valor_mercado, "a_mercado": True})
    except Exception:
        pass

    # Calcula capital acumulado por dia baseado em aportes registrados
    aportes = _carregar_aportes()
    total_investido = 0.0
    aporte_idx = 0

    for p in pontos:
        # Soma todos os aportes até (inclusive) esse dia
        while aporte_idx < len(aportes) and aportes[aporte_idx]["data"] <= p["data"]:
            total_investido += aportes[aporte_idx]["valor_brl"]
            aporte_idx += 1
        p["capital_acumulado"] = round(total_investido, 2)

    # Fallback: sem aportes registrados, usa o primeiro ponto como base
    if not aportes:
        capital_base = pontos[0]["valor_brl"] if pontos else 0.0
        for p in pontos:
            p["capital_acumulado"] = round(capital_base, 2)

    # Ajusta valor de dias históricos onde aportes chegaram após o snapshot do bot.
    # Ex: PIX creditado após o primeiro ciclo do dia — stats capturou saldo sem o depósito.
    # Fórmula segura: max(valor_stats, min(capital_acumulado, valor_stats + aportes_do_dia))
    # — nunca reduz o valor; nunca ultrapassa o capital acumulado.
    aportes_por_dia: dict = {}
    for a in aportes:
        d = a["data"]
        aportes_por_dia[d] = round(aportes_por_dia.get(d, 0.0) + a["valor_brl"], 2)

    for p in pontos:
        if p.get("a_mercado"):
            continue
        aportes_dia = aportes_por_dia.get(p["data"], 0.0)
        if aportes_dia > 0:
            cap = p["capital_acumulado"]
            ajustado = max(p["valor_brl"], min(cap, round(p["valor_brl"] + aportes_dia, 2)))
            p["valor_brl"] = ajustado

    total_investido_final = sum(a["valor_brl"] for a in aportes) if aportes else (pontos[0]["valor_brl"] if pontos else 0.0)

    for p in pontos:
        base = p["capital_acumulado"]
        p["variacao_brl"] = round(p["valor_brl"] - base, 2)
        p["variacao_pct"] = round((p["valor_brl"] / base - 1) * 100, 2) if base else 0.0

    # Lucro realizado: soma de lucro_brl de todas as VENDAs nos stats (trades fechados)
    lucro_realizado_brl = 0.0
    for filename in arquivos:
        with open(os.path.join(stats_dir, filename)) as f:
            stats_item = json.load(f)
        for op in stats_item.get("operacoes", []):
            if op["tipo"] == "VENDA":
                lucro_realizado_brl += float(op.get("lucro_brl", 0.0))
    lucro_realizado_brl = round(lucro_realizado_brl, 2)

    # P&L não-realizado: posições abertas vs custo de entrada
    pnl_aberto_brl = 0.0
    if pontos:
        ultimo_ponto = pontos[-1]
        if ultimo_ponto.get("a_mercado"):
            # valor_mercado já calculado acima inclui posições a mercado
            # pnl_aberto = valor_mercado - (BRL disponível + custo das posições abertas)
            custo_posicoes_abertas = sum(p["custo_total"] for p in posicoes.values())
            try:
                pnl_aberto_brl = round(
                    ultimo_ponto["valor_brl"] - (saldo_brl_atual + custo_posicoes_abertas), 2
                )
            except Exception:
                pnl_aberto_brl = 0.0

    return {
        "capital_inicial": round(total_investido_final, 2),
        "total_investido": round(total_investido_final, 2),
        "lucro_realizado_brl": lucro_realizado_brl,
        "pnl_aberto_brl": pnl_aberto_brl,
        "pontos": pontos,
    }


@app.get("/bot/logs/stream")
async def bot_logs_stream(token: str = Query(...), historico: int = Query(default=100)):
    """SSE endpoint — token via query param (EventSource não suporta headers)."""
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or token != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")

    async def generator():
        # garante que o arquivo existe
        with open(_BOT_LOG_FILE, "a+") as _:
            pass

        with open(_BOT_LOG_FILE) as f:
            # envia histórico: lê as últimas N linhas e volta para essa posição
            todas = f.readlines()
            for linha in todas[-historico:]:
                texto = linha.rstrip("\n")
                if texto:
                    yield f"data: {texto}\n\n"

            # continua tail a partir do fim atual do arquivo
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
