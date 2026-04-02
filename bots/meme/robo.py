"""Bot Meme — orquestrador principal (Scanner + MA crossover + RSI + trailing stop, USDT)."""
import json
import logging
import logging.handlers
import os
import signal
import tempfile
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_DOWN

import pandas as pd
from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
from dotenv import load_dotenv

from infra.binance_client import criar_cliente_sincronizado
from infra.persistencia import salvar_posicao, carregar_posicao
from infra.stats_store import (
    iniciar_stats_do_dia,
    registrar_compra,
    registrar_venda,
    calcular_resumo,
    carregar_stats_do_dia,
)
from infra.notificacao import enviar_whatsapp
from core.risco import (
    verificar_breakeven,
    atualizar_trailing_stop,
    verificar_trailing_stop,
    verificar_take_profit,
)
from bots.meme.config import (
    BOT_ID,
    PERIODO_CANDLE,
    CANDLES_HISTORICO,
    INTERVALO_SCANNER_S,
    CAPITAL_USDT,
    PERCENTUAL_COMPRA,
    TAKE_PROFIT_PCT,
    STOP_PCT_MIN,
    ATR_MULTIPLICADOR,
    BREAKEVEN_GATILHO,
    BREAKEVEN_FOLGA,
    SCORE_MINIMO,
    STOP_PORTFOLIO_PCT,
    LIMITE_DIARIO_PCT,
    MAX_POSICOES,
    MAX_TENTATIVAS,
    POSICAO_FILE,
    STATS_DIR,
    APORTES_FILE,
    RESERVA_FILE,
    BLOQUEIO_FILE,
    STATUS_FILE,
    LOG_FILE,
)
from bots.meme.scanner import scan_melhor, scan_todos
from bots.meme.estrategia import avaliar_sinal_meme, calcular_stop_inicial

load_dotenv()

logger = logging.getLogger(__name__)

_executando = True


def _signal_handler(sig, frame):
    global _executando
    logger.info("[meme] Sinal %s recebido. Encerrando...", sig)
    _executando = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ─── Aportes ────────────────────────────────────────────────────────────────

def _carregar_dados_aportes() -> dict:
    """Carrega stats_meme/aportes.json."""
    if not os.path.exists(APORTES_FILE):
        return {"confirmados": [], "rejeitados": []}
    with open(APORTES_FILE) as f:
        dados = json.load(f)
    if isinstance(dados, list):
        return {"confirmados": dados, "rejeitados": []}
    return dados


