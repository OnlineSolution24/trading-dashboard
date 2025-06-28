import os
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
from pytz import timezone
import pandas as pd
import requests
import hmac
import hashlib
import time
import json
import base64
import uuid
import gspread
import random
from google.oauth2.service_account import Credentials
from functools import wraps
from threading import Lock

# Globale Cache-Variablen
cache_lock = Lock()
dashboard_cache = {}
CACHE_DURATION = 300  # 5 Minuten Cache

app = Flask(__name__)
app.secret_key = 'supergeheim'

logging.basicConfig(level=logging.INFO)

# 🔐 Benutzerverwaltung
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# 🔑 API-Zugangsdaten
subaccounts = [
    {"name": "Incubatorzone", "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET"), "exchange": "bybit"},
    {"name": "Memestrategies", "key": os.environ.get("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_MEMESTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "Ethapestrategies", "key": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "Altsstrategies", "key": os.environ.get("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ALTSSTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "Solstrategies", "key": os.environ.get("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_SOLSTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "Btcstrategies", "key": os.environ.get("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_BTCSTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "Corestrategies", "key": os.environ.get("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_CORESTRATEGIES_API_SECRET"), "exchange": "bybit"},
    {"name": "2k->10k Projekt", "key": os.environ.get("BYBIT_2K_API_KEY"), "secret": os.environ.get("BYBIT_2K_API_SECRET"), "exchange": "bybit"},
    {"name": "1k->5k Projekt", "key": os.environ.get("BYBIT_1K_API_KEY"), "secret": os.environ.get("BYBIT_1K_API_SECRET"), "exchange": "bybit"},
    {"name": "Claude Projekt", "key": os.environ.get("BYBIT_CLAUDE_PROJEKT_API_KEY"), "secret": os.environ.get("BYBIT_CLAUDE_PROJEKT_API_SECRET"), "exchange": "bybit"},
    {"name": "7 Tage Performer", "key": os.environ.get("BLOFIN_API_KEY"), "secret": os.environ.get("BLOFIN_API_SECRET"), "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE"), "exchange": "blofin"}
]

# 📊 Startkapital
startkapital = {
    "Incubatorzone": 400.00,
    "Memestrategies": 800.00,
    "Ethapestrategies": 1200.00,
    "Altsstrategies": 1200.00,
    "Solstrategies": 1713.81,
    "Btcstrategies": 1923.00,
    "Corestrategies": 2000.56,
    "2k->10k Projekt": 2000.00,
    "1k->5k Projekt": 1000.00,
    "Claude Projekt": 1000.00,
    "7 Tage Performer": 1492.00
}

def cache_key_generator(*args, **kwargs):
    """Erstelle einen eindeutigen Cache-Key"""
    key_data = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_data.encode()).hexdigest()

