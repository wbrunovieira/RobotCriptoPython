import pandas as pd
import os
import time
import signal
import threading
from binance.enums import *
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

from persistencia import salvar_posicao, carregar_posicao
from conexao import criar_cliente_sincronizado
from estrategia import (
    calcular_quantidade,
    avaliar_sinal,
    verificar_lucro_minimo,
    atualizar_trailing_stop,
    verificar_trailing_stop,
    verificar_take_profit,
    contar_posicoes_abertas,
    calcular_rsi,
    stop_pct_por_atr,
    verificar_breakeven,
)
from notificacao import enviar_whatsapp
from stats import iniciar_stats_do_dia, registrar_compra, registrar_venda, calcular_resumo, carregar_stats_do_dia
from reserva import registrar_lucro, calcular_conversao, registrar_conversao
from pares import listar_pares, arquivo_posicao, calcular_saldo_disponivel, consolidar_resumo

load_dotenv()

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")

BOT_ID = os.getenv("BOT_ID", "MACross1")  # identifica este bot nas ordens da Binance

PERIODO_CANDLE = os.getenv("BOT_PERIODO_CANDLE", "1h")
STOP_PCT = float(os.getenv("BOT_STOP_PCT", "0.015"))
TAKE_PROFIT_PCT = float(os.getenv("BOT_TAKE_PROFIT_PCT", "0.03"))
TETO_SALDO_PCT = float(os.getenv("BOT_TETO_SALDO_PCT", "0.60"))
MAX_POSICOES = int(os.getenv("BOT_MAX_POSICOES", "3"))
PERCENTUAL_COMPRA = 0.90  # dentro do teto, usa 90%
STOP_PORTFOLIO_PCT = float(os.getenv("BOT_STOP_PORTFOLIO_PCT", "0.05"))  # drawdown máximo do portfolio
_BLOQUEIO_PORTFOLIO_FILE = "bloqueio_portfolio.json"
MAX_TENTATIVAS = 3
INTERVALO_MONITORAMENTO = int(os.getenv("BOT_INTERVALO_MONITORAMENTO", "60"))
_intervalo_estrategia_min = int(os.getenv("BOT_INTERVALO_ESTRATEGIA_MIN", "15"))
INTERVALO_ESTRATEGIA = _intervalo_estrategia_min * 60


def _params_atuais() -> dict:
    return {
        "bot_id": BOT_ID,
        "take_profit_pct": TAKE_PROFIT_PCT,
        "stop_pct": STOP_PCT,
        "teto_saldo_pct": TETO_SALDO_PCT,
        "percentual_compra": PERCENTUAL_COMPRA,
        "periodo_candle": PERIODO_CANDLE,
        "intervalo_monitoramento_s": INTERVALO_MONITORAMENTO,
        "intervalo_estrategia_min": _intervalo_estrategia_min,
        "max_posicoes": MAX_POSICOES,
    }


def criar_cliente():
    return criar_cliente_sincronizado(api_key, secret_key)


def pegando_dados(cliente, codigo, intervalo):
    try:
        candles = cliente.get_klines(symbol=codigo, interval=intervalo, limit=1000)
        precos = pd.DataFrame(candles)
        precos.columns = [
            "tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume",
            "tempo_fechamento", "moedas_negociadas", "numero_trades",
            "volume_ativo_base_compra", "volume_ativo_cotacao", "-",
        ]
        precos = precos[["maxima", "minima", "fechamento", "tempo_fechamento"]]
        precos["tempo_fechamento"] = (
            pd.to_datetime(precos["tempo_fechamento"], unit="ms")
            .dt.tz_localize("UTC")
            .dt.tz_convert("America/Sao_Paulo")
        )
        for col in ("maxima", "minima", "fechamento"):
            precos[col] = precos[col].astype(float)
        return precos
    except Exception as e:
        print(f"[{codigo}] Erro ao pegar dados: {e}")
        return pd.DataFrame()


def obter_preco_atual(cliente, codigo):
    ticker = cliente.get_symbol_ticker(symbol=codigo)
    return float(ticker["price"])