def _salvar_dados_aportes(dados: dict) -> None:
    """Salva stats_meme/aportes.json de forma atômica."""
    dir_ = os.path.dirname(APORTES_FILE) or "."
    os.makedirs(dir_, exist_ok=True)
    dados["confirmados"] = sorted(dados["confirmados"], key=lambda x: x.get("data", ""))
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f, indent=2)
        os.replace(tmp, APORTES_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def _aportes_confirmados_usdt() -> float:
    """Soma total de aportes confirmados em USDT."""
    dados = _carregar_dados_aportes()
    confirmados = dados.get("confirmados", [])
    total = sum(float(a.get("valor_usdt", 0)) for a in confirmados)
    return total


def _capital_em_posicao(cliente) -> float:
    """Retorna o valor em USDT da posição aberta atual (se houver)."""
    estado = carregar_posicao(arquivo=POSICAO_FILE)
    if not estado.get("posicao") or not estado.get("preco_entrada"):
        return 0.0

    simbolo = estado.get("simbolo")
    if not simbolo:
        return 0.0

    try:
        ativo = simbolo.replace("USDT", "")
        conta = cliente.get_account()
        for item in conta["balances"]:
            if item["asset"] == ativo:
                saldo = float(item["free"]) + float(item["locked"])
                if saldo > 0:
                    ticker = cliente.get_symbol_ticker(symbol=simbolo)
                    preco = float(ticker["price"])
                    return saldo * preco
    except Exception as e:
        logger.error("[meme][capital] Erro ao calcular capital em posição: %s", e)

    return 0.0


def _saldo_para_bot(saldo_usdt: float) -> float:
    """Limita o saldo USDT disponível para o bot ao capital autorizado.

    Regra:
    1. Total de aportes confirmados em USDT
    2. Capital máximo = min(CAPITAL_USDT, total_aportes_usdt)
    3. Disponível = capital_max - capital_em_posicao
    4. Retorna min(saldo_real, disponivel)
    """
    total_aportes = _aportes_confirmados_usdt()
    capital_max = min(CAPITAL_USDT, total_aportes)
    # capital_em_posicao não está disponível aqui sem cliente, já aplicado em ciclo
    disponivel = max(0.0, capital_max)
    resultado = min(saldo_usdt, disponivel)
    if resultado < saldo_usdt:
        logger.info(
            "[meme][aporte] Saldo USDT: %.2f | Aportes: %.2f | Cap. máx: %.2f | Disponível bot: %.2f",
            saldo_usdt, total_aportes, capital_max, resultado,
        )
    return resultado


def _saldo_para_bot_com_posicao(saldo_usdt: float, capital_em_pos: float) -> float:
    """Versão completa que desconta capital já em posição."""
    total_aportes = _aportes_confirmados_usdt()
    capital_max = min(CAPITAL_USDT, total_aportes)
    disponivel = max(0.0, capital_max - capital_em_pos)
    resultado = min(saldo_usdt, disponivel)
    if resultado < saldo_usdt:
        logger.info(
            "[meme][aporte] USDT: %.2f | Aportes: %.2f | Cap.max: %.2f | Em posição: %.2f | Bot: %.2f",
            saldo_usdt, total_aportes, capital_max, capital_em_pos, resultado,
        )
    return resultado


# ─── Reserva / Reinvestimento ────────────────────────────────────────────────

def _carregar_reserva() -> dict:
    if not os.path.exists(RESERVA_FILE):
        return {"pnl_total_usdt": 0.0, "entradas": []}
    with open(RESERVA_FILE) as f:
        return json.load(f)


def _salvar_reserva(dados: dict) -> None:
    dir_ = os.path.dirname(RESERVA_FILE) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f, indent=2)
        os.replace(tmp, RESERVA_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def _registrar_lucro_reserva(lucro_usdt: float, timestamp: str) -> None:
    """Registra lucro na reserva e adiciona aporte se positivo."""
    if lucro_usdt <= 0:
        return
    reserva = _carregar_reserva()
    reserva["pnl_total_usdt"] = round(reserva.get("pnl_total_usdt", 0.0) + lucro_usdt, 6)
    entradas = reserva.get("entradas", [])
    entradas.append({"timestamp": timestamp, "lucro_usdt": round(lucro_usdt, 6)})
    reserva["entradas"] = entradas
    _salvar_reserva(reserva)

    # Adicionar como lucro_reinvestido nos aportes
    data_str = timestamp[:10]
    dados_aportes = _carregar_dados_aportes()
    dados_aportes["confirmados"].append({
        "data": data_str,
        "valor_usdt": round(lucro_usdt, 6),
        "fonte": "lucro_reinvestido",
    })
    _salvar_dados_aportes(dados_aportes)
    logger.info("[meme][reserva] Lucro reinvestido: +$%.4f USDT em %s", lucro_usdt, data_str)


# ─── Saldo e dados ──────────────────────────────────────────────────────────

def obter_saldo_usdt(cliente) -> float:
    """Retorna o saldo livre de USDT."""
    conta = cliente.get_account()
    for item in conta["balances"]:
        if item["asset"] == "USDT":
            return float(item["free"])
    return 0.0


def obter_saldo_ativo(cliente, ativo: str) -> float:
    """Retorna saldo livre de um ativo."""
    conta = cliente.get_account()
    for item in conta["balances"]:
        if item["asset"] == ativo:
            return float(item["free"])
    return 0.0


def pegando_dados(cliente, simbolo: str) -> pd.DataFrame:
    """Busca candles e retorna DataFrame padronizado."""
    try:
        candles = cliente.get_klines(symbol=simbolo, interval=PERIODO_CANDLE, limit=CANDLES_HISTORICO)
        df = pd.DataFrame(candles)
        df.columns = [
            "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
            "tempo_fechamento", "moedas_negociadas", "numero_trades",
            "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
        ]
        df = df[["maxima", "minima", "fechamento", "volume"]]
        for col in ("maxima", "minima", "fechamento", "volume"):
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        logger.error("[meme][%s] Erro ao buscar dados: %s", simbolo, e)
        return pd.DataFrame()


def obter_preco_atual(cliente, simbolo: str) -> float:
    ticker = cliente.get_symbol_ticker(symbol=simbolo)
    return float(ticker["price"])


def _obter_step_size(cliente, simbolo: str) -> str:
    """Obtém o step_size do símbolo para arredondamento de quantidade."""
    info = cliente.get_symbol_info(simbolo)
    for filtro in info["filters"]:
        if filtro["filterType"] == "LOT_SIZE":
            return filtro["stepSize"]
    return "0.01"


# ─── Controle de estado ──────────────────────────────────────────────────────

def _gravar_status(rodando: bool = True) -> None:
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    try:
        os.makedirs("run", exist_ok=True)
        dados = {
            "rodando": rodando,
            "pid": os.getpid(),
            "ultimo_ciclo": timestamp,
            "versao": "1.0.0",
            "bot": "meme",
        }
        fd, tmp = tempfile.mkstemp(dir="run", prefix=".tmp_meme_")
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f)
        os.replace(tmp, STATUS_FILE)
    except Exception as e:
        logger.error("[meme][status] Erro ao gravar status: %s", e)


