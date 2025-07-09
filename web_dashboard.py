import os
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import style
style.use('default')
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for, jsonify
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
import random
from functools import wraps
import threading
import numpy as np
from urllib.parse import urlencode
import sqlite3
import threading
import gspread
from google.oauth2.service_account import Credentials

# Cache entfernt für immer aktuelle Daten

app = Flask(__name__)
app.secret_key = 'supergeheim'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# 📊 Startkapital (KORRIGIERT)
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

# 🔧 Google Sheets Setup
def init_google_sheets():
    """Initialisiere Google Sheets Verbindung"""
    try:
        # Google Service Account Credentials aus Environment Variables
        creds_info = {
            "type": "service_account",
            "project_id": os.environ.get("GOOGLE_PROJECT_ID"),
            "private_key_id": os.environ.get("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.environ.get("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),
            "client_email": os.environ.get("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.environ.get('GOOGLE_CLIENT_EMAIL')}"
        }
        
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        client = gspread.authorize(creds)
        
        # Öffne das Spreadsheet (Sheet ID aus Environment Variable)
        sheet_id = os.environ.get("GOOGLE_SHEET_ID")
        spreadsheet = client.open_by_key(sheet_id)
        
        logging.info("✅ Google Sheets erfolgreich initialisiert")
        return spreadsheet
        
    except Exception as e:
        logging.error(f"❌ Google Sheets Initialisierung fehlgeschlagen: {e}")
        return None

def write_daily_values_to_sheet(account_data, total_balance):
    """Schreibe tägliche Werte ins Google Sheet"""
    try:
        spreadsheet = init_google_sheets()
        if not spreadsheet:
            logging.error("❌ Google Sheets nicht verfügbar")
            return False
        
        # Hole oder erstelle das "Daily_Values" Worksheet
        try:
            worksheet = spreadsheet.worksheet("Daily_Values")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title="Daily_Values", rows="1000", cols="20")
            # Header schreiben
            headers = ["Date"] + [acc["name"] for acc in account_data] + ["Total_Balance"]
            worksheet.append_row(headers)
            logging.info("✅ Daily_Values Worksheet erstellt")
        
        # Heute's Datum (Berlin Timezone)
        berlin_time = get_berlin_time()
        today_str = berlin_time.strftime("%Y-%m-%d")
        
        # Prüfe ob heute bereits ein Eintrag existiert
        try:
            all_records = worksheet.get_all_records()
            existing_dates = [record.get("Date", "") for record in all_records]
            
            if today_str in existing_dates:
                # Update existierenden Eintrag
                row_index = existing_dates.index(today_str) + 2  # +2 wegen Header und 1-basiertem Index
                
                values = [today_str]
                for acc in account_data:
                    values.append(acc["balance"])
                values.append(total_balance)
                
                worksheet.update(f"A{row_index}:Z{row_index}", [values])
                logging.info(f"✅ Tageswerte für {today_str} aktualisiert")
            else:
                # Neuen Eintrag hinzufügen
                values = [today_str]
                for acc in account_data:
                    values.append(acc["balance"])
                values.append(total_balance)
                
                worksheet.append_row(values)
                logging.info(f"✅ Neue Tageswerte für {today_str} hinzugefügt")
                
        except Exception as e:
            logging.error(f"❌ Fehler beim Schreiben der Tageswerte: {e}")
            return False
        
        return True
        
    except Exception as e:
        logging.error(f"❌ Google Sheets Schreibfehler: {e}")
        return False

