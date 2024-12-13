import pandas as pd
import os 
import time 
from binance.client import Client
from binance.enums import *

from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("KEY_BINANCE")
secret_key = os.getenv("SECRET_BINANCE")

cliente_binance = Client(api_key, secret_key)

conta = cliente_binance.get_account()

for ativo in conta["balances"]:

    if float(ativo["free"]) > 0:
        
        print(ativo)


order = cliente_binance.create_order(
                            symbol='SOLBRL',
                            side=SIDE_BUY,
                            type=ORDER_TYPE_MARKET,
                            quantity=0.015)

print(order)

conta = cliente_binance.get_account()

for ativo in conta["balances"]:

    if float(ativo["free"]) > 0:
        
        print(ativo)