def obter_saldos(cliente, ativos_extras=None):
    """Retorna saldo BRL e um dict {ativo: saldo} para cada ativo monitorado."""
    conta = cliente.get_account()
    ativos_monitorados = {"BRL"} | {p["ativo"] for p in listar_pares()}
    if ativos_extras:
        ativos_monitorados |= set(ativos_extras)

    saldos = {a: 0.0 for a in ativos_monitorados}
    for item in conta["balances"]:
        if item["asset"] in ativos_monitorados:
            saldos[item["asset"]] = float(item["free"])

    saldo_brl = saldos.pop("BRL", 0.0)
    return saldo_brl, saldos


def obter_posicao_real_par(cliente, ativo, step_size):
    """Verifica se há saldo real do ativo acima do step_size mínimo."""
    conta = cliente.get_account()
    minimo = float(step_size)
    for item in conta["balances"]:
        if item["asset"] == ativo:
            return float(item["free"]) >= minimo
    return False


def log_operacao(tipo, simbolo, quantidade, preco):
    try:
        with open("log_operacoes.txt", "a") as f:
            timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {tipo} {simbolo} | Qtd: {quantidade} | Preco: R${preco:.2f}\n")
    except Exception as e:
        print(f"Erro ao gravar log: {e}")


def _portfolio_bloqueado() -> bool:
    """Retorna True se o stop de portfolio foi acionado nas últimas 24h."""
    import json as _json
    if not os.path.exists(_BLOQUEIO_PORTFOLIO_FILE):
        return False
    try:
        with open(_BLOQUEIO_PORTFOLIO_FILE) as f:
            dados = _json.load(f)
        bloqueio_ate = pd.Timestamp(dados["bloqueio_ate"])
        agora = pd.Timestamp.now(tz="America/Sao_Paulo")
        if bloqueio_ate.tzinfo is None:
            bloqueio_ate = bloqueio_ate.tz_localize("America/Sao_Paulo")
        if agora < bloqueio_ate:
            print(f"[portfolio] Bloqueado até {bloqueio_ate.strftime('%Y-%m-%d %H:%M')}.")
            return True
        return False
    except Exception:
        return False


def _bloquear_portfolio(horas: int = 24):
    import json as _json
    bloqueio_ate = (pd.Timestamp.now(tz="America/Sao_Paulo") + pd.Timedelta(hours=horas)).isoformat()
    with open(_BLOQUEIO_PORTFOLIO_FILE, "w") as f:
        _json.dump({"bloqueio_ate": bloqueio_ate}, f)


def _verificar_alta_forte(cliente, simbolo: str, preco_atual: float) -> bool:
    """Retorna True se MA9 > MA21, preço acima da MA50, RSI > 55 e volume acima da média."""
    try:
        dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
        if dados.empty or len(dados) < 50:
            return False
        fech = dados["fechamento"].astype(float)
        ma9 = fech.rolling(9).mean().iloc[-1]
        ma21 = fech.rolling(21).mean().iloc[-1]
        ma50 = fech.rolling(50).mean().iloc[-1]
        rsi = calcular_rsi(fech)
        # Confirma volume: candle atual deve estar 30% acima da média de 20 candles
        volume_forte = True
        if "volume" in dados.columns and len(dados) >= 21:
            vol = dados["volume"].astype(float)
            volume_forte = float(vol.iloc[-1]) > float(vol.rolling(20).mean().iloc[-1]) * 1.3
        return bool(ma9 > ma21 and preco_atual > ma50 and rsi > 55 and volume_forte)
    except Exception:
        return False