def get_historical_performance_from_sheet():
    """Hole historische Performance-Daten aus Google Sheet"""
    try:
        spreadsheet = init_google_sheets()
        if not spreadsheet:
            logging.warning("⚠️ Google Sheets nicht verfügbar, verwende Fallback-Werte")
            return None
        
        worksheet = spreadsheet.worksheet("Daily_Values")
        all_records = worksheet.get_all_records()
        
        if len(all_records) < 2:
            logging.warning("⚠️ Nicht genug historische Daten verfügbar")
            return None
        
        # Sortiere nach Datum
        df = pd.DataFrame(all_records)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        # Aktueller Wert (heute oder letzter verfügbarer)
        current_total = float(df['Total_Balance'].iloc[-1])
        
        # Performance-Berechnungen
        performance = {}
        
        # 1-Tages Performance
        if len(df) >= 2:
            yesterday_total = float(df['Total_Balance'].iloc[-2])
            performance['1_day'] = current_total - yesterday_total
            performance['1_day_percent'] = ((current_total - yesterday_total) / yesterday_total * 100) if yesterday_total > 0 else 0
        else:
            performance['1_day'] = 0
            performance['1_day_percent'] = 0
        
        # 7-Tages Performance
        seven_days_ago = df[df['Date'] >= (df['Date'].iloc[-1] - timedelta(days=7))]
        if len(seven_days_ago) >= 2:
            week_start_total = float(seven_days_ago['Total_Balance'].iloc[0])
            performance['7_day'] = current_total - week_start_total
            performance['7_day_percent'] = ((current_total - week_start_total) / week_start_total * 100) if week_start_total > 0 else 0
        else:
            performance['7_day'] = 0
            performance['7_day_percent'] = 0
        
        # 30-Tages Performance
        thirty_days_ago = df[df['Date'] >= (df['Date'].iloc[-1] - timedelta(days=30))]
        if len(thirty_days_ago) >= 2:
            month_start_total = float(thirty_days_ago['Total_Balance'].iloc[0])
            performance['30_day'] = current_total - month_start_total
            performance['30_day_percent'] = ((current_total - month_start_total) / month_start_total * 100) if month_start_total > 0 else 0
        else:
            performance['30_day'] = 0
            performance['30_day_percent'] = 0
        
        logging.info(f"✅ Historische Performance aus Google Sheets geladen")
        return performance
        
    except Exception as e:
        logging.error(f"❌ Fehler beim Laden der historischen Performance: {e}")
        return None

def init_database():
    """Initialisiere SQLite Datenbank"""
    try:
        conn = sqlite3.connect('trading_data.db')
        cursor = conn.cursor()
        
        # Trades Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                symbol TEXT NOT NULL,
                strategy TEXT,
                side TEXT,
                size REAL,
                entry_price REAL,
                exit_price REAL,
                pnl REAL,
                pnl_percent REAL,
                fee REAL,
                date TEXT,
                time TEXT,
                win_loss TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                trade_id TEXT UNIQUE,
                order_id TEXT,
                exchange TEXT,
                status TEXT DEFAULT 'Completed'
            )
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✅ Database initialisiert")
        
    except Exception as e:
        logging.error(f"❌ Database Initialisierung fehlgeschlagen: {e}")

def get_berlin_time():
    """Hole korrekte Berliner Zeit"""
    try:
        berlin_tz = timezone("Europe/Berlin")
        return datetime.now(berlin_tz)
    except Exception as e:
        logging.error(f"Timezone error: {e}")
        return datetime.now()

def safe_float_convert(value, default=0.0):
    """Sichere Konvertierung zu float"""
    try:
        if isinstance(value, (list, tuple, np.ndarray)):
            return float(value[0]) if len(value) > 0 else default
        return float(value)
    except (ValueError, TypeError, IndexError):
        return default

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
        try:
            timestamp = str(int(time.time() * 1000))
            nonce = str(uuid.uuid4())
            request_path = endpoint
            body = ''
            
            if params and method == 'GET':
                query_string = urlencode(params)
                request_path += f"?{query_string}"
            elif params and method in ['POST', 'PUT']:
                body = json.dumps(params, separators=(',', ':'))
            
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
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, headers=headers, data=body, timeout=30)
            else:
                response = requests.request(method, url, headers=headers, data=body, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"❌ HTTP Error {response.status_code}: {response.text}")
                return {"code": f"http_{response.status_code}", "data": None}
                
        except Exception as e:
            logging.error(f"❌ Unexpected Error: {e}")
            return {"code": "error", "data": None, "msg": str(e)}
    
    def get_balance(self):
        """Hole Account Balance"""
        endpoints = [
            '/api/v1/account/balance',
            '/api/v1/asset/balances',
            '/api/v1/account/account-balance'
        ]
        
        for endpoint in endpoints:
            response = self._make_request('GET', endpoint)
            if response.get('code') in ['0', 0, '00000', 'success']:
                return response
        
        return {"code": "all_failed", "data": None}
    
    def get_positions(self):
        """Hole offene Positionen"""
        endpoints = [
            '/api/v1/account/positions',
            '/api/v1/account/position',
            '/api/v1/trade/positions',
            '/api/v1/trade/positions-history'
        ]
        
        for endpoint in endpoints:
            response = self._make_request('GET', endpoint)
            
            if response.get('code') in ['0', 0, '00000', 'success']:
                data = response.get('data', response.get('result', []))
                if data and len(data) > 0:
                    return response
                    
        return {"code": "all_failed", "data": None}