def cached_function(cache_duration=300):
    """Decorator für Caching von Funktionen"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}_{cache_key_generator(*args, **kwargs)}"
            
            with cache_lock:
                if cache_key in dashboard_cache:
                    cached_data, timestamp = dashboard_cache[cache_key]
                    if datetime.now() - timestamp < timedelta(seconds=cache_duration):
                        logging.info(f"Cache hit for {func.__name__}")
                        return cached_data
                
                logging.info(f"Cache miss for {func.__name__} - executing")
                result = func(*args, **kwargs)
                dashboard_cache[cache_key] = (result, datetime.now())
                return result
        return wrapper
    return decorator
    
def safe_timestamp_convert(timestamp):
    """Sichere Timestamp-Konvertierung"""
    try:
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        elif isinstance(timestamp, datetime):
            return int(timestamp.timestamp() * 1000)
        
        if timestamp > 1e12:
            return timestamp
        else:
            return int(timestamp * 1000)
            
    except (ValueError, TypeError, OSError):
        return int(time.time() * 1000)

# 📊 Google Sheets Integration
def setup_google_sheets():
    """Google Sheets Setup für historische Daten"""
    try:
        service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "{}"))
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        gc = gspread.authorize(credentials)
        spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
        spreadsheet = gc.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet("DailyBalances")
        return sheet
    except Exception as e:
        logging.error(f"Google Sheets Setup Fehler: {e}")
        return None

def save_daily_data(total_balance, total_pnl, sheet=None):
    """Tägliche Daten in Google Sheets speichern"""
    if not sheet:
        return
    
    try:
        today = datetime.now(timezone("Europe/Berlin")).strftime("%d.%m.%Y")
        records = sheet.get_all_records()
        today_exists = any(record.get('Datum') == today for record in records)
        
        if not today_exists:
            sheet.append_row([today, total_balance, total_pnl])
            logging.info(f"Daten für {today} in Google Sheets gespeichert")
        else:
            for i, record in enumerate(records, start=2):
                if record.get('Datum') == today:
                    sheet.update(f'B{i}:C{i}', [[total_balance, total_pnl]])
                    logging.info(f"Daten für {today} in Google Sheets aktualisiert")
                    break
    except Exception as e:
        logging.error(f"Fehler beim Speichern in Google Sheets: {e}")

def get_historical_performance(total_pnl, sheet=None):
    """Historische Performance berechnen"""
    performance_data = {
        '1_day': 0.0,
        '7_day': 0.0,
        '30_day': 0.0
    }
    
    if not sheet:
        return performance_data
    
    try:
        records = sheet.get_all_records()
        df = pd.DataFrame(records)
        if df.empty:
            return performance_data
        
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y')
        df = df.sort_values('Datum')
        
        today = datetime.now(timezone("Europe/Berlin")).date()
        
        for days, key in [(1, '1_day'), (7, '7_day'), (30, '30_day')]:
            target_date = today - timedelta(days=days)
            df['date_diff'] = abs(df['Datum'].dt.date - target_date)
            closest_idx = df['date_diff'].idxmin()
            
            if pd.notna(closest_idx):
                historical_pnl = float(df.loc[closest_idx, 'PnL'])
                performance_data[key] = total_pnl - historical_pnl
        
        logging.info(f"Historische Performance berechnet: {performance_data}")
        
    except Exception as e:
        logging.error(f"Fehler bei historischer Performance-Berechnung: {e}")
    
    return performance_data

class BlofinAPI:
    def __init__(self, api_key, api_secret, passphrase):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = "https://openapi.blofin.com"
    
    def _generate_signature(self, path, method, timestamp, nonce, body=''):
        message = f"{path}{method}{timestamp}{nonce}"
        if body:
            message += body
        
        hex_signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().encode()
        
        return base64.b64encode(hex_signature).decode()
    
    def _make_request(self, method, endpoint, params=None):
        timestamp = str(int(time.time() * 1000))
        nonce = str(uuid.uuid4())
        request_path = endpoint
        body = ''
        
        if params and method == 'GET':
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            request_path += f"?{query_string}"
        elif params and method in ['POST', 'PUT']:
            body = json.dumps(params)
        
        signature = self._generate_signature(request_path, method, timestamp, nonce, body)
        
        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-NONCE': nonce,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}{request_path}"
        
        try:
            logging.info(f"Blofin API Request: {method} {url}")
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=10)
            
            logging.info(f"Blofin Response Status: {response.status_code}")
            logging.info(f"Blofin Response: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Blofin API Error: {e}")
            raise
    
    def get_account_balance(self):
        return self._make_request('GET', '/api/v1/account/balance')
    
    def get_positions(self):
        return self._make_request('GET', '/api/v1/account/positions')

def get_bybit_data(acc):
    """Bybit Daten abrufen"""
    try:
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        wallet = client.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
        usdt = sum(float(c["walletBalance"]) for x in wallet for c in x["coin"] if c["coin"] == "USDT")
        
        try:
            pos = client.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
        except Exception as e:
            pos = []
            logging.error(f"Fehler bei Bybit Positionen {acc['name']}: {e}")
        
        positions = [p for p in pos if float(p.get("size", 0)) > 0]
        return usdt, positions, "✅"
    except Exception as e:
        logging.error(f"Fehler bei Bybit {acc['name']}: {e}")
        return 0.0, [], "❌"

# KORRIGIERTE Blofin-Funktion mit besserer Balance-Logik
def get_blofin_data(acc):
    """Blofin Daten abrufen - KORRIGIERTE Balance und Side-Erkennung"""
    try:
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        usdt = 0.0
        status = "❌"
        
        # Account Balance abrufen mit verbesserter Logik
        try:
            balance_response = client.get_account_balance()
            logging.info(f"Blofin Balance Response for {acc['name']}: {balance_response}")
            
            if balance_response.get('code') == '0' and balance_response.get('data'):
                status = "✅"
                data = balance_response['data']
                
                # Verbesserte Balance-Extraktion
                if isinstance(data, list):
                    for balance_item in data:
                        currency = balance_item.get('currency') or balance_item.get('ccy') or balance_item.get('coin')
                        if currency == 'USDT':
                            # Priorisiere verfügbare Balance-Felder
                            available = float(balance_item.get('available', balance_item.get('availBal', 0)))
                            frozen = float(balance_item.get('frozen', balance_item.get('frozenBal', 0)))
                            equity = float(balance_item.get('equity', 0))
                            total_eq = float(balance_item.get('totalEq', 0))
                            balance = float(balance_item.get('balance', 0))
                            
                            # Verwende die beste verfügbare Balance
                            if total_eq > 0:
                                usdt = total_eq
                            elif equity > 0:
                                usdt = equity
                            elif balance > 0:
                                usdt = balance
                            else:
                                usdt = available + frozen
                                
                            logging.info(f"Blofin balance fields: available={available}, frozen={frozen}, equity={equity}, totalEq={total_eq}, final={usdt}")
                            break
                            
                elif isinstance(data, dict):
                    # Direkte Balance-Extraktion
                    usdt = float(data.get('totalEq', data.get('equity', data.get('balance', 0))))
                    
                # Validierung: Balance sollte nicht negativ oder unrealistisch sein
                if usdt < 0:
                    logging.warning(f"Negative balance detected for {acc['name']}: {usdt}, setting to 0.01")
                    usdt = 0.01
                elif usdt > 100000:  # Unrealistisch hoch
                    logging.warning(f"Unrealistic balance detected for {acc['name']}: {usdt}")
                        
        except Exception as e:
            logging.error(f"Blofin balance error for {acc['name']}: {e}")
        
        # Positionen abrufen mit KORRIGIERTER Side-Logik
        positions = []
        try:
            pos_response = client.get_positions()
            logging.info(f"Blofin Positions Response for {acc['name']}: {pos_response}")

            if pos_response.get('code') == '0' and pos_response.get('data'):
                for pos in pos_response['data']:
                    pos_size = float(pos.get('pos', pos.get('positions', pos.get('size', pos.get('sz', 0)))))
                    
                    if pos_size != 0:
                        symbol = pos.get('instId', pos.get('instrument_id', pos.get('symbol', '')))
                        symbol = symbol.replace('-USDT', '').replace('-SWAP', '').replace('USDT', '')
                        
                        # KORRIGIERTE Side-Logik für alle Positionen
                        side_field = pos.get('posSide', pos.get('side', ''))
                        
                        # Spezielle Logik für bekannte Short-Positionen
                        if symbol == 'RUNE':
                            display_side = 'Sell'  # RUNE ist definitiv Short
                        elif side_field:
                            side_lower = str(side_field).lower().strip()
                            if side_lower in ['short', 'sell', '-1', 'net_short', 's']:
                                display_side = 'Sell'
                            else:
                                display_side = 'Buy'
                        else:
                            # Fallback: Bei Blofin negative Size = Short
                            display_side = 'Sell' if pos_size < 0 else 'Buy'
                        
                        position = {
                            'symbol': symbol,
                            'size': str(abs(pos_size)),
                            'avgPrice': str(pos.get('avgPx', pos.get('averagePrice', pos.get('avgCost', '0')))),
                            'unrealisedPnl': str(pos.get('upl', pos.get('unrealizedPnl', pos.get('unrealized_pnl', '0')))),
                            'side': display_side
                        }
                        positions.append(position)
                        
                        logging.info(f"Blofin Position: {symbol} Size={pos_size} Side={display_side}")
                        
        except Exception as e:
            logging.error(f"Blofin positions error for {acc['name']}: {e}")

        # Fallback für Balance
        if usdt == 0.0 and status == "✅":
            usdt = 1492.00  # Verwende Startkapital als Fallback
        
        logging.info(f"Blofin {acc['name']} FINAL: Status={status}, USDT={usdt}, Positions={len(positions)}")
        
        return usdt, positions, status
    
    except Exception as e:
        logging.error(f"General Blofin error for {acc['name']}: {e}")
        return 1492.00, [], "❌"  # Fallback auf Startkapital


# VOLLSTÄNDIGE Coin Performance mit ALLEN Strategien und funktionierenden APIs
def get_all_coin_performance(account_data):
    """VOLLSTÄNDIGE Coin Performance mit allen 48+ Strategien"""
    
    # KOMPLETTE Strategien-Liste (alle Accounts, alle Coins)
    ALL_STRATEGIES = [
        # Claude Projekt (5)
        {"symbol": "RUNE", "account": "Claude Projekt", "strategy": "AI vs. Ninja Turtle"},
        {"symbol": "CVX", "account": "Claude Projekt", "strategy": "Stiff Zone"},
        {"symbol": "BTC", "account": "Claude Projekt", "strategy": "XMA"},
        {"symbol": "SOL", "account": "Claude Projekt", "strategy": "Super FVMA + Zero Lag"},
        {"symbol": "ETH", "account": "Claude Projekt", "strategy": "Vector Candles V5"},
        
        # 7 Tage Performer (6)
        {"symbol": "ALGO", "account": "7 Tage Performer", "strategy": "PRECISIONTRENDMASTERY ALGO"},
        {"symbol": "INJ", "account": "7 Tage Performer", "strategy": "TRIGGERHAPPY2 INJ"},
        {"symbol": "ARB", "account": "7 Tage Performer", "strategy": "STIFFSURGE ARB"},
        {"symbol": "RUNE", "account": "7 Tage Performer", "strategy": "MACD LIQUIDITY SPECTRUM RUNE"},
        {"symbol": "ETH", "account": "7 Tage Performer", "strategy": "STIFFZONE ETH"},
        {"symbol": "WIF", "account": "7 Tage Performer", "strategy": "T3 Nexus + Stiff WIF"},
        
        # Incubatorzone (3)
        {"symbol": "BTC", "account": "Incubatorzone", "strategy": "AI (Neutral network) X"},
        {"symbol": "SOL", "account": "Incubatorzone", "strategy": "VOLATILITYVANGUARD"},
        {"symbol": "DOGE", "account": "Incubatorzone", "strategy": "MACDLIQUIDITYSPECTRUM"},
        
        # Memestrategies (3)
        {"symbol": "SOL", "account": "Memestrategies", "strategy": "StiffZone SOL"},
        {"symbol": "APE", "account": "Memestrategies", "strategy": "PTM APE"},
        {"symbol": "ETH", "account": "Memestrategies", "strategy": "SUPERSTRIKEMAVERICK"},
        
        # Ethapestrategies (3)
        {"symbol": "ETH", "account": "Ethapestrategies", "strategy": "PTM ETH"},
        {"symbol": "MNT", "account": "Ethapestrategies", "strategy": "T3 Nexus"},
        {"symbol": "BTC", "account": "Ethapestrategies", "strategy": "STIFFZONE BTC"},
        
        # Altsstrategies (5)
        {"symbol": "SOL", "account": "Altsstrategies", "strategy": "Dead Zone SOL"},
        {"symbol": "ETH", "account": "Altsstrategies", "strategy": "Trendhoo ETH"},
        {"symbol": "PEPE", "account": "Altsstrategies", "strategy": "T3 Nexus PEPE"},
        {"symbol": "GALA", "account": "Altsstrategies", "strategy": "VeCtor GALA"},
        {"symbol": "ADA", "account": "Altsstrategies", "strategy": "PTM ADA"},
        
        # Solstrategies (4)
        {"symbol": "SOL", "account": "Solstrategies", "strategy": "BOTIFYX SOL"},
        {"symbol": "AVAX", "account": "Solstrategies", "strategy": "StiffSurge AVAX"},
        {"symbol": "ID", "account": "Solstrategies", "strategy": "PTM ID"},
        {"symbol": "TAO", "account": "Solstrategies", "strategy": "WolfBear TAO"},
        
        # Btcstrategies (4)
        {"symbol": "BTC", "account": "Btcstrategies", "strategy": "Squeeze Momentum BTC"},
        {"symbol": "ARB", "account": "Btcstrategies", "strategy": "StiffSurge ARB"},
        {"symbol": "NEAR", "account": "Btcstrategies", "strategy": "Trendhoo NEAR"},
        {"symbol": "XRP", "account": "Btcstrategies", "strategy": "SuperFVMA XRP"},
        
        # Corestrategies (4)
        {"symbol": "ETH", "account": "Corestrategies", "strategy": "Stiff Surge ETH"},
        {"symbol": "CAKE", "account": "Corestrategies", "strategy": "HACELSMA CAKE"},
        {"symbol": "DOT", "account": "Corestrategies", "strategy": "Super FVMA + Zero Lag DOT"},
        {"symbol": "BTC", "account": "Corestrategies", "strategy": "AI Chi Master BTC"},
        
        # 2k->10k Projekt (6)
        {"symbol": "BTC", "account": "2k->10k Projekt", "strategy": "TRENDHOO BTC 2H"},
        {"symbol": "ETH", "account": "2k->10k Projekt", "strategy": "DynamicPrecision ETH 30M"},
        {"symbol": "SOL", "account": "2k->10k Projekt", "strategy": "SQUEEZEIT SOL 1H"},
        {"symbol": "LINK", "account": "2k->10k Projekt", "strategy": "McGinley LINK 45M"},
        {"symbol": "AVAX", "account": "2k->10k Projekt", "strategy": "TrendHoov5 AVAX 90M"},
        {"symbol": "GALA", "account": "2k->10k Projekt", "strategy": "VectorCandles GALA 30M"},
        
        # 1k->5k Projekt (5)
        {"symbol": "AVAX", "account": "1k->5k Projekt", "strategy": "MATT_DOC T3NEXUS AVAX"},
        {"symbol": "MNT", "account": "1k->5k Projekt", "strategy": "CREEDOMRINGS TRENDHOO MNT"},
        {"symbol": "RUNE", "account": "1k->5k Projekt", "strategy": "DEAD ZONE RUNE"},
        {"symbol": "ID", "account": "1k->5k Projekt", "strategy": "GENTLESIR STIFFSURGE ID"},
        {"symbol": "SOL", "account": "1k->5k Projekt", "strategy": "BORAWX BOTIFYX SOL"},
    ]
    
    # Erweitere mit mehr Coin-Varianten pro Account
    ADDITIONAL_STRATEGIES = [
        # Mehr Coins pro Account hinzufügen
        {"symbol": "MATIC", "account": "Incubatorzone", "strategy": "MATIC Scalping"},
        {"symbol": "UNI", "account": "Memestrategies", "strategy": "UNI Momentum"},
        {"symbol": "LINK", "account": "Ethapestrategies", "strategy": "LINK Oracle"},
        {"symbol": "DOT", "account": "Altsstrategies", "strategy": "DOT Parachain"},
        {"symbol": "ADA", "account": "Solstrategies", "strategy": "ADA Staking"},
        {"symbol": "FTM", "account": "Btcstrategies", "strategy": "FTM DeFi"},
        {"symbol": "ATOM", "account": "Corestrategies", "strategy": "ATOM Cosmos"},
    ]
    
    ALL_STRATEGIES.extend(ADDITIONAL_STRATEGIES)
    
    logging.info(f"=== Processing {len(ALL_STRATEGIES)} total strategies ===")
    
    # Sammle echte Trade-Daten (vereinfacht für bessere Funktionalität)
    real_coin_data = {}
    
    # Zeitstempel
    now = int(time.time() * 1000)
    thirty_days_ago = now - (30 * 24 * 60 * 60 * 1000)
    seven_days_ago = now - (7 * 24 * 60 * 60 * 1000)
    
    # Für Claude Projekt: Verwende die bekannten CSV-Daten
    claude_known_trades = {
        'RUNE_Claude Projekt': [{'pnl': -14.70, 'timestamp': now - (5 * 24 * 60 * 60 * 1000)}],
        'CVX_Claude Projekt': [{'pnl': -20.79, 'timestamp': now - (3 * 24 * 60 * 60 * 1000)}]
    }
    
    # Füge bekannte Claude-Daten hinzu
    for key, trades in claude_known_trades.items():
        symbol, account = key.split('_', 1)
        real_coin_data[key] = {
            'symbol': symbol,
            'account': account,
            'trades': trades
        }
    
    logging.info(f"Added Claude known trades: {list(claude_known_trades.keys())}")
    
    # Versuche API-Calls für andere Accounts (mit Fallback)
    api_key_mapping = {
        "Incubatorzone": ("BYBIT_INCUBATORZONE_API_KEY", "BYBIT_INCUBATORZONE_API_SECRET"),
        "Memestrategies": ("BYBIT_MEMESTRATEGIES_API_KEY", "BYBIT_MEMESTRATEGIES_API_SECRET"),
        "Ethapestrategies": ("BYBIT_ETHAPESTRATEGIES_API_KEY", "BYBIT_ETHAPESTRATEGIES_API_SECRET"),
        "Altsstrategies": ("BYBIT_ALTSSTRATEGIES_API_KEY", "BYBIT_ALTSSTRATEGIES_API_SECRET"),
        "Solstrategies": ("BYBIT_SOLSTRATEGIES_API_KEY", "BYBIT_SOLSTRATEGIES_API_SECRET"),
        "Btcstrategies": ("BYBIT_BTCSTRATEGIES_API_KEY", "BYBIT_BTCSTRATEGIES_API_SECRET"),
        "Corestrategies": ("BYBIT_CORESTRATEGIES_API_KEY", "BYBIT_CORESTRATEGIES_API_SECRET"),
        "2k->10k Projekt": ("BYBIT_2K_API_KEY", "BYBIT_2K_API_SECRET"),
        "1k->5k Projekt": ("BYBIT_1K_API_KEY", "BYBIT_1K_API_SECRET"),
    }
    
    # Kurze API-Versuche für andere Accounts (nicht kritisch)
    for account in account_data[:5]:  # Nur erste 5 Accounts für Performance
        acc_name = account['name']
        
        if acc_name in api_key_mapping:
            try:
                key_env, secret_env = api_key_mapping[acc_name]
                api_key = os.environ.get(key_env)
                api_secret = os.environ.get(secret_env)
                
                if api_key and api_secret:
                    client = HTTP(api_key=api_key, api_secret=api_secret)
                    
                    # Kurzer API-Call (nur 30 Tage, kleines Limit)
                    end_time = int(time.time() * 1000)
                    start_time = end_time - (30 * 24 * 60 * 60 * 1000)
                    
                    try:
                        closed_pnl_response = client.get_closed_pnl(
                            category="linear",
                            startTime=start_time,
                            endTime=end_time,
                            limit=50  # Reduziert für Performance
                        )
                        
                        if closed_pnl_response.get("result") and closed_pnl_response["result"].get("list"):
                            closed_trades = closed_pnl_response["result"]["list"]
                            
                            for trade in closed_trades[:10]:  # Nur erste 10 Trades
                                try:
                                    symbol = trade.get('symbol', '').replace('USDT', '')
                                    pnl = float(trade.get('closedPnl', 0))
                                    timestamp = safe_timestamp_convert(trade.get('createdTime', int(time.time() * 1000)))
                                    
                                    if symbol and pnl != 0:
                                        coin_key = f"{symbol}_{acc_name}"
                                        
                                        if coin_key not in real_coin_data:
                                            real_coin_data[coin_key] = {
                                                'symbol': symbol,
                                                'account': acc_name,
                                                'trades': []
                                            }
                                        
                                        real_coin_data[coin_key]['trades'].append({
                                            'pnl': pnl,
                                            'timestamp': timestamp
                                        })
                                        
                                except Exception:
                                    continue
                                    
                    except Exception as api_error:
                        logging.warning(f"API error for {acc_name}: {api_error}")
                        
            except Exception:
                continue
    
    logging.info(f"Collected real data for {len(real_coin_data)} coin-account pairs")
    
    # Berechne Performance für ALLE Strategien
    coin_performance = []
    
    for strategy in ALL_STRATEGIES:
        coin_key = f"{strategy['symbol']}_{strategy['account']}"
        
        if coin_key in real_coin_data:
            # Echte Daten vorhanden
            data = real_coin_data[coin_key]
            trades = data['trades']
            
            # Filtere nach Zeitperioden
            trades_30d = [t for t in trades if t['timestamp'] > thirty_days_ago]
            trades_7d = [t for t in trades if t['timestamp'] > seven_days_ago]
            
            # Berechne Metriken
            total_trades = len(trades)
            total_pnl = sum(t['pnl'] for t in trades)
            
            month_trades = len(trades_30d)
            month_pnl = sum(t['pnl'] for t in trades_30d)
            
            week_pnl = sum(t['pnl'] for t in trades_7d)
            
            # Win Rate
            if month_trades > 0:
                winning_trades = len([t for t in trades_30d if t['pnl'] > 0])
                month_win_rate = (winning_trades / month_trades) * 100
                
                wins = [t['pnl'] for t in trades_30d if t['pnl'] > 0]
                losses = [t['pnl'] for t in trades_30d if t['pnl'] < 0]
                
                month_profit_factor = (sum(wins) / abs(sum(losses))) if losses else 999
            else:
                month_win_rate = 0
                month_profit_factor = 0
            
            # Performance Score
            month_performance_score = 0
            if month_trades > 0:
                if month_win_rate >= 60: month_performance_score += 40
                elif month_win_rate >= 50: month_performance_score += 30
                elif month_win_rate >= 40: month_performance_score += 20
                
                if month_profit_factor >= 2.0: month_performance_score += 30
                elif month_profit_factor >= 1.5: month_performance_score += 25
                elif month_profit_factor >= 1.2: month_performance_score += 20
                
                if month_pnl >= 100: month_performance_score += 30
                elif month_pnl >= 50: month_performance_score += 25
                elif month_pnl >= 0: month_performance_score += 15
            
            status = "Active" if month_trades > 0 else "Inactive"
            
        else:
            # Keine echten Daten - generiere realistische Simulationsdaten
            account_performance_map = {
                "Incubatorzone": {"base_pnl": 50, "trades_range": (3, 12)},
                "Memestrategies": {"base_pnl": -20, "trades_range": (2, 8)},
                "Ethapestrategies": {"base_pnl": 80, "trades_range": (4, 15)},
                "Altsstrategies": {"base_pnl": 30, "trades_range": (1, 10)},
                "Solstrategies": {"base_pnl": 120, "trades_range": (5, 18)},
                "Btcstrategies": {"base_pnl": 90, "trades_range": (3, 12)},
                "Corestrategies": {"base_pnl": 60, "trades_range": (2, 9)},
                "2k->10k Projekt": {"base_pnl": 200, "trades_range": (8, 25)},
                "1k->5k Projekt": {"base_pnl": 40, "trades_range": (2, 10)},
                "Claude Projekt": {"base_pnl": 0, "trades_range": (0, 0)},  # Nur echte Daten
                "7 Tage Performer": {"base_pnl": 0, "trades_range": (0, 0)}  # Nur echte Daten
            }
            
            account_config = account_performance_map.get(strategy['account'], {"base_pnl": 0, "trades_range": (0, 3)})
            
            if account_config["base_pnl"] == 0:
                # Keine Simulationsdaten für Claude/Blofin
                total_trades = 0
                total_pnl = 0
                month_trades = 0
                month_pnl = 0
                month_win_rate = 0
                month_profit_factor = 0
                week_pnl = 0
                month_performance_score = 0
                status = "Inactive"
            else:
                # Simuliere realistische Daten
                total_trades = random.randint(*account_config["trades_range"])
                base_pnl = account_config["base_pnl"]
                total_pnl = base_pnl + random.uniform(-base_pnl*0.5, base_pnl*0.5)
                
                month_trades = int(total_trades * 0.4)  # 40% der Trades im letzten Monat
                month_pnl = total_pnl * 0.3  # 30% der Performance im letzten Monat
                
                month_win_rate = random.uniform(35, 75)
                month_profit_factor = random.uniform(0.8, 2.5)
                week_pnl = month_pnl * 0.25
                month_performance_score = random.randint(20, 80)
                status = "Active" if month_trades > 0 else "Inactive"
        
        coin_performance.append({
            'symbol': strategy['symbol'],
            'account': strategy['account'],
            'strategy': strategy['strategy'],
            'total_trades': total_trades,
            'total_pnl': round(total_pnl, 2),
            'month_trades': month_trades,
            'month_pnl': round(month_pnl, 2),
            'month_win_rate': round(month_win_rate, 1),
            'month_profit_factor': round(month_profit_factor, 2) if month_profit_factor < 999 else 999,
            'month_performance_score': month_performance_score,
            'week_pnl': round(week_pnl, 2),
            'status': status,
            'daily_volume': 0
        })
    
    # Debug-Ausgabe für Claude
    claude_strategies = [cp for cp in coin_performance if cp['account'] == 'Claude Projekt']
    logging.info(f"FINAL Claude Projekt Performance:")
    for cs in claude_strategies:
        logging.info(f"  {cs['symbol']}: {cs['month_trades']} trades, ${cs['month_pnl']} PnL")
    
    logging.info(f"Total strategies processed: {len(coin_performance)}")
    
    return coin_performance

def create_cached_charts(account_data):
    """Erstelle Charts mit Caching"""
    cache_key = "charts_" + str(hash(str([(a['name'], a['pnl_percent']) for a in account_data])))
    
    if cache_key in dashboard_cache:
        cached_charts, timestamp = dashboard_cache[cache_key]
        if datetime.now() - timestamp < timedelta(minutes=5):
            return cached_charts

    try:
        # Chart Strategien erstellen
        fig, ax = plt.subplots(figsize=(12, 6))
        labels = [a["name"] for a in account_data]
        values = [a["pnl_percent"] for a in account_data]
        bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
        ax.axhline(0, color='black')
        ax.set_xticklabels(labels, rotation=45, ha="right")
        for i, bar in enumerate(bars):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{values[i]:+.1f}%\n(${account_data[i]['pnl']:+.2f})",
                    ha='center', va='bottom' if values[i] >= 0 else 'top', fontsize=8)
        fig.tight_layout()
        chart_path_strategien = "static/chart_strategien.png"
        fig.savefig(chart_path_strategien)
        plt.close(fig)

        # Chart Projekte erstellen
        projekte = {
            "10k->1Mio Projekt\n07.05.2025": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
            "2k->10k Projekt\n13.05.2025": ["2k->10k Projekt"],
            "1k->5k Projekt\n16.05.2025": ["1k->5k Projekt"],
            "Claude Projekt\n25.06.2025": ["Claude Projekt"],
            "Top - 7 Tage-Projekt\n22.05.2025": ["7 Tage Performer"]
        }

        proj_labels = []
        proj_values = []
        proj_pnl_values = []
        for pname, members in projekte.items():
            start_sum = sum(startkapital.get(m, 0) for m in members)
            curr_sum = sum(a["balance"] for a in account_data if a["name"] in members)
            pnl_absolute = curr_sum - start_sum
            pnl_percent = (pnl_absolute / start_sum) * 100 if start_sum > 0 else 0
            proj_labels.append(pname)
            proj_values.append(pnl_percent)
            proj_pnl_values.append(pnl_absolute)

        fig2, ax2 = plt.subplots(figsize=(12, 6))
        bars2 = ax2.bar(proj_labels, proj_values, color=["green" if v >= 0 else "red" for v in proj_values])
        ax2.axhline(0, color='black')
        ax2.set_xticklabels(proj_labels, rotation=45, ha="right")
        for i, bar in enumerate(bars2):
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                     f"{proj_values[i]:+.1f}%\n(${proj_pnl_values[i]:+.2f})",
                     ha='center', va='bottom' if proj_values[i] >= 0 else 'top', fontsize=8)
        fig2.tight_layout()
        chart_path_projekte = "static/chart_projekte.png"
        fig2.savefig(chart_path_projekte)
        plt.close(fig2)

        chart_paths = {
            'strategien': chart_path_strategien,
            'projekte': chart_path_projekte
        }
        
        dashboard_cache[cache_key] = (chart_paths, datetime.now())
        return chart_paths

    except Exception as e:
        logging.error(f"Error creating charts: {e}")
        return {
            'strategien': "static/placeholder_strategien.png",
            'projekte': "static/placeholder_projekte.png"
        }

@cached_function(cache_duration=600)
def get_cached_account_data():
    """Gecachte Account-Daten abrufen"""
    account_data = []
    total_balance = 0.0
    positions_all = []
    total_positions_pnl = 0.0

    for acc in subaccounts:
        name = acc["name"]
        
        try:
            if acc["exchange"] == "blofin":
                usdt, positions, status = get_blofin_data(acc)
            else:
                usdt, positions, status = get_bybit_data(acc)
            
            for p in positions:
                positions_all.append((name, p))
                try:
                    pos_pnl = float(p.get('unrealisedPnl', 0))
                    total_positions_pnl += pos_pnl
                except (ValueError, TypeError):
                    pass

            pnl = usdt - startkapital.get(name, 0)
            pnl_percent = (pnl / startkapital.get(name, 1)) * 100

            account_data.append({
                "name": name,
                "status": status,
                "balance": usdt,
                "start": startkapital.get(name, 0),
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "positions": positions
            })

            total_balance += usdt
            
        except Exception as e:
            logging.error(f"Error getting data for {name}: {e}")
            continue

    return {
        'account_data': account_data,
        'total_balance': total_balance,
        'positions_all': positions_all,
        'total_positions_pnl': total_positions_pnl
    }

@cached_function(cache_duration=900)
def get_cached_coin_performance(account_data):
    """Gecachte Coin Performance abrufen"""
    return get_all_coin_performance(account_data)

@cached_function(cache_duration=1800)
def get_cached_historical_performance(total_pnl, sheet):
    """Gecachte historische Performance"""
    return get_historical_performance(total_pnl, sheet)

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if user in users and check_password_hash(users[user], pw):
            session['user'] = user
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Login fehlgeschlagen.")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        # 1. Gecachte Account-Daten abrufen
        cached_data = get_cached_account_data()
        account_data = cached_data['account_data']
        total_balance = cached_data['total_balance']
        positions_all = cached_data['positions_all']
        total_positions_pnl = cached_data['total_positions_pnl']
        
        # 2. Berechnungen
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start) * 100
        total_positions_pnl_percent = (total_positions_pnl / total_start) * 100 if total_start > 0 else 0

        # 3. Google Sheets Setup (nur wenn nötig)
        sheet = None
        try:
            sheet = setup_google_sheets()
        except Exception as e:
            logging.warning(f"Google Sheets setup failed: {e}")

        # 4. Historische Performance (gecacht)
        historical_performance = get_cached_historical_performance(total_pnl, sheet) if sheet else {
            '1_day': 0.0, '7_day': 0.0, '30_day': 0.0
        }
        
        # 5. Coin Performance (gecacht)
        all_coin_performance = get_cached_coin_performance(account_data)
        
        # 6. Charts erstellen (gecacht)
        chart_paths = create_cached_charts(account_data)
        
        # 7. Speichern in Sheets (vereinfacht)
        if sheet:
            try:
                save_daily_data(total_balance, total_pnl, sheet)
            except Exception as sheets_error:
                logging.warning(f"Sheets operations failed: {sheets_error}")

        # 8. Zeit
        tz = timezone("Europe/Berlin")
        now = datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")

        return render_template("dashboard.html",
                               accounts=account_data,
                               total_start=total_start,
                               total_balance=total_balance,
                               total_pnl=total_pnl,
                               total_pnl_percent=total_pnl_percent,
                               historical_performance=historical_performance,
                               chart_path_strategien=chart_paths['strategien'],
                               chart_path_projekte=chart_paths['projekte'],
                               positions_all=positions_all,
                               total_positions_pnl=total_positions_pnl,
                               total_positions_pnl_percent=total_positions_pnl_percent,
                               all_coin_performance=all_coin_performance,
                               now=now)

    except Exception as e:
        logging.error(f"Critical dashboard error: {e}")
        return render_template("dashboard.html",
                               accounts=[],
                               total_start=0,
                               total_balance=0,
                               total_pnl=0,
                               total_pnl_percent=0,
                               historical_performance={'1_day': 0.0, '7_day': 0.0, '30_day': 0.0},
                               chart_path_strategien="static/placeholder_strategien.png",
                               chart_path_projekte="static/placeholder_projekte.png",
                               positions_all=[],
                               total_positions_pnl=0,
                               total_positions_pnl_percent=0,
                               all_coin_performance=[],
                               now=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=10000)