def verificar_stop_portfolio(cliente) -> bool:
    """
    Calcula o drawdown não-realizado do portfolio.
    Se exceder STOP_PORTFOLIO_PCT, fecha todas as posições e bloqueia por 24h.
    Retorna True se acionado.
    """
    pares = listar_pares()
    saldo_brl, saldos = obter_saldos(cliente)
    pnl_total = 0.0
    capital_total = saldo_brl

    for par in pares:
        simbolo = par["simbolo"]
        ativo = par["ativo"]
        estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
        if not estado["posicao"] or not estado.get("preco_entrada"):
            continue
        saldo_ativo = saldos.get(ativo, 0.0)
        if saldo_ativo <= 0:
            continue
        try:
            preco_atual = obter_preco_atual(cliente, simbolo)
        except Exception:
            continue
        preco_entrada = estado["preco_entrada"]
        capital_total += saldo_ativo * preco_atual
        pnl_total += saldo_ativo * (preco_atual - preco_entrada)

    if capital_total <= 0:
        return False

    drawdown_pct = pnl_total / capital_total
    print(f"[portfolio] P&L não-realizado: R${pnl_total:.2f} ({drawdown_pct*100:.2f}% do capital)")

    if drawdown_pct < -STOP_PORTFOLIO_PCT:
        msg = (
            f"STOP DE PORTFOLIO\n"
            f"Drawdown: {drawdown_pct*100:.1f}% (limite: -{STOP_PORTFOLIO_PCT*100:.0f}%)\n"
            f"Fechando todas as posições. Bloqueio por 24h."
        )
        print(msg)
        enviar_whatsapp(msg)
        for par in pares:
            simbolo = par["simbolo"]
            ativo = par["ativo"]
            estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
            if estado["posicao"]:
                try:
                    preco_atual = obter_preco_atual(cliente, simbolo)
                    saldo_ativo = saldos.get(ativo, 0.0)
                    if saldo_ativo > 0:
                        executar_venda(cliente, par, saldo_ativo, preco_atual, motivo="Stop de Portfolio")
                except Exception as e:
                    print(f"[{simbolo}][portfolio] Erro ao fechar: {e}")
        _bloquear_portfolio(horas=24)
        return True

    return False


def executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct: float = None):
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    stop_pct = stop_pct if stop_pct is not None else STOP_PCT

    saldo_disponivel = calcular_saldo_disponivel(saldo_brl, TETO_SALDO_PCT)
    valor_a_usar = saldo_disponivel * PERCENTUAL_COMPRA
    quantidade_fmt = float(
        Decimal(str(valor_a_usar / preco_atual)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
    )

    client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
    ordem = cliente.create_order(
        symbol=simbolo,
        side=SIDE_BUY,
        type=ORDER_TYPE_MARKET,
        quantity=quantidade_fmt,
        newClientOrderId=client_order_id,
    )
    total_brl = round(quantidade_fmt * preco_atual, 2)
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    log_operacao("COMPRA", simbolo, quantidade_fmt, preco_atual)
    registrar_compra(
        preco_atual, quantidade_fmt, total_brl, timestamp,
        par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
    )
    preco_maximo, stop_price = atualizar_trailing_stop(preco_atual, None, None, stop_pct)
    salvar_posicao(True, preco_atual, preco_maximo=preco_maximo, stop_price=stop_price,
                   arquivo=arquivo_posicao(simbolo))
    msg = (
        f"COMPRA {ativo}\n"
        f"Qtd: {quantidade_fmt} {ativo}\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Stop inicial: R${stop_price:.2f} ({stop_pct*100:.1f}% ATR)\n"
        f"Total: R${total_brl:.2f} (teto: R${saldo_disponivel:.2f})"
    )
    print(msg)
    enviar_whatsapp(msg)
    return True


def executar_venda(cliente, par, saldo_ativo, preco_atual, motivo="Sinal de venda"):
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    quantidade_fmt = Decimal(str(saldo_ativo)).quantize(Decimal(step_size), rounding=ROUND_DOWN)
    client_order_id = f"{BOT_ID}-{simbolo}-{int(time.time() * 1000)}"
    cliente.create_order(
        symbol=simbolo,
        side=SIDE_SELL,
        type=ORDER_TYPE_MARKET,
        quantity=float(quantidade_fmt),
        newClientOrderId=client_order_id,
    )
    total_brl = round(float(quantidade_fmt) * preco_atual, 2)
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    preco_entrada = estado.get("preco_entrada")
    log_operacao("VENDA", simbolo, float(quantidade_fmt), preco_atual)
    registrar_venda(
        preco_atual, float(quantidade_fmt), total_brl, preco_entrada, timestamp,
        par=simbolo, bot_id=BOT_ID, order_id=client_order_id,
    )
    salvar_posicao(False, None, arquivo=arquivo_posicao(simbolo))

    stats = carregar_stats_do_dia()
    resumo = calcular_resumo(stats) if stats else {}
    lucro_op = total_brl - (preco_entrada * float(quantidade_fmt)) if preco_entrada else 0

    msg = (
        f"VENDA {ativo} ({motivo})\n"
        f"Qtd: {quantidade_fmt} {ativo}\n"
        f"Preco: R${preco_atual:.2f}\n"
        f"Lucro op: R${lucro_op:.2f}\n"
        f"Lucro dia: R${resumo.get('lucro_total_brl', 0):.2f} ({resumo.get('taxa_acerto_pct', 0):.0f}% acerto)"
    )
    print(msg)
    enviar_whatsapp(msg)

    _verificar_reserva_usdc(cliente, lucro_op, timestamp)
    return False


def _verificar_reserva_usdc(cliente, lucro_op: float, timestamp: str):
    try:
        estado = registrar_lucro(lucro_op)
        valor_conversao = calcular_conversao(estado["lucro_acumulado_brl"])
        if valor_conversao == 0.0:
            print(f"[reserva] Lucro acumulado: R${estado['lucro_acumulado_brl']:.2f} (aguardando R$30)")
            return
        ticker = cliente.get_symbol_ticker(symbol="USDCBRL")
        taxa_cambio = float(ticker["price"])
        quantidade_usdc = round(valor_conversao / taxa_cambio, 4)
        cliente.create_order(symbol="USDCBRL", side="BUY", type="MARKET", quoteOrderQty=valor_conversao)
        estado_novo = registrar_conversao(valor_conversao, quantidade_usdc, taxa_cambio, timestamp)
        msg = (
            f"RESERVA USDC\n"
            f"Convertido: R${valor_conversao:.2f} → {quantidade_usdc:.4f} USDC\n"
            f"Taxa: R${taxa_cambio:.4f}/USDC\n"
            f"Reserva total: {estado_novo['reserva_usdc']:.4f} USDC"
        )
        print(msg)
        enviar_whatsapp(msg)
    except Exception as e:
        print(f"[reserva] Erro na conversão USDC: {e}")


def monitorar_stop_par(cliente, par):
    """Checagem de take-profit e trailing stop para um par específico."""
    simbolo = par["simbolo"]
    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    if not estado["posicao"]:
        return

    try:
        preco_atual = obter_preco_atual(cliente, simbolo)
        preco_maximo = estado["preco_maximo"]
        stop_price = estado["stop_price"]
        preco_entrada = estado["preco_entrada"]

        # --- Take-profit: vende ao atingir +TAKE_PROFIT_PCT ---
        if verificar_take_profit(preco_atual, preco_entrada, TAKE_PROFIT_PCT):
            variacao = ((preco_atual / preco_entrada) - 1) * 100

            # TP adaptativo: em alta forte (MA9>MA21, preço>MA50, RSI>55), mantém posição
            if _verificar_alta_forte(cliente, simbolo, preco_atual):
                print(f"[{simbolo}][tp] TP +{variacao:.2f}% atingido | alta forte — trailing stop continua.")
                return

            print(f"[{simbolo}][tp] TAKE-PROFIT! Preco: R${preco_atual:.2f} (+{variacao:.2f}%)")
            enviar_whatsapp(
                f"TAKE-PROFIT {simbolo}\n"
                f"Entrada: R${preco_entrada:.2f} | Atual: R${preco_atual:.2f}\n"
                f"Ganho: +{variacao:.2f}%"
            )
            _, saldos = obter_saldos(cliente)
            executar_venda(cliente, par, saldos.get(par["ativo"], 0.0), preco_atual, motivo="Take-Profit")

            # Reavalia reentrada imediata: se ainda há sinal de compra, recompra
            saldo_brl, _ = obter_saldos(cliente)
            dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
            if not dados.empty:
                sinal = avaliar_sinal(dados, posicao=False, reentrada=True)
                if sinal == "COMPRAR":
                    stop_atr = stop_pct_por_atr(dados, stop_pct_min=STOP_PCT)
                    print(f"[{simbolo}][tp] Reentrada imediata após take-profit.")
                    executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct=stop_atr)
            return

        # --- Trailing stop: atualiza máximo e verifica queda ---
        novo_maximo, novo_stop = atualizar_trailing_stop(preco_atual, preco_maximo, stop_price, STOP_PCT)

        # status por par a cada checagem
        dist_stop = ((preco_atual / novo_stop) - 1) * 100 if novo_stop else 0
        dist_tp = ((preco_entrada * (1 + TAKE_PROFIT_PCT)) / preco_atual - 1) * 100 if preco_entrada else 0
        variacao_entrada = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
        print(
            f"[{simbolo}] R${preco_atual:.2f} | entrada {variacao_entrada:+.2f}% | "
            f"stop R${novo_stop:.2f} ({dist_stop:.1f}% acima) | "
            f"tp em {dist_tp:.1f}%"
        )

        # --- Break-even: quando lucro >= 1.5%, move stop para entrada + 0.1% ---
        novo_stop_be = verificar_breakeven(preco_atual, preco_entrada, novo_stop)
        if novo_stop_be is not None and novo_stop_be > novo_stop:
            novo_stop = novo_stop_be
            salvar_posicao(True, preco_entrada, preco_maximo=novo_maximo, stop_price=novo_stop,
                           arquivo=arquivo_posicao(simbolo))
            print(f"[{simbolo}][be] Break-even ativado! Stop → R${novo_stop:.2f}")
        elif novo_maximo != preco_maximo or novo_stop != stop_price:
            salvar_posicao(True, preco_entrada, preco_maximo=novo_maximo, stop_price=novo_stop,
                           arquivo=arquivo_posicao(simbolo))
            print(f"[{simbolo}][stop] ▲ Novo topo R${novo_maximo:.2f} → stop atualizado R${novo_stop:.2f}")

        if verificar_trailing_stop(preco_atual, novo_stop):
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            print(f"[{simbolo}][stop] TRAILING STOP! Preco: R${preco_atual:.2f} ({variacao:.2f}%)")
            enviar_whatsapp(
                f"TRAILING STOP {simbolo}\n"
                f"Topo: R${novo_maximo:.2f} | Stop: R${novo_stop:.2f}\n"
                f"Atual: R${preco_atual:.2f} | Variacao: {variacao:.2f}%"
            )
            _, saldos = obter_saldos(cliente)
            executar_venda(cliente, par, saldos.get(par["ativo"], 0.0), preco_atual, motivo="Trailing Stop")

            # Reavalia reentrada imediata: se ainda há sinal de compra, recompra
            saldo_brl, _ = obter_saldos(cliente)
            dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
            if not dados.empty:
                sinal = avaliar_sinal(dados, posicao=False, reentrada=True)
                if sinal == "COMPRAR":
                    stop_atr = stop_pct_por_atr(dados, stop_pct_min=STOP_PCT)
                    print(f"[{simbolo}][stop] Reentrada imediata após trailing stop.")
                    executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct=stop_atr)

    except Exception as e:
        print(f"[{simbolo}][stop] Erro: {e}")