def _bloquear_portfolio(horas: int = 24) -> None:
    bloqueio_ate = (pd.Timestamp.now(tz="America/Sao_Paulo") + pd.Timedelta(hours=horas)).isoformat()
    dados = {"bloqueio_ate": bloqueio_ate}
    dir_ = os.path.dirname(BLOQUEIO_FILE) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(dados, f)
        os.replace(tmp, BLOQUEIO_FILE)
    except Exception:
        os.unlink(tmp)
        raise


def _portfolio_bloqueado() -> bool:
    if not os.path.exists(BLOQUEIO_FILE):
        return False
    try:
        with open(BLOQUEIO_FILE) as f:
            dados = json.load(f)
        bloqueio_ate = pd.Timestamp(dados["bloqueio_ate"])
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
        if bloqueio_ate.tzinfo is None:
            bloqueio_ate = bloqueio_ate.tz_localize("America/Sao_Paulo")
        if agora < bloqueio_ate:
            logger.warning("[meme][portfolio] Bloqueado até %s.", bloqueio_ate.strftime("%Y-%m-%d %H:%M"))
            return True
        return False
    except Exception as e:
        logger.error("[meme][portfolio] Erro ao ler bloqueio: %s", e)
        return False


def _limite_diario_atingido() -> bool:
    """Retorna True se o prejuízo do dia ultrapassou LIMITE_DIARIO_PCT do capital."""
    hoje = date.today().strftime("%Y-%m-%d")
    arquivo = os.path.join(STATS_DIR, f"{hoje}.json")
    stats = carregar_stats_do_dia(arquivo=arquivo)
    if not stats:
        return False
    capital_inicial = stats.get("saldo_inicial_brl", 0.0)
    if capital_inicial <= 0:
        return False
    resumo = calcular_resumo(stats)
    lucro = resumo.get("lucro_total_brl", 0.0)
    limite = capital_inicial * LIMITE_DIARIO_PCT
    if lucro < -limite:
        logger.warning(
            "[meme][risco] Limite diário atingido: $%.4f (%.1f%%). Novas entradas bloqueadas.",
            lucro, lucro / capital_inicial * 100,
        )
        return True
    return False


# ─── Logging de operação ─────────────────────────────────────────────────────

def log_operacao(tipo: str, simbolo: str, quantidade: float, preco: float) -> None:
    try:
        os.makedirs("logs", exist_ok=True)
        with open(LOG_FILE, "a") as f:
            timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {tipo} {simbolo} | Qtd: {quantidade} | Preco: ${preco:.8f}\n")
    except Exception as e:
        logger.error("[meme] Erro ao gravar log de operação: %s", e)