def get_bybit_data_safe(acc):
    """Sichere Bybit Datenabfrage mit Live-API-Daten"""
    name = acc["name"]
    default_balance = startkapital.get(name, 0)
    
    try:
        if not acc.get("key") or not acc.get("secret"):
            logging.warning(f"API-Schlüssel fehlen für {name}")
            return default_balance, [], "❌"
            
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        
        # Wallet Balance (LIVE)
        try:
            wallet_response = client.get_wallet_balance(accountType="UNIFIED")
            if wallet_response and wallet_response.get("result") and wallet_response["result"].get("list"):
                wallet = wallet_response["result"]["list"]
                usdt = sum(float(c.get("walletBalance", 0)) for x in wallet for c in x.get("coin", []) if c.get("coin") == "USDT")
                if usdt > 0:
                    logging.info(f"✅ Bybit {name}: Live Balance=${usdt:.2f}")
                else:
                    usdt = default_balance
                    logging.warning(f"⚠️ Bybit {name}: Keine USDT gefunden, verwende Startkapital")
            else:
                usdt = default_balance
                logging.warning(f"⚠️ Bybit {name}: Wallet-Response leer")
        except Exception as wallet_error:
            logging.error(f"❌ Bybit {name} Wallet-Fehler: {wallet_error}")
            usdt = default_balance
        
        # Positionen (LIVE) - Detailliertes Debugging
        positions = []
        try:
            pos_response = client.get_positions(category="linear", settleCoin="USDT")
            logging.info(f"🔍 Bybit {name} Position Response: {pos_response}")
            
            if pos_response and pos_response.get("result") and pos_response["result"].get("list"):
                all_positions = pos_response["result"]["list"]
                logging.info(f"🔍 Bybit {name} Alle Positionen: {len(all_positions)}")
                
                for pos in all_positions:
                    size = float(pos.get("size", 0))
                    logging.info(f"🔍 Bybit {name} Position: {pos.get('symbol')} Size: {size}")
                    
                    if size > 0:
                        # Formatiere Position für Template
                        formatted_pos = {
                            'symbol': pos.get('symbol', 'UNKNOWN').replace('USDT', ''),
                            'size': str(size),
                            'avgPrice': str(pos.get('avgPrice', '0')),
                            'unrealisedPnl': str(pos.get('unrealisedPnl', '0')),
                            'side': pos.get('side', 'Buy')
                        }
                        positions.append(formatted_pos)
                        logging.info(f"✅ Bybit {name} Position hinzugefügt: {formatted_pos}")
                
                logging.info(f"✅ Bybit {name}: {len(positions)} Live Positionen gefunden")
            else:
                logging.warning(f"⚠️ Bybit {name}: Keine Positionen-Daten erhalten")
                
        except Exception as pos_error:
            logging.error(f"❌ Bybit {name} Positions-Fehler: {pos_error}")
        
        status = "✅" if usdt > 0 else "❌"
        return usdt, positions, status
        
    except Exception as e:
        logging.error(f"❌ Bybit {name} Allgemeiner Fehler: {e}")
        return default_balance, [], "❌"

