"""Rotas do bot BRL — status, posições, stats, saldos, bot control, performance."""
import asyncio
import json
import os
import signal
import subprocess
import sys
from datetime import date, timedelta
from typing import Optional

from binance import Client as BinanceClient
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)

from infra.stats_store import carregar_stats_do_dia, calcular_resumo
from infra.reserva_store import estado_inicial
from pares import listar_pares
from api.deps import (
    _verificar_token,
    _stats_dir,
    _reserva_file,
    _status_file,
    _arquivo_posicao_par,
    _arquivo_stats,
    _carregar_aportes,
    _bot_pid,
    _bot_rodando,
    _bot_pid_efetivo,
    BotParams,
    _BOT_PID_FILE,
    _BOT_LOG_FILE,
)

router = APIRouter()


@router.get("/status", dependencies=[Depends(_verificar_token)])
def get_status():
    arquivo = _status_file()
    if not os.path.exists(arquivo):
        return {"rodando": False, "ultimo_ciclo": None, "versao": None}
    with open(arquivo) as f:
        return json.load(f)


@router.get("/posicoes", dependencies=[Depends(_verificar_token)])
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


@router.get("/stats/dia", dependencies=[Depends(_verificar_token)])
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


@router.get("/operacoes", dependencies=[Depends(_verificar_token)])
def get_operacoes(data: str = Query(default=None)):
    if data is None:
        data = date.today().strftime("%Y-%m-%d")
    arquivo = _arquivo_stats(data)
    if not os.path.exists(arquivo):
        return []
    with open(arquivo) as f:
        stats = json.load(f)
    return stats.get("operacoes", [])


@router.get("/reserva", dependencies=[Depends(_verificar_token)])
def get_reserva():
    arquivo = _reserva_file()
    if not os.path.exists(arquivo):
        return estado_inicial()
    with open(arquivo) as f:
        return json.load(f)


@router.get("/saldos", dependencies=[Depends(_verificar_token)])
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


@router.get("/cotacao", dependencies=[Depends(_verificar_token)])
def get_cotacao():
    api_key = os.getenv("KEY_BINANCE", "")
    api_secret = os.getenv("SECRET_BINANCE", "")
    cliente = BinanceClient(api_key, api_secret)
    ticker = cliente.get_symbol_ticker(symbol="USDTBRL")
    return {"usd_brl": float(ticker["price"])}


@router.get("/candles/{simbolo}", dependencies=[Depends(_verificar_token)])
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


@router.post("/bot/iniciar", dependencies=[Depends(_verificar_token)])
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

    os.makedirs(os.path.dirname(_BOT_LOG_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(_BOT_PID_FILE), exist_ok=True)
    log_file = open(_BOT_LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "-u", os.path.join(_ROOT, "robo_cripto.py")],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=_ROOT,
        env=env,
        start_new_session=True,
    )
    log_file.close()

    with open(_BOT_PID_FILE, "w") as f:
        f.write(str(proc.pid))

    return {"ok": True, "pid": proc.pid}


@router.post("/bot/parar", dependencies=[Depends(_verificar_token)])
def bot_parar():
    if not _bot_rodando():
        raise HTTPException(status_code=409, detail="Bot não está rodando")
    pid = _bot_pid()
    os.kill(pid, signal.SIGTERM)
    if os.path.exists(_BOT_PID_FILE):
        os.remove(_BOT_PID_FILE)
    return {"ok": True}


@router.get("/bot/info", dependencies=[Depends(_verificar_token)])
def bot_info():
    return {"rodando": _bot_rodando(), "pid": _bot_pid_efetivo()}


@router.get("/bot/logs", dependencies=[Depends(_verificar_token)])
def bot_logs(linhas: int = Query(default=100)):
    if not os.path.exists(_BOT_LOG_FILE):
        return {"linhas": []}
    with open(_BOT_LOG_FILE) as f:
        todas = f.readlines()
    return {"linhas": [l.rstrip("\n") for l in todas[-linhas:]]}