def monitorar_stop(cliente):
    try:
        if verificar_stop_portfolio(cliente):
            return  # stop de portfolio acionado — não processa stops individuais
    except Exception as e:
        print(f"[portfolio][stop] Erro ao verificar stop de portfolio (rede?): {e}. Continuando stops individuais.")
    for par in listar_pares():
        monitorar_stop_par(cliente, par)


def ciclo_par(cliente, par, saldo_brl, saldo_ativo):
    """Avaliação completa de estratégia para um par."""
    simbolo = par["simbolo"]
    ativo = par["ativo"]
    step_size = par["step_size"]

    estado = carregar_posicao(arquivo=arquivo_posicao(simbolo))
    posicao = estado["posicao"]
    preco_entrada = estado["preco_entrada"]
    preco_maximo = estado["preco_maximo"]
    stop_price = estado["stop_price"]

    posicao_real = obter_posicao_real_par(cliente, ativo, step_size)
    if posicao_real != posicao:
        print(f"[{simbolo}] Divergencia: real={posicao_real} salvo={posicao}. Corrigindo.")
        posicao = posicao_real
        if not posicao_real:
            preco_entrada = preco_maximo = stop_price = None
        salvar_posicao(posicao, preco_entrada, preco_maximo=preco_maximo, stop_price=stop_price,
                       arquivo=arquivo_posicao(simbolo))

    print(f"[{simbolo}] {'COMPRADO' if posicao else 'NAO COMPRADO'}", end="")
    if preco_entrada:
        print(f" | Entrada: R${preco_entrada:.2f} | Stop: R${stop_price:.2f}", end="")
    print()

    dados = pegando_dados(cliente, simbolo, PERIODO_CANDLE)
    if dados.empty:
        print(f"[{simbolo}] Sem dados. Pulando.")
        return

    preco_atual = float(dados["fechamento"].iloc[-1])
    print(f"[{simbolo}] Preco: R${preco_atual:.2f}")

    pares_abertos = contar_posicoes_abertas(listar_pares())
    sinal = avaliar_sinal(dados, posicao, pares_abertos=pares_abertos, max_posicoes=MAX_POSICOES)

    if sinal == "COMPRAR":
        if _portfolio_bloqueado():
            print(f"[{simbolo}] Compra bloqueada: stop de portfolio ativo.")
        else:
            stop_atr = stop_pct_por_atr(dados, stop_pct_min=STOP_PCT)
            print(f"[{simbolo}] Stop ATR calculado: {stop_atr*100:.2f}%")
            executar_compra(cliente, par, saldo_brl, preco_atual, stop_pct=stop_atr)
    elif sinal == "VENDER":
        if verificar_lucro_minimo(preco_atual, preco_entrada):
            executar_venda(cliente, par, saldo_ativo, preco_atual)
        else:
            variacao = ((preco_atual / preco_entrada) - 1) * 100 if preco_entrada else 0
            print(f"[{simbolo}] Venda ignorada: lucro {variacao:.2f}% nao cobre taxas.")
    else:
        print(f"[{simbolo}] Sem sinal.")