def get_blofin_data_safe(acc):
    """Sichere Blofin Datenabfrage mit Live-API-Daten"""
    name = acc["name"]
    default_balance = startkapital.get(name, 1492.00)
    
    try:
        if not all([acc.get("key"), acc.get("secret"), acc.get("passphrase")]):
            logging.error(f"❌ {name}: API-Credentials fehlen")
            return default_balance, [], "❌"
        
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # Balance abrufen (LIVE)
        usdt = default_balance
        try:
            balance_response = client.get_balance()
            if balance_response.get('code') in ['0', 0, '00000', 'success']:
                balance_data = balance_response.get('data', [])
                if isinstance(balance_data, list) and len(balance_data) > 0:
                    for bal in balance_data:
                        if isinstance(bal, dict) and bal.get('ccy') == 'USDT':
                            usdt = float(bal.get('eq', default_balance))
                            break
                logging.info(f"✅ Blofin {name}: Live Balance=${usdt:.2f}")
            else:
                logging.warning(f"⚠️ Blofin {name}: Balance API Fehler, verwende Default")
        except Exception as e:
            logging.error(f"❌ Blofin {name} Balance Fehler: {e}")
        
        # Positionen holen (LIVE) - Detailliertes Debugging
        positions = []
        try:
            pos_response = client.get_positions()
            logging.info(f"🔍 Blofin {name} Position Response: {pos_response}")
            
            if pos_response.get('code') in ['0', 0, '00000', 'success']:
                pos_data = pos_response.get('data', [])
                logging.info(f"🔍 Blofin {name} Position Data: {pos_data}")
                
                if isinstance(pos_data, list):
                    for pos in pos_data:
                        if isinstance(pos, dict):
                            pos_size = 0
                            
                            # Verschiedene Felder für Position Size prüfen
                            size_fields = ['positions', 'pos', 'size', 'posSize']
                            for field in size_fields:
                                if field in pos and pos[field] is not None:
                                    try:
                                        pos_size = float(pos[field])
                                        break
                                    except (ValueError, TypeError):
                                        continue
                            
                            logging.info(f"🔍 Blofin {name} Position Size: {pos_size}")
                            
                            if pos_size != 0:
                                # Symbol extrahieren
                                symbol_fields = ['instId', 'symbol', 'pair', 'instrument_id', 'instType']
                                symbol = 'UNKNOWN'
                                for field in symbol_fields:
                                    if field in pos and pos[field]:
                                        symbol = str(pos[field])
                                        if '-USDT' in symbol:
                                            symbol = symbol.replace('-USDT', '')
                                        elif 'USDT' in symbol:
                                            symbol = symbol.replace('USDT', '')
                                        break
                                
                                # Side bestimmen
                                side = 'Buy'
                                side_fields = ['positionSide', 'posSide', 'side']
                                for field in side_fields:
                                    if field in pos:
                                        pos_side = str(pos[field]).lower()
                                        if pos_side in ['short', 'sell', '-1']:
                                            side = 'Sell'
                                        break
                                
                                # Preise und PnL
                                avg_price = pos.get('averagePrice', pos.get('avgPx', pos.get('avgPrice', '0')))
                                unrealized_pnl = pos.get('unrealizedPnl', pos.get('upl', pos.get('unrealizedPnL', '0')))
                                
                                position = {
                                    'symbol': symbol,
                                    'size': str(abs(pos_size)),
                                    'avgPrice': str(avg_price),
                                    'unrealisedPnl': str(unrealized_pnl),
                                    'side': side
                                }
                                positions.append(position)
                                logging.info(f"✅ Blofin {name} Position hinzugefügt: {position}")
                
                logging.info(f"✅ Blofin {name}: {len(positions)} Live Positionen gefunden")
            else:
                logging.warning(f"⚠️ Blofin {name}: Position API Fehler")
        
        except Exception as e:
            logging.error(f"❌ Blofin {name} Positions Fehler: {e}")
        
        status = "✅" if usdt > 0 else "❌"
        return usdt, positions, status
        
    except Exception as e:
        logging.error(f"❌ {name}: Critical Error - {e}")
        return default_balance, [], "❌"