@router.get("/bot/logs/stream")
async def bot_logs_stream(token: str = Query(...), historico: int = Query(default=100)):
    """SSE endpoint — token via query param (EventSource não suporta headers)."""
    token_esperado = os.getenv("API_TOKEN", "")
    if not token_esperado or token != token_esperado:
        raise HTTPException(status_code=401, detail="Token inválido")

    async def generator():
        with open(_BOT_LOG_FILE, "a+") as _:
            pass

        with open(_BOT_LOG_FILE) as f:
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


@router.get("/performance", dependencies=[Depends(_verificar_token)])
def get_performance(periodo: str = Query(default="mes")):
    import yfinance as yf

    hoje = date.today()
    dias = {"dia": 1, "semana": 7, "mes": 30}.get(periodo, 30)
    inicio = hoje - timedelta(days=dias)

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

    cdi_anual = 0.1375
    cdi_115_diario = (1 + cdi_anual * 1.15) ** (1 / 252) - 1
    cdi_series, acum = [], 1.0
    for i, p in enumerate(bot_series):
        cdi_series.append({"data": p["data"], "pct": round((acum - 1) * 100, 4)})
        acum *= (1 + cdi_115_diario)

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


@router.patch("/stats/{data_str}/saldo", dependencies=[Depends(_verificar_token)])
def patch_saldo_dia(data_str: str, body: dict):
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


@router.get("/portfolio/evolucao", dependencies=[Depends(_verificar_token)])
def get_portfolio_evolucao():
    """Retorna a evolução diária do portfolio: BRL + posições abertas."""
    stats_dir = _stats_dir()
    if not os.path.exists(stats_dir):
        return {"capital_inicial": 0, "pontos": []}

    arquivos = sorted(
        f for f in os.listdir(stats_dir)
        if f.endswith(".json") and f != "aportes.json"
    )
    if not arquivos:
        return {"capital_inicial": 0, "pontos": []}

    posicoes: dict = {}
    pontos = []

    for filename in arquivos:
        data_str = filename[:-5]
        with open(os.path.join(stats_dir, filename)) as f:
            stats = json.load(f)

        saldo_brl = stats.get("saldo_inicial_brl", 0.0)
        custo_posicoes = sum(p["custo_total"] for p in posicoes.values())
        valor_dia = round(saldo_brl + custo_posicoes, 2)

        pontos.append({"data": data_str, "valor_brl": valor_dia, "a_mercado": False})

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
                    valor_posicoes_mercado += pos["custo_total"]

        valor_mercado = round(saldo_brl_atual + valor_posicoes_mercado, 2)

        if pontos and pontos[-1]["data"] == hoje:
            pontos[-1]["valor_brl"] = valor_mercado
            pontos[-1]["a_mercado"] = True
        else:
            pontos.append({"data": hoje, "valor_brl": valor_mercado, "a_mercado": True})
    except Exception:
        pass

    aportes = _carregar_aportes()
    total_investido = 0.0
    aporte_idx = 0

    for p in pontos:
        while aporte_idx < len(aportes) and aportes[aporte_idx]["data"] <= p["data"]:
            total_investido += aportes[aporte_idx]["valor_brl"]
            aporte_idx += 1
        p["capital_acumulado"] = round(total_investido, 2)

    if not aportes:
        capital_base = pontos[0]["valor_brl"] if pontos else 0.0
        for p in pontos:
            p["capital_acumulado"] = round(capital_base, 2)

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

    lucro_realizado_brl = 0.0
    for filename in arquivos:
        with open(os.path.join(stats_dir, filename)) as f:
            stats_item = json.load(f)
        for op in stats_item.get("operacoes", []):
            if op["tipo"] == "VENDA":
                lucro_realizado_brl += float(op.get("lucro_brl", 0.0))
    lucro_realizado_brl = round(lucro_realizado_brl, 2)

    pnl_aberto_brl = 0.0
    if pontos:
        ultimo_ponto = pontos[-1]
        if ultimo_ponto.get("a_mercado"):
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