def _gravar_status(rodando: bool = True):
    import json as _json
    timestamp = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("status.json", "w") as f:
            _json.dump({"rodando": rodando, "pid": os.getpid(), "ultimo_ciclo": timestamp, "versao": "1.0.0"}, f)
    except Exception:
        pass


def ciclo(cliente):
    _gravar_status()
    print(f"\n=== {pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M:%S')} ===")

    saldo_brl, saldos = obter_saldos(cliente)
    print(f"BRL disponivel: R${saldo_brl:.2f}")
    for ativo, saldo in saldos.items():
        if saldo > 0:
            print(f"  {ativo}: {saldo:.6f}")

    iniciar_stats_do_dia(saldo_inicial_brl=saldo_brl, parametros=_params_atuais())

    stats = carregar_stats_do_dia()
    if stats:
        resumo = calcular_resumo(stats)
        print(f"Dia: {resumo['total_operacoes']} ops | Lucro: R${resumo['lucro_total_brl']:.2f} | Acerto: {resumo['taxa_acerto_pct']:.0f}%")

    for par in listar_pares():
        saldo_ativo = saldos.get(par["ativo"], 0.0)
        ciclo_par(cliente, par, saldo_brl, saldo_ativo)
        # Atualiza saldo BRL após possível compra
        saldo_brl, saldos = obter_saldos(cliente)


_parar = threading.Event()


def _handler_sinal(signum, frame):
    if not _parar.is_set():
        print("\nSoft stop solicitado. Aguardando fim do ciclo atual...")
        _parar.set()


def _aguardar(segundos: int) -> bool:
    for _ in range(segundos):
        if _parar.is_set():
            return True
        time.sleep(1)
    return False


def main():
    signal.signal(signal.SIGINT, _handler_sinal)
    signal.signal(signal.SIGTERM, _handler_sinal)

    tentativas = 0
    cliente = criar_cliente()

    while not _parar.is_set():
        try:
            ciclo(cliente)
            tentativas = 0

            checks = INTERVALO_ESTRATEGIA // INTERVALO_MONITORAMENTO
            for i in range(checks):
                if _aguardar(INTERVALO_MONITORAMENTO):
                    break
                print(f"[{i+1}/{checks}] {pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%H:%M:%S')} checando stops...")
                monitorar_stop(cliente)

        except Exception as e:
            tentativas += 1
            espera = min(60 * tentativas, 300)
            print(f"Erro ({tentativas}/{MAX_TENTATIVAS}): {e}. Reconectando em {espera}s...")
            if tentativas >= MAX_TENTATIVAS:
                enviar_whatsapp(f"Bot com erros consecutivos: {e}")
                tentativas = 0
            if _aguardar(espera):
                break
            try:
                cliente = criar_cliente()
            except Exception as ce:
                print(f"Falha ao reconectar: {ce}. Tentando novamente no próximo ciclo.")

    print("Encerrando bot...")
    _gravar_status(rodando=False)
    try:
        enviar_whatsapp("Bot encerrado manualmente.")
    except Exception:
        pass
    print("Robo encerrado.")


if __name__ == "__main__":
    main()