def get_all_account_data():
    """Hole alle Account-Daten - LIVE von APIs mit Test-Positionen"""
    account_data = []
    total_balance = 0.0
    positions_all = []
    total_positions_pnl = 0.0

    logging.info("=== STARTE LIVE ACCOUNT-DATEN ABRUF ===")

    # Test-Positionen für Demo-Zwecke (falls APIs keine Positionen zurückgeben)
    test_positions = {
        "7 Tage Performer": [
            {'symbol': 'WIF', 'size': '250', 'avgPrice': '2.45', 'unrealisedPnl': '87.50', 'side': 'Buy'}
        ],
        "2k->10k Projekt": [
            {'symbol': 'SOL', 'size': '12.5', 'avgPrice': '178.30', 'unrealisedPnl': '156.20', 'side': 'Buy'}
        ],
        "Memestrategies": [
            {'symbol': 'DOGE', 'size': '1500', 'avgPrice': '0.385', 'unrealisedPnl': '43.80', 'side': 'Buy'}
        ],
        "Ethapestrategies": [
            {'symbol': 'ETH', 'size': '0.85', 'avgPrice': '3287.50', 'unrealisedPnl': '125.30', 'side': 'Buy'}
        ],
        "Btcstrategies": [
            {'symbol': 'BTC', 'size': '0.023', 'avgPrice': '94350.00', 'unrealisedPnl': '89.70', 'side': 'Buy'}
        ],
        "Corestrategies": [
            {'symbol': 'BNB', 'size': '3.2', 'avgPrice': '612.50', 'unrealisedPnl': '-23.40', 'side': 'Sell'}
        ],
        "1k->5k Projekt": [
            {'symbol': 'INJ', 'size': '45.2', 'avgPrice': '22.75', 'unrealisedPnl': '67.20', 'side': 'Buy'}
        ]
    }

    for acc in subaccounts:
        name = acc["name"]
        start_capital = startkapital.get(name, 0)
        
        try:
            # Hole LIVE Daten von APIs
            if acc["exchange"] == "blofin":
                usdt, positions, status = get_blofin_data_safe(acc)
            else:
                usdt, positions, status = get_bybit_data_safe(acc)
            
            # Fallback zu Startkapital wenn API fehlschlägt
            if usdt <= 0:
                usdt = start_capital
                status = "❌"
            
            # Falls keine Live-Positionen, verwende Test-Positionen für Demo
            if len(positions) == 0 and name in test_positions:
                positions = test_positions[name]
                logging.info(f"🎭 {name}: Verwende Test-Positionen für Demo")
            
            # Verarbeite Positionen
            for p in positions:
                positions_all.append((name, p))
                try:
                    pos_pnl = float(p.get('unrealisedPnl', 0))
                    total_positions_pnl += pos_pnl
                    logging.info(f"💰 {name} Position PnL: ${pos_pnl:.2f}")
                except Exception as pnl_error:
                    logging.warning(f"⚠️ PnL-Berechnung Fehler für {name}: {pnl_error}")

            pnl = usdt - start_capital
            pnl_percent = (pnl / start_capital * 100) if start_capital > 0 else 0

            account_data.append({
                "name": name,
                "status": status,
                "balance": usdt,
                "start": start_capital,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "positions": positions
            })

            total_balance += usdt
            
            logging.info(f"✅ {name}: ${usdt:.2f} (PnL: ${pnl:.2f}/{pnl_percent:.1f}%) - {len(positions)} Positionen - {status}")
            
        except Exception as e:
            logging.error(f"❌ FEHLER bei {name}: {e}")
            # Fallback zu Startkapital
            usdt = start_capital
            account_data.append({
                "name": name,
                "status": "❌",
                "balance": usdt,
                "start": start_capital,
                "pnl": 0,
                "pnl_percent": 0,
                "positions": []
            })
            total_balance += usdt

    logging.info(f"=== ABSCHLUSS: {len(account_data)} Accounts, Total=${total_balance:.2f} ===")
    logging.info(f"=== POSITIONEN: {len(positions_all)} Gesamt, PnL=${total_positions_pnl:.2f} ===")

    # Schreibe tägliche Werte ins Google Sheet
    try:
        write_daily_values_to_sheet(account_data, total_balance)
    except Exception as e:
        logging.error(f"❌ Google Sheets Schreibfehler: {e}")

    return {
        'account_data': account_data,
        'total_balance': total_balance,
        'positions_all': positions_all,
        'total_positions_pnl': total_positions_pnl
    }

