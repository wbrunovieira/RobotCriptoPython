import pandas as pd
import os 
import time 
from binance.client import Client
from binance.enums import *
from decimal import Decimal, ROUND_DOWN

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")

cliente_binance = Client(api_key, secret_key)

codigo_operado = "SOLBRL"
ativo_operado = "SOL"
periodo_candle = Client.KLINE_INTERVAL_1HOUR
quantidade = 0.015


def pegando_dados(codigo, intervalo):
    try:
        candles = cliente_binance.get_klines(symbol=codigo, interval=intervalo, limit=1000)
        precos = pd.DataFrame(candles)
        precos.columns = ["tempo_abertura", "abertura", "maxima", "minima", "fechamento", "volume", "tempo_fechamento", "moedas_negociadas", "numero_trades",
                          "volume_ativo_base_compra", "volume_ativo_cotação", "-"]
        precos = precos[["fechamento", "tempo_fechamento"]]
        precos["tempo_fechamento"] = pd.to_datetime(precos["tempo_fechamento"], unit="ms").dt.tz_localize("UTC")
        precos["tempo_fechamento"] = precos["tempo_fechamento"].dt.tz_convert("America/Sao_Paulo")
    except Exception as e:
        print(f"Erro ao pegar dados: {e}")
        precos = pd.DataFrame()
    return precos

def estrategia_trade(dados, codigo_ativo, ativo_operado, quantidade, posicao):
    try:
        dados["media_rapida"] = dados["fechamento"].rolling(window=7).mean()
        dados["media_devagar"] = dados["fechamento"].rolling(window=40).mean()

        ultima_media_rapida = dados["media_rapida"].iloc[-1]
        ultima_media_devagar = dados["media_devagar"].iloc[-1]

        print(f"Última Média Rápida: {ultima_media_rapida} | Última Média Devagar: {ultima_media_devagar}")

        conta = cliente_binance.get_account()
        for ativo in conta["balances"]:
            if ativo["asset"] == ativo_operado:
                quantidade_atual = float(ativo["free"])

        if ultima_media_rapida > ultima_media_devagar:
            if posicao == False:
                order = cliente_binance.create_order(
                    symbol=codigo_ativo,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantidade
                )
                print("COMPROU O ATIVO")
                log_operacao("COMPROU", ativo_operado, quantidade)
                posicao = True

        elif ultima_media_rapida < ultima_media_devagar:
            if posicao == True:
                quantidade_formatada = Decimal(quantidade_atual).quantize(Decimal('0.0001'), rounding=ROUND_DOWN)
                order = cliente_binance.create_order(
                    symbol=codigo_ativo,
                    side=SIDE_SELL,
                    type=ORDER_TYPE_MARKET,
                    quantity=float(quantidade_formatada)
                )
                print("VENDEU O ATIVO")
                log_operacao("VENDEU", ativo_operado, quantidade_formatada)
                posicao = False

    except Exception as e:
        print(f"Erro na função de estratégia: {e}")

    return posicao

def log_operacao(tipo_operacao, ativo, quantidade):
    """Registra as operações de compra e venda em um arquivo de log."""
    try:
        with open("log_operacoes.txt", "a") as f:
            timestamp = pd.Timestamp.now(tz='America/Sao_Paulo').strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[{timestamp}] {tipo_operacao} o ativo {ativo} - Quantidade: {quantidade}\n")
    except Exception as e:
        print(f"Erro ao gravar o log: {e}")

try:
    posicao_atual = False
    while True:
        print("\n🔍 Verificando os saldos na Binance...")
        conta = cliente_binance.get_account()
        for ativo in conta["balances"]:
            if float(ativo["free"]) > 0:
                print(f"Saldo: {ativo['asset']} - Livre: {ativo['free']} - Bloqueado: {ativo['locked']}")

        print(f"Status da posição: {'COMPRADO' if posicao_atual else 'NÃO COMPRADO'}")

        dados_atualizados = pegando_dados(codigo=codigo_operado, intervalo=periodo_candle)
        posicao_atual = estrategia_trade(dados_atualizados, codigo_ativo=codigo_operado, 
                                         ativo_operado=ativo_operado, quantidade=quantidade, posicao=posicao_atual)
        
        print(f"Iniciando espera de 1 hora às {pd.Timestamp.now(tz='America/Sao_Paulo')}")
        time.sleep(60 * 60)
except KeyboardInterrupt:
    print("Robô encerrado pelo usuário.")