# ─── Execução de ordens ──────────────────────────────────────────────────────

def executar_compra(cliente, resultado_scanner: dict, saldo_usdt: float) -> bool:
    """Executa ordem de compra para o melhor candidato do scanner."""
    simbolo = resultado_scanner["simbolo"]
    ativo = simbolo.replace("USDT", "")

    try:
        preco_atual = obter_preco_atual(cliente, simbolo)
        step_size = _obter_step_size(cliente, simbolo)

        valor_a_usar = saldo_usdt * PERCENTUAL_COMPRA
        if valor_a_usar <= 0:
            logger.warning("[meme][compra] Saldo insuficiente para compra (%.6f USDT).", valor_a_usar)
            return False

        quantidade_raw = valor_a_usar / preco_atual
        quantidade_fmt = float(
            Decimal(str(quantidade_raw)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
        )

        if quantidade_fmt <= 0:
            logger.warning("[meme][compra] Quantidade calculada é zero. Abortando.")
            return False

        client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
        ordem = cliente.create_order(
            symbol=simbolo,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade_fmt,
            newClientOrderId=client_order_id,
        )

        total_usdt = round(quantidade_fmt * preco_atual, 8)
        timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")

        log_operacao("COMPRA", simbolo, quantidade_fmt, preco_atual)

        hoje = date.today().strftime("%Y-%m-%d")
        arquivo_stats = os.path.join(STATS_DIR, f"{hoje}.json")
        registrar_compra(
            preco_atual, quantidade_fmt, total_usdt, timestamp,
            arquivo=arquivo_stats,
            par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
        )

        dados = pegando_dados(cliente, simbolo)
        stop_pct = calcular_stop_inicial(dados) if not dados.empty else STOP_PCT_MIN
        preco_maximo, stop_price = atualizar_trailing_stop(preco_atual, None, None, stop_pct)

        # Salvar posição com símbolo
        estado = {
            "posicao": True,
            "preco_entrada": preco_atual,
            "preco_maximo": preco_maximo,
            "stop_price": stop_price,
            "simbolo": simbolo,
            "quantidade": quantidade_fmt,
        }
        dir_ = os.path.dirname(POSICAO_FILE) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(estado, f)
            os.replace(tmp, POSICAO_FILE)
        except Exception:
            os.unlink(tmp)
            raise

        msg = (
            f"COMPRA {simbolo} [Meme Bot]\n"
            f"Score: {resultado_scanner['score']}/10\n"
            f"Qtd: {quantidade_fmt} {ativo}\n"
            f"Preco: ${preco_atual:.8f}\n"
            f"Stop inicial: ${stop_price:.8f} ({stop_pct*100:.1f}%)\n"
            f"Total: ${total_usdt:.4f} USDT"
        )
        logger.info(msg)
        enviar_whatsapp(msg)
        return True

    except Exception as e:
        logger.error("[meme][compra] Erro ao executar compra de %s: %s", simbolo, e)
        return False


def executar_venda(cliente, motivo: str = "Sinal de venda") -> bool:
    """Executa ordem de venda da posição atual."""
    estado = _carregar_posicao_meme()
    if not estado.get("posicao"):
        logger.warning("[meme][venda] Sem posição aberta para vender.")
        return False

    simbolo = estado.get("simbolo")
    if not simbolo:
        logger.error("[meme][venda] Símbolo não encontrado na posição.")
        return False

    ativo = simbolo.replace("USDT", "")
    preco_entrada = estado.get("preco_entrada")
    quantidade_original = estado.get("quantidade", 0.0)

    try:
        step_size = _obter_step_size(cliente, simbolo)
        saldo_ativo = obter_saldo_ativo(cliente, ativo)
        quantidade_fmt = float(
            Decimal(str(saldo_ativo)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
        )

        if quantidade_fmt <= 0:
            logger.warning("[meme][venda] Saldo de %s insuficiente (%.8f).", ativo, saldo_ativo)
            return False

        preco_atual = obter_preco_atual(cliente, simbolo)
        client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
        cliente.create_order(
            symbol=simbolo,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=quantidade_fmt,
            newClientOrderId=client_order_id,
        )

        total_usdt = round(quantidade_fmt * preco_atual, 8)
        timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")

        log_operacao("VENDA", simbolo, quantidade_fmt, preco_atual)

        hoje = date.today().strftime("%Y-%m-%d")
        arquivo_stats = os.path.join(STATS_DIR, f"{hoje}.json")
        registrar_venda(
            preco_atual, quantidade_fmt, total_usdt, preco_entrada, timestamp,
            arquivo=arquivo_stats,
            par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
        )

        # Limpar posição
        estado_vazio = {
            "posicao": False,
            "preco_entrada": None,
            "preco_maximo": None,
            "stop_price": None,
            "simbolo": None,
            "quantidade": 0.0,
        }
        dir_ = os.path.dirname(POSICAO_FILE) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(estado_vazio, f)
            os.replace(tmp, POSICAO_FILE)
        except Exception:
            os.unlink(tmp)
            raise

        lucro_usdt = total_usdt - (preco_entrada * quantidade_fmt) if preco_entrada else 0.0
        variacao_pct = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0.0

        msg = (
            f"VENDA {simbolo} [{motivo}] [Meme Bot]\n"
            f"Qtd: {quantidade_fmt} {ativo}\n"
            f"Preco: ${preco_atual:.8f}\n"
            f"Lucro: ${lucro_usdt:.4f} USDT ({variacao_pct:+.2f}%)\n"
            f"Total: ${total_usdt:.4f} USDT"
        )
        logger.info(msg)
        enviar_whatsapp(msg)

        # Reinvestir lucro se positivo
        if lucro_usdt > 0:
            _registrar_lucro_reserva(lucro_usdt, timestamp)

        return True

    except Exception as e:
        logger.error("[meme][venda] Erro ao executar venda: %s", e)
        return False


# ─── Posição ─────────────────────────────────────────────────────────────────

def _carregar_posicao_meme() -> dict:
    """Carrega posição meme com campos extras (simbolo, quantidade)."""
    if not os.path.exists(POSICAO_FILE):
        return {
            "posicao": False,
            "preco_entrada": None,
            "preco_maximo": None,
            "stop_price": None,
            "simbolo": None,
            "quantidade": 0.0,
        }
    with open(POSICAO_FILE) as f:
        dados = json.load(f)
    dados.setdefault("preco_maximo", None)
    dados.setdefault("stop_price", None)
    dados.setdefault("simbolo", None)
    dados.setdefault("quantidade", 0.0)
    return dados


def _salvar_posicao_meme(estado: dict) -> None:
    dir_ = os.path.dirname(POSICAO_FILE) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".tmp_")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(estado, f)
        os.replace(tmp, POSICAO_FILE)
    except Exception:
        os.unlink(tmp)
        raise


# ─── Monitoramento ──────────────────────────────────────────────────────────

def monitorar_posicao(cliente) -> None:
    """Verifica trailing stop, breakeven e take-profit para a posição aberta."""
    estado = _carregar_posicao_meme()
    if not estado.get("posicao"):
        return

    simbolo = estado.get("simbolo")
    if not simbolo:
        return

    preco_entrada = estado.get("preco_entrada")
    preco_maximo = estado.get("preco_maximo")
    stop_price = estado.get("stop_price")

    try:
        preco_atual = obter_preco_atual(cliente, simbolo)

        # Take-profit
        if preco_entrada and preco_atual >= preco_entrada * (1 + TAKE_PROFIT_PCT):
            variacao = (preco_atual / preco_entrada - 1) * 100
            logger.info("[meme][%s][tp] TAKE-PROFIT! %.8f (+%.2f%%)", simbolo, preco_atual, variacao)
            enviar_whatsapp(
                f"TAKE-PROFIT {simbolo} [Meme Bot]\n"
                f"Entrada: ${preco_entrada:.8f} | Atual: ${preco_atual:.8f}\n"
                f"Ganho: +{variacao:.2f}%"
            )
            executar_venda(cliente, motivo="Take-Profit")
            return

        # Trailing stop update + breakeven
        novo_maximo, novo_stop = atualizar_trailing_stop(
            preco_atual, preco_maximo, stop_price,
            (stop_price / preco_maximo - 1) * -1 if preco_maximo and stop_price else 0.03,
        )

        novo_stop_be = verificar_breakeven(
            preco_atual, preco_entrada, novo_stop,
            ativacao_pct=BREAKEVEN_GATILHO,
            margem_pct=BREAKEVEN_FOLGA,
        )
        if novo_stop_be is not None and novo_stop_be > novo_stop:
            novo_stop = novo_stop_be
            logger.info("[meme][%s][be] Break-even ativado! Stop → $.8f", simbolo, novo_stop)

        if novo_maximo != preco_maximo or novo_stop != stop_price:
            estado["preco_maximo"] = novo_maximo
            estado["stop_price"] = novo_stop
            _salvar_posicao_meme(estado)

        variacao_entrada = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
        logger.info(
            "[meme][%s] $.8f | entrada %+.2f%% | stop $.8f",
            simbolo, preco_atual, variacao_entrada, novo_stop,
        )

        # Trailing stop disparado
        if verificar_trailing_stop(preco_atual, novo_stop):
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            logger.info("[meme][%s][stop] TRAILING STOP! %.8f (%.2f%%)", simbolo, preco_atual, variacao)
            enviar_whatsapp(
                f"TRAILING STOP {simbolo} [Meme Bot]\n"
                f"Topo: ${novo_maximo:.8f} | Stop: ${novo_stop:.8f}\n"
                f"Atual: ${preco_atual:.8f} | Variacao: {variacao:.2f}%"
            )
            executar_venda(cliente, motivo="Trailing Stop")

    except Exception as e:
        logger.error("[meme][%s][stop] Erro ao monitorar: %s", simbolo, e)


# ─── Stop de portfolio ───────────────────────────────────────────────────────

def verificar_stop_portfolio(cliente) -> bool:
    """Verifica se o drawdown da posição atual excede STOP_PORTFOLIO_PCT."""
    estado = _carregar_posicao_meme()
    if not estado.get("posicao") or not estado.get("preco_entrada"):
        return False

    simbolo = estado.get("simbolo")
    if not simbolo:
        return False

    try:
        preco_atual = obter_preco_atual(cliente, simbolo)
        preco_entrada = estado["preco_entrada"]
        drawdown = (preco_atual - preco_entrada) / preco_entrada
        if drawdown < -STOP_PORTFOLIO_PCT:
            msg = (
                f"STOP DE PORTFOLIO [Meme Bot]\n"
                f"Drawdown: {drawdown*100:.1f}% (limite: -{STOP_PORTFOLIO_PCT*100:.0f}%)\n"
                f"Fechando posição. Bloqueio por 24h."
            )
            logger.warning(msg)
            enviar_whatsapp(msg)
            executar_venda(cliente, motivo="Stop de Portfolio")
            _bloquear_portfolio(horas=24)
            return True
    except Exception as e:
        logger.error("[meme][portfolio] Erro ao verificar: %s", e)
    return False


# ─── Ciclo principal ─────────────────────────────────────────────────────────

def ciclo(cliente) -> None:
    """Ciclo principal do bot meme."""
    _gravar_status()
    agora = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=== [Meme Bot] %s ===", agora)

    # Stats do dia
    hoje = date.today().strftime("%Y-%m-%d")
    arquivo_stats = os.path.join(STATS_DIR, f"{hoje}.json")
    saldo_usdt = obter_saldo_usdt(cliente)
    logger.info("[meme] USDT disponível: $%.4f", saldo_usdt)
    os.makedirs(STATS_DIR, exist_ok=True)
    iniciar_stats_do_dia(saldo_inicial_brl=saldo_usdt, arquivo=arquivo_stats)

    stats = carregar_stats_do_dia(arquivo=arquivo_stats)
    if stats:
        resumo = calcular_resumo(stats)
        logger.info("[meme] Dia: %d ops | Lucro: $%.4f | Acerto: %.0f%%",
                    resumo["total_operacoes"], resumo["lucro_total_brl"], resumo["taxa_acerto_pct"])

    # Monitorar posição existente
    monitorar_posicao(cliente)

    # Verificar stop de portfolio
    if verificar_stop_portfolio(cliente):
        return

    # Verificar posição atual
    estado = _carregar_posicao_meme()
    posicao_aberta = estado.get("posicao", False)

    if posicao_aberta:
        simbolo = estado.get("simbolo", "?")
        preco_entrada = estado.get("preco_entrada")
        preco_atual_val = None
        if simbolo and simbolo != "?":
            try:
                preco_atual_val = obter_preco_atual(cliente, simbolo)
            except Exception:
                pass

        dados = None
        if simbolo and simbolo != "?":
            dados = pegando_dados(cliente, simbolo)

        if dados is not None and not dados.empty:
            sinal = avaliar_sinal_meme(
                dados,
                posicao=True,
                preco_entrada=estado.get("preco_entrada"),
                stop_price=estado.get("stop_price"),
                preco_maximo=estado.get("preco_maximo"),
            )
            if sinal == "VENDER":
                executar_venda(cliente, motivo="Sinal de estratégia")
        return

    # Sem posição — procurar entrada
    if _portfolio_bloqueado():
        logger.info("[meme] Compra bloqueada: stop de portfolio ativo.")
        return

    if _limite_diario_atingido():
        logger.info("[meme] Compra bloqueada: limite de perda diária atingido.")
        return

    # Calcular capital em posição (deve ser 0 se chegou aqui, mas por segurança)
    capital_em_pos = _capital_em_posicao(cliente)
    saldo_bot = _saldo_para_bot_com_posicao(saldo_usdt, capital_em_pos)

    if saldo_bot <= 0:
        logger.info("[meme] Saldo insuficiente após aplicar limite de aportes ($%.4f).", saldo_bot)
        return

    logger.info("[meme] Executando scan do universo meme...")
    resultado = scan_melhor(cliente)
    if resultado is None:
        logger.info("[meme] Nenhum candidato com score >= %d.", SCORE_MINIMO)
        return

    logger.info("[meme] Candidato: %s (score=%d, RSI=%.1f, ADX=%.1f)",
                resultado["simbolo"], resultado["score"], resultado["rsi"], resultado["adx"])

    executar_compra(cliente, resultado, saldo_bot)


# ─── Validação e main ────────────────────────────────────────────────────────

def _validar_env() -> None:
    """Verifica que as variáveis de ambiente obrigatórias estão definidas."""
    ausentes = []
    for var in ("KEY_BINANCE", "SECRET_BINANCE"):
        if not os.getenv(var):
            ausentes.append(var)
    if ausentes:
        raise EnvironmentError(f"Variáveis de ambiente obrigatórias ausentes: {', '.join(ausentes)}")


def main() -> None:
    """Ponto de entrada do bot meme."""
    global _executando

    os.makedirs("logs", exist_ok=True)
    os.makedirs("run", exist_ok=True)
    os.makedirs(STATS_DIR, exist_ok=True)
    os.makedirs("posicoes", exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
            ),
        ],
    )

    _validar_env()

    api_key = os.getenv("KEY_BINANCE")
    secret_key = os.getenv("SECRET_BINANCE")

    logger.info("[meme] Bot iniciado. BOT_ID=%s, CAPITAL_USDT=%.2f", BOT_ID, CAPITAL_USDT)

    cliente = criar_cliente_sincronizado(api_key, secret_key)
    _executando = True

    while _executando:
        try:
            ciclo(cliente)
        except Exception as e:
            logger.error("[meme] Erro no ciclo: %s", e)
        finally:
            if _executando:
                logger.info("[meme] Aguardando %ds até próximo ciclo...", INTERVALO_SCANNER_S)
                for _ in range(INTERVALO_SCANNER_S):
                    if not _executando:
                        break
                    time.sleep(1)

    _gravar_status(rodando=False)
    logger.info("[meme] Bot encerrado.")