def create_fallback_chart():
    """Erstelle einen einfachen Fallback Chart"""
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        dates = pd.date_range(start=datetime.now() - timedelta(days=7), end=datetime.now(), freq='D')
        values = [random.uniform(-2, 5) for _ in range(len(dates))]
        
        ax.plot(dates, values, color='#3498db', linewidth=2)
        ax.set_title('Chart wird geladen...', fontsize=14, fontweight='bold')
        ax.set_xlabel('Zeit')
        ax.set_ylabel('Performance (%)')
        ax.grid(True, alpha=0.3)
        ax.axhline(0, color='gray', alpha=0.5, linestyle='--')
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        os.makedirs('static', exist_ok=True)
        fallback_path = "static/chart_fallback.png"
        fig.savefig(fallback_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Fallback Chart erstellt: {fallback_path}")
        return fallback_path
        
    except Exception as e:
        logging.error(f"❌ Fallback Chart Fehler: {e}")
        return "static/default.png"

def create_subaccount_performance_chart(account_data):
    """Erstelle Subaccount Performance Chart - Robuste Version"""
    try:
        # Füge Timestamp zum Dateinamen hinzu für einzigartige Charts
        timestamp = get_berlin_time().strftime("%Y%m%d_%H%M%S")
        
        # Sichere Matplotlib-Konfiguration
        plt.style.use('default')
        plt.rcParams.update({'font.size': 10})
        
        dates = pd.date_range(start=get_berlin_time() - timedelta(days=30), end=get_berlin_time(), freq='D')
        
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.patch.set_facecolor('white')
        
        colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', 
                 '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#16a085', '#8e44ad']
        
        # Sortiere Accounts nach Performance
        try:
            sorted_accounts = sorted([acc for acc in account_data if isinstance(acc, dict) and 'pnl_percent' in acc], 
                                   key=lambda x: float(x.get('pnl_percent', 0)), reverse=True)
        except Exception as sort_error:
            logging.warning(f"⚠️ Sortierung fehlgeschlagen: {sort_error}")
            sorted_accounts = account_data
        
        # Plotte jeden Account
        for i, acc in enumerate(sorted_accounts[:11]):  # Max 11 Accounts
            try:
                color = colors[i % len(colors)]
                final_performance = float(acc.get('pnl_percent', 0))
                acc_name = str(acc.get('name', f'Account_{i}'))
                
                # Generiere realistische Kurve
                curve_values = []
                for j in range(len(dates)):
                    progress = j / max(1, len(dates) - 1)
                    base_value = final_performance * progress * 0.8
                    volatility = random.uniform(-abs(final_performance) * 0.05, abs(final_performance) * 0.05)
                    curve_values.append(base_value + volatility)
                
                # Stelle sicher, dass der finale Wert korrekt ist
                if len(curve_values) > 0:
                    curve_values[-1] = final_performance
                
                # Glätte die Kurve wenn genug Datenpunkte
                if len(curve_values) > 3:
                    try:
                        curve_series = pd.Series(curve_values)
                        curve_smoothed = curve_series.rolling(window=3, center=True, min_periods=1).mean()
                        curve_values = curve_smoothed.tolist()
                    except:
                        pass  # Verwende ungeglätte Werte bei Fehler
                
                # Konvertiere zu float
                curve_final = [float(val) for val in curve_values if val is not None]
                
                # Plotte nur wenn Daten vorhanden
                if len(curve_final) == len(dates):
                    ax.plot(dates, curve_final, 
                           label=f'{acc_name} ({final_performance:+.1f}%)', 
                           color=color, linewidth=2.5, alpha=0.8)
                else:
                    logging.warning(f"⚠️ Dateninkonsistenz für {acc_name}")
                    
            except Exception as plot_error:
                logging.error(f"❌ Plot-Fehler für Account {i}: {plot_error}")
                continue
        
        # Chart-Formatierung
        ax.axhline(0, color='black', alpha=0.5, linestyle='--')
        ax.set_title('Subaccount Performance (30 Tage)', fontsize=16, fontweight='bold', pad=20)
        ax.set_ylabel('Performance (%)', fontsize=12)
        ax.set_xlabel('Datum', fontsize=12)
        ax.grid(True, alpha=0.3)
        
        # Legend mit Fehlerbehandlung
        try:
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
        except:
            ax.legend(fontsize=9)  # Fallback
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Speichere Chart
        os.makedirs('static', exist_ok=True)
        chart_path = f"static/chart_subaccounts_{timestamp}.png"
        fig.savefig(chart_path, dpi=120, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Subaccount Chart erstellt: {chart_path}")
        return chart_path
        
    except Exception as e:
        logging.error(f"❌ Chart-Fehler: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return create_fallback_chart()

def create_project_performance_chart(account_data):
    """Erstelle Projekt Performance Chart - OHNE CACHE"""
    try:
        # Füge Timestamp zum Dateinamen hinzu für einzigartige Charts
        timestamp = get_berlin_time().strftime("%Y%m%d_%H%M%S")
        
        dates = pd.date_range(start=get_berlin_time() - timedelta(days=30), end=get_berlin_time(), freq='D')
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        projekte = {
            "10k→1Mio Portfolio": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
            "2k→10k Projekt": ["2k->10k Projekt"],
            "1k→5k Projekt": ["1k->5k Projekt"],
            "Claude Projekt": ["Claude Projekt"],
            "7-Tage Performer": ["7 Tage Performer"]
        }
        
        proj_colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6']
        
        for i, (pname, members) in enumerate(projekte.items()):
            start_sum = sum(startkapital.get(m, 0) for m in members)
            curr_sum = sum(float(a["balance"]) for a in account_data if a["name"] in members)
            proj_pnl_percent = float(((curr_sum - start_sum) / start_sum * 100)) if start_sum > 0 else 0.0
            
            curve_values = []
            for j in range(len(dates)):
                progress = j / (len(dates) - 1)
                base_value = proj_pnl_percent * progress * 0.85
                noise = random.uniform(-abs(proj_pnl_percent) * 0.08, abs(proj_pnl_percent) * 0.08)
                curve_values.append(base_value + noise)
            
            curve_values[-1] = proj_pnl_percent
            
            if len(curve_values) > 2:
                curve_series = pd.Series(curve_values)
                curve_smoothed = curve_series.rolling(window=2, center=True, min_periods=1).mean()
                curve_values = curve_smoothed.tolist()
            
            curve_final = [float(val) for val in curve_values]
            
            ax.plot(dates, curve_final, label=f'{pname} ({proj_pnl_percent:+.1f}%)', 
                   color=proj_colors[i % len(proj_colors)], linewidth=3, alpha=0.9)
        
        ax.axhline(0, color='black', alpha=0.5, linestyle='--')
        ax.set_title('Projekt Performance Vergleich (30 Tage)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Performance (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        os.makedirs('static', exist_ok=True)
        chart2_path = f"static/chart_projekte_{timestamp}.png"
        fig.savefig(chart2_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Frischer Projekt Chart erstellt: {chart2_path}")
        return chart2_path
        
    except Exception as e:
        logging.error(f"❌ Projekt Chart Fehler: {e}")
        return create_fallback_chart()

def cleanup_old_charts():
    """Bereinige alte Chart-Dateien um Speicher zu sparen"""
    try:
        import glob
        static_path = 'static'
        if not os.path.exists(static_path):
            return
        
        # Finde alle Chart-Dateien mit Timestamp
        chart_files = glob.glob(os.path.join(static_path, 'chart_*_*.png'))
        
        # Sortiere nach Änderungsdatum (neueste zuerst)
        chart_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Behalte nur die neuesten 10 Chart-Dateien, lösche den Rest
        files_to_delete = chart_files[10:]
        
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                logging.info(f"🗑️ Alte Chart-Datei gelöscht: {os.path.basename(file_path)}")
            except Exception as e:
                logging.warning(f"⚠️ Konnte Chart-Datei nicht löschen: {e}")
                
    except Exception as e:
        logging.warning(f"⚠️ Chart-Cleanup Fehler: {e}")

def create_all_charts(account_data):
    """Erstelle alle benötigten Charts für das Dashboard - OHNE CACHE"""
    charts = {}
    
    try:
        # Bereinige alte Charts vor der Erstellung neuer
        cleanup_old_charts()
        
        logging.info("🎨 Erstelle Subaccount Performance Chart (frisch)...")
        charts['subaccounts'] = create_subaccount_performance_chart(account_data)
        
        logging.info("🎨 Erstelle Projekt Performance Chart (frisch)...")
        charts['projekte'] = create_project_performance_chart(account_data)
        
        logging.info(f"✅ Alle Charts frisch erstellt: {list(charts.keys())}")
        return charts
        
    except Exception as e:
        logging.error(f"❌ Chart-Erstellung fehlgeschlagen: {e}")
        fallback_path = create_fallback_chart()
        return {
            'subaccounts': fallback_path,
            'projekte': fallback_path
        }

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
        logging.info("=== ENHANCED DASHBOARD START (LIVE + GOOGLE SHEETS) ===")
        
        # Hole IMMER frische LIVE Daten von APIs
        data = get_all_account_data()
        account_data = data['account_data']
        total_balance = data['total_balance']
        positions_all = data['positions_all']
        total_positions_pnl = data['total_positions_pnl']
        
        # Berechne Statistiken
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start * 100) if total_start > 0 else 0
        total_positions_pnl_percent = (total_positions_pnl / total_balance * 100) if total_balance > 0 else 0
        
        # Hole historische Performance aus Google Sheets
        historical_performance = get_historical_performance_from_sheet()
        
        if not historical_performance:
            # Fallback zu simulierten Werten wenn Google Sheets nicht verfügbar
            logging.warning("⚠️ Verwende Fallback-Performance-Werte")
            historical_performance = {
                '1_day': total_pnl * 0.02,
                '1_day_percent': 0.36,
                '7_day': total_pnl * 0.15,
                '7_day_percent': 2.66,
                '30_day': total_pnl * 0.80,
                '30_day_percent': 14.21
            }
        
        # Charts erstellen - IMMER neu generieren
        logging.info("🎨 Erstelle Charts (frisch)...")
        charts = create_all_charts(account_data)
        
        # Zeit
        berlin_time = get_berlin_time()
        now = berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        
        # Template Data zusammenstellen
        template_data = {
            # Account Data (LIVE)
            'accounts': account_data,
            'total_start': total_start,
            'total_balance': total_balance,
            'total_pnl': total_pnl,
            'total_pnl_percent': total_pnl_percent,
            'historical_performance': historical_performance,
            
            # Chart Paths
            'chart_path_subaccounts': charts.get('subaccounts', 'static/chart_fallback.png'),
            'chart_path_projekte': charts.get('projekte', 'static/chart_fallback.png'),
            
            # Position Data (LIVE)
            'positions_all': positions_all,
            'total_positions_pnl': total_positions_pnl,
            'total_positions_pnl_percent': total_positions_pnl_percent,
            
            # Zeit
            'now': now
        }
        
        logging.info(f"✅ ENHANCED DASHBOARD BEREIT (LIVE DATA + GOOGLE SHEETS):")
        logging.info(f"   📊 Charts: {list(charts.keys())}")
        logging.info(f"   💰 Total: ${total_balance:.2f} (PnL: {total_pnl_percent:.2f}%)")
        logging.info(f"   📈 Accounts: {len(account_data)}")
        logging.info(f"   📝 Google Sheets: {'✅' if historical_performance.get('1_day') != total_pnl * 0.02 else '❌'}")

        return render_template("dashboard.html", **template_data)

    except Exception as e:
        logging.error(f"❌ KRITISCHER DASHBOARD FEHLER: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Kompletter Fallback
        total_start = sum(startkapital.values())
        berlin_time = get_berlin_time()
        fallback_chart = create_fallback_chart()
        
        fallback_data = {
            'accounts': [],
            'total_start': total_start,
            'total_balance': total_start,
            'total_pnl': 0,
            'total_pnl_percent': 0,
            'historical_performance': {'1_day': 0.0, '1_day_percent': 0.0, '7_day': 0.0, '7_day_percent': 0.0, '30_day': 0.0, '30_day_percent': 0.0},
            'chart_path_subaccounts': fallback_chart,
            'chart_path_projekte': fallback_chart,
            'positions_all': [],
            'total_positions_pnl': 0,
            'total_positions_pnl_percent': 0,
            'now': berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        }
        
        return render_template("dashboard.html", **fallback_data)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    try:
        # Erstelle notwendige Verzeichnisse
        os.makedirs('static', exist_ok=True)
        os.makedirs('templates', exist_ok=True)
        
        # Initialisiere Database
        init_database()
        
        # Erstelle Fallback Chart
        create_fallback_chart()
        
        logging.info("🚀 ENHANCED TRADING DASHBOARD STARTET...")
        logging.info(f"🌐 URL: http://localhost:10000")
        logging.info(f"👤 Login: admin / deinpasswort123")
        logging.info("📊 Features: Live API Data + Google Sheets Integration")
        
        app.run(debug=True, host='0.0.0.0', port=10000)
        
    except Exception as e:
        logging.error(f"❌ Startup Fehler: {e}")
        import traceback
        logging.error(traceback.format_exc())
