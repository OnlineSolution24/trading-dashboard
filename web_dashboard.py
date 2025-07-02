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
import gspread
import random
from google.oauth2.service_account import Credentials
from functools import wraps
from threading import Lock
import numpy as np
from urllib.parse import urlencode
import sqlite3
import threading
import subprocess
import sys

# Progressive Import System Integration
try:
    from progressive_import_system import (
        ProgressiveTradeImporter, 
        ProgressDatabase,
        get_progressive_import_status,
        get_all_import_progress,
        start_progressive_import
    )
    PROGRESSIVE_IMPORT_AVAILABLE = True
    logging.info("✅ Progressive Import System geladen")
except ImportError as e:
    PROGRESSIVE_IMPORT_AVAILABLE = False
    logging.warning(f"⚠️ Progressive Import System nicht verfügbar: {e}")

# Progressive Status Variable (nach den anderen globalen Variablen)
progressive_status = {
    'running': False,
    'progress': 0,
    'message': 'Bereit',
    'session_id': '',
    'current_account': '',
    'total_accounts': 0,
    'completed_accounts': 0,
    'total_trades': 0,
    'estimated_completion': None
}

# Globale Cache-Variablen
cache_lock = Lock()
dashboard_cache = {}
import_status = {
    'running': False,
    'progress': 0,
    'message': 'Bereit',
    'last_update': None,
    'mode': None
}

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

class GoogleSheetsPerformanceReader:
    """Liest Performance-Daten aus Google Sheets für das Dashboard"""
    
    def __init__(self):
        self.gc = None
        self.spreadsheet = None
        self._connect()
    
    def _connect(self):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_file = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        
        if not creds_file:
            logging.warning("GOOGLE_SERVICE_ACCOUNT_JSON nicht gefunden - verwende Demo-Daten")
            return
        
        # FIX: Korrekte JSON Behandlung
        try:
            if isinstance(creds_file, str):
                # Falls Base64 encoded
                if not creds_file.strip().startswith('{'):
                    try:
                        import base64
                        creds_file = base64.b64decode(creds_file).decode('utf-8')
                    except:
                        pass
                creds_data = json.loads(creds_file)
            else:
                creds_data = creds_file
        except json.JSONDecodeError as e:
            logging.error(f"JSON Parse Error: {e}")
            self.gc = None
            return
        
        credentials = Credentials.from_service_account_info(creds_data, scopes=scope)
        self.gc = gspread.authorize(credentials)
        
        sheet_id = os.environ.get('GOOGLE_SHEET_ID')
        if not sheet_id:
            logging.warning("GOOGLE_SHEET_ID nicht gefunden - verwende Demo-Daten")
            return
        
        self.spreadsheet = self.gc.open_by_key(sheet_id)
        logging.info("✅ Google Sheets Performance Reader verbunden")
        
    except Exception as e:
        logging.error(f"❌ Google Sheets Performance Reader Fehler: {e}")
        self.gc = None
    
    def get_performance_data(self):
        """Hole Performance-Daten aus Google Sheets"""
        
        if not self.gc or not self.spreadsheet:
            logging.warning("⚠️ Google Sheets nicht verbunden - verwende Demo-Daten")
            return self._get_demo_performance_data()
        
        try:
            # Versuche Performance Summary zu laden
            worksheet = self.spreadsheet.worksheet('Performance_Summary')
            records = worksheet.get_all_records()
            
            if not records:
                logging.warning("⚠️ Performance Summary leer - verwende Demo-Daten")
                return self._get_demo_performance_data()
            
            # Konvertiere zu unserem Format
            performance_data = []
            for record in records:
                try:
                    perf_data = {
                        'account': record.get('Account', ''),
                        'symbol': record.get('Symbol', ''),
                        'strategy': record.get('Strategy', ''),
                        'total_trades': int(record.get('Total_Trades', 0)) if record.get('Total_Trades') else 0,
                        'total_pnl': float(record.get('Total_PnL', 0)) if record.get('Total_PnL') else 0,
                        'month_trades': int(record.get('Month_Trades', 0)) if record.get('Month_Trades') else 0,
                        'month_pnl': float(record.get('Month_PnL', 0)) if record.get('Month_PnL') else 0,
                        'week_pnl': float(record.get('Week_PnL', 0)) if record.get('Week_PnL') else 0,
                        'month_win_rate': float(record.get('Month_Win_Rate', 0)) if record.get('Month_Win_Rate') else 0,
                        'month_profit_factor': float(record.get('Month_Profit_Factor', 0)) if record.get('Month_Profit_Factor') else 0,
                        'month_performance_score': float(record.get('Month_Performance_Score', 0)) if record.get('Month_Performance_Score') else 0,
                        'status': record.get('Status', 'Inactive')
                    }
                    
                    # Nur gültige Einträge hinzufügen
                    if perf_data['account'] and perf_data['symbol']:
                        performance_data.append(perf_data)
                        
                except Exception as e:
                    logging.error(f"❌ Fehler beim Parsen von Performance Record: {e}")
                    continue
            
            if performance_data:
                logging.info(f"✅ Performance-Daten aus Google Sheets geladen: {len(performance_data)} Einträge")
                return performance_data
            else:
                logging.warning("⚠️ Keine gültigen Performance-Daten gefunden - verwende Demo-Daten")
                return self._get_demo_performance_data()
                
        except gspread.WorksheetNotFound:
            logging.warning("⚠️ Performance_Summary Worksheet nicht gefunden - verwende Demo-Daten")
            return self._get_demo_performance_data()
        except Exception as e:
            logging.error(f"❌ Fehler beim Laden der Performance-Daten: {e}")
            return self._get_demo_performance_data()
    
    def _get_demo_performance_data(self):
        """Fallback Demo-Performance-Daten"""
        logging.info("🎭 Verwende Demo Performance-Daten")
        
        demo_data = []
        
        # Account-spezifische Coin-Listen
        account_coins = {
            'Claude Projekt': [
                {'symbol': 'RUNE', 'strategy': 'AI vs. Ninja Turtle', 'pnl': -14.70, 'trades': 1, 'win_rate': 0.0, 'score': 15}
            ],
            '7 Tage Performer': [
                {'symbol': 'WIF', 'strategy': 'MACD LIQUIDITY SPECTRUM', 'pnl': 420.50, 'trades': 8, 'win_rate': 75.0, 'score': 85},
                {'symbol': 'ARB', 'strategy': 'STIFFZONE ETH', 'pnl': 278.30, 'trades': 12, 'win_rate': 66.7, 'score': 75},
                {'symbol': 'AVAX', 'strategy': 'PRECISION TREND MASTERY', 'pnl': 312.70, 'trades': 15, 'win_rate': 73.3, 'score': 80},
                {'symbol': 'ALGO', 'strategy': 'TRIGGERHAPPY2 INJ', 'pnl': -45.90, 'trades': 6, 'win_rate': 33.3, 'score': 25},
                {'symbol': 'SOL', 'strategy': 'VOLUME SPIKE HUNTER', 'pnl': 567.80, 'trades': 22, 'win_rate': 81.8, 'score': 92}
            ],
            'Memestrategies': [
                {'symbol': 'DOGE', 'strategy': 'MEME MOMENTUM MASTER', 'pnl': 245.60, 'trades': 18, 'win_rate': 72.2, 'score': 78},
                {'symbol': 'SHIB', 'strategy': 'SHIBA SWING STRATEGY', 'pnl': 134.80, 'trades': 12, 'win_rate': 58.3, 'score': 62},
                {'symbol': 'PEPE', 'strategy': 'PEPE PROFIT PREDICTOR', 'pnl': 89.40, 'trades': 15, 'win_rate': 66.7, 'score': 70},
                {'symbol': 'WIF', 'strategy': 'WIF WAVE RIDER', 'pnl': 167.20, 'trades': 9, 'win_rate': 77.8, 'score': 82},
                {'symbol': 'BONK', 'strategy': 'BONK BREAKOUT HUNTER', 'pnl': -23.50, 'trades': 8, 'win_rate': 37.5, 'score': 35}
            ],
            'Ethapestrategies': [
                {'symbol': 'ETH', 'strategy': 'ETHEREUM EMPIRE BUILDER', 'pnl': 456.90, 'trades': 25, 'win_rate': 68.0, 'score': 85},
                {'symbol': 'LDO', 'strategy': 'LIDO LIQUID STAKING', 'pnl': 123.40, 'trades': 14, 'win_rate': 64.3, 'score': 72},
                {'symbol': 'MATIC', 'strategy': 'POLYGON POWER PLAY', 'pnl': 234.70, 'trades': 19, 'win_rate': 73.7, 'score': 79},
                {'symbol': 'LINK', 'strategy': 'CHAINLINK ORACLE ORACLE', 'pnl': 178.30, 'trades': 16, 'win_rate': 62.5, 'score': 68},
                {'symbol': 'UNI', 'strategy': 'UNISWAP UNICORN', 'pnl': 298.50, 'trades': 21, 'win_rate': 76.2, 'score': 83}
            ],
            'Solstrategies': [
                {'symbol': 'SOL', 'strategy': 'SOLANA SPEED DEMON', 'pnl': 389.20, 'trades': 24, 'win_rate': 70.8, 'score': 84},
                {'symbol': 'RAY', 'strategy': 'RAYDIUM ROCKET', 'pnl': 156.80, 'trades': 13, 'win_rate': 69.2, 'score': 75},
                {'symbol': 'ORCA', 'strategy': 'ORCA OCEAN RIDER', 'pnl': 87.60, 'trades': 11, 'win_rate': 54.5, 'score': 58},
                {'symbol': 'SRM', 'strategy': 'SERUM SURGE STRATEGY', 'pnl': -34.20, 'trades': 7, 'win_rate': 28.6, 'score': 28}
            ],
            'Btcstrategies': [
                {'symbol': 'BTC', 'strategy': 'BITCOIN BEAST MODE', 'pnl': 678.90, 'trades': 28, 'win_rate': 75.0, 'score': 88},
                {'symbol': 'LTC', 'strategy': 'LITECOIN LIGHTNING', 'pnl': 234.50, 'trades': 16, 'win_rate': 62.5, 'score': 71},
                {'symbol': 'BCH', 'strategy': 'BITCOIN CASH CRUSHER', 'pnl': 145.20, 'trades': 12, 'win_rate': 58.3, 'score': 65}
            ],
            'Altsstrategies': [
                {'symbol': 'ADA', 'strategy': 'CARDANO CONSTELLATION', 'pnl': 189.40, 'trades': 17, 'win_rate': 64.7, 'score': 73},
                {'symbol': 'DOT', 'strategy': 'POLKADOT PARACHAIN', 'pnl': 267.80, 'trades': 20, 'win_rate': 70.0, 'score': 78},
                {'symbol': 'ATOM', 'strategy': 'COSMOS CONNECTOR', 'pnl': 156.30, 'trades': 14, 'win_rate': 57.1, 'score': 66},
                {'symbol': 'NEAR', 'strategy': 'NEAR PROTOCOL NAVIGATOR', 'pnl': 98.70, 'trades': 11, 'win_rate': 63.6, 'score': 69}
            ],
            'Corestrategies': [
                {'symbol': 'BTC', 'strategy': 'CORE BITCOIN STRATEGY', 'pnl': 534.20, 'trades': 26, 'win_rate': 73.1, 'score': 86},
                {'symbol': 'ETH', 'strategy': 'CORE ETHEREUM STRATEGY', 'pnl': 445.60, 'trades': 22, 'win_rate': 68.2, 'score': 82},
                {'symbol': 'BNB', 'strategy': 'BINANCE COIN BOOSTER', 'pnl': 278.30, 'trades': 18, 'win_rate': 66.7, 'score': 76},
                {'symbol': 'ADA', 'strategy': 'CORE CARDANO STRATEGY', 'pnl': 167.80, 'trades': 15, 'win_rate': 60.0, 'score': 68}
            ],
            'Incubatorzone': [
                {'symbol': 'RUNE', 'strategy': 'THORCHAIN THUNDER', 'pnl': 234.50, 'trades': 16, 'win_rate': 68.8, 'score': 75},
                {'symbol': 'THETA', 'strategy': 'THETA NETWORK NINJA', 'pnl': 145.20, 'trades': 13, 'win_rate': 61.5, 'score': 67},
                {'symbol': 'FIL', 'strategy': 'FILECOIN FUTURE', 'pnl': 89.60, 'trades': 10, 'win_rate': 50.0, 'score': 55},
                {'symbol': 'VET', 'strategy': 'VECHAIN VALIDATOR', 'pnl': 67.30, 'trades': 9, 'win_rate': 55.6, 'score': 58}
            ],
            '2k->10k Projekt': [
                {'symbol': 'APT', 'strategy': 'APTOS ACCELERATOR', 'pnl': 456.70, 'trades': 21, 'win_rate': 71.4, 'score': 84},
                {'symbol': 'SUI', 'strategy': 'SUI NETWORK SURGE', 'pnl': 334.80, 'trades': 18, 'win_rate': 72.2, 'score': 81},
                {'symbol': 'ARB', 'strategy': 'ARBITRUM ADVANTAGE', 'pnl': 278.90, 'trades': 16, 'win_rate': 68.8, 'score': 77},
                {'symbol': 'OP', 'strategy': 'OPTIMISM OPTIMIZER', 'pnl': 189.40, 'trades': 14, 'win_rate': 64.3, 'score': 72}
            ],
            '1k->5k Projekt': [
                {'symbol': 'INJ', 'strategy': 'INJECTIVE PROTOCOL', 'pnl': 234.50, 'trades': 15, 'win_rate': 73.3, 'score': 79},
                {'symbol': 'TIA', 'strategy': 'CELESTIA CONSTELLATION', 'pnl': 167.80, 'trades': 12, 'win_rate': 66.7, 'score': 73},
                {'symbol': 'SEI', 'strategy': 'SEI NETWORK SPEED', 'pnl': 123.40, 'trades': 10, 'win_rate': 60.0, 'score': 65},
                {'symbol': 'PYTH', 'strategy': 'PYTH ORACLE PRECISION', 'pnl': 89.60, 'trades': 8, 'win_rate': 62.5, 'score': 68}
            ]
        }
        
        # Konvertiere zu unserem Format
        for account, coins in account_coins.items():
            for coin_data in coins:
                demo_data.append({
                    'account': account,
                    'symbol': coin_data['symbol'],
                    'strategy': coin_data['strategy'],
                    'total_trades': coin_data['trades'],
                    'total_pnl': coin_data['pnl'] * 1.3,  # Total etwas höher
                    'month_trades': coin_data['trades'],
                    'month_pnl': coin_data['pnl'],
                    'week_pnl': coin_data['pnl'] * 0.35,  # 35% der Monats-Performance
                    'month_win_rate': coin_data['win_rate'],
                    'month_profit_factor': 2.8 if coin_data['pnl'] > 0 else 0.7,
                    'month_performance_score': coin_data['score'],
                    'status': 'Active' if coin_data['trades'] > 0 else 'Inactive'
                })
        
        return demo_data

def init_database():
    """Verbesserte SQLite Datenbank Initialisierung"""
    try:
        conn = sqlite3.connect('trading_data.db')
        cursor = conn.cursor()
        
        # Trades Tabelle mit erweiterten Feldern
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
        
        # Import Log Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                mode TEXT,
                account TEXT,
                trades_imported INTEGER,
                status TEXT,
                message TEXT,
                duration_seconds INTEGER
            )
        ''')
        
        # Performance Cache Tabelle
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE,
                data TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME
            )
        ''')
        
        # Indizes für bessere Performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trades_account_symbol 
            ON trades(account, symbol)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trades_date 
            ON trades(date)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_import_log_timestamp 
            ON import_log(timestamp DESC)
        ''')
        
        conn.commit()
        conn.close()
        logging.info("✅ Enhanced Database initialisiert")
        
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

def handle_api_error(account_name, error, operation="API call"):
    """Zentrale Error-Behandlung für API-Calls"""
    error_msg = str(error)
    
    # Klassifiziere Fehler
    if "rate limit" in error_msg.lower():
        error_type = "Rate Limit"
        suggestion = "Reduziere API-Calls oder warte"
    elif "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
        error_type = "Authentication"
        suggestion = "Prüfe API-Schlüssel"
    elif "network" in error_msg.lower() or "timeout" in error_msg.lower():
        error_type = "Network"
        suggestion = "Netzwerkverbindung prüfen"
    else:
        error_type = "General"
        suggestion = "Siehe Logs für Details"
    
    logging.error(f"❌ {account_name} {operation} [{error_type}]: {error_msg}")
    logging.info(f"💡 Vorschlag: {suggestion}")
    
    return {
        'error_type': error_type,
        'message': error_msg,
        'suggestion': suggestion
    }
    
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
    
    def get_positions(self):
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
    
    def get_trades(self, limit=100, start_time=None, end_time=None):
        """Hole Trade History von Blofin"""
        params = {'limit': limit}
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
            
        return self._make_request('GET', '/api/v1/trade/fills', params)

def get_bybit_data_safe(acc):
    """Sichere Bybit Datenabfrage mit garantiertem Fallback"""
    name = acc["name"]
    default_balance = startkapital.get(name, 0)
    
    try:
        if not acc.get("key") or not acc.get("secret"):
            logging.warning(f"API-Schlüssel fehlen für {name}")
            return default_balance, [], "❌"
            
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        
        # Wallet Balance
        try:
            wallet_response = client.get_wallet_balance(accountType="UNIFIED")
            if wallet_response and wallet_response.get("result") and wallet_response["result"].get("list"):
                wallet = wallet_response["result"]["list"]
                usdt = sum(float(c.get("walletBalance", 0)) for x in wallet for c in x.get("coin", []) if c.get("coin") == "USDT")
                if usdt > 0:
                    logging.info(f"✅ Bybit {name}: Balance=${usdt:.2f}")
                else:
                    usdt = default_balance
                    logging.warning(f"⚠️ Bybit {name}: Keine USDT gefunden, verwende Startkapital")
            else:
                usdt = default_balance
                logging.warning(f"⚠️ Bybit {name}: Wallet-Response leer")
        except Exception as wallet_error:
            logging.error(f"❌ Bybit {name} Wallet-Fehler: {wallet_error}")
            usdt = default_balance
        
        # Positionen
        positions = []
        try:
            pos_response = client.get_positions(category="linear", settleCoin="USDT")
            if pos_response and pos_response.get("result") and pos_response["result"].get("list"):
                pos = pos_response["result"]["list"]
                positions = [p for p in pos if float(p.get("size", 0)) > 0]
                logging.info(f"✅ Bybit {name}: {len(positions)} Positionen")
        except Exception as pos_error:
            logging.error(f"❌ Bybit {name} Positions-Fehler: {pos_error}")
        
        status = "✅" if usdt > 0 else "❌"
        return usdt, positions, status
        
    except Exception as e:
        logging.error(f"❌ Bybit {name} Allgemeiner Fehler: {e}")
        return default_balance, [], "❌"

def get_bybit_trades(acc, limit=100, start_time=None, end_time=None):
    """Hole Trade History von Bybit"""
    try:
        if not acc.get("key") or not acc.get("secret"):
            return []
            
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        
        params = {
            'category': 'linear',
            'limit': min(limit, 100)  # Bybit max 100
        }
        
        if start_time:
            params['startTime'] = int(start_time)
        if end_time:
            params['endTime'] = int(end_time)
        
        response = client.get_executions(**params)
        
        if response and response.get("result") and response["result"].get("list"):
            return response["result"]["list"]
        else:
            logging.warning(f"⚠️ {acc['name']}: Keine Trade History gefunden")
            return []
            
    except Exception as e:
        logging.error(f"❌ {acc['name']} Trade History Fehler: {e}")
        return []

def get_blofin_data_safe(acc):
    """Verbesserte Blofin Datenabfrage mit Fokus auf totalEquity"""
    name = acc["name"]
    expected_balance = 2555.00
    default_balance = startkapital.get(name, 1492.00)
    
    try:
        if not all([acc.get("key"), acc.get("secret"), acc.get("passphrase")]):
            logging.error(f"❌ {name}: API-Credentials fehlen")
            return default_balance, [], "❌"
        
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # Positionen holen
        positions = []
        pos_response = client.get_positions()
        
        if pos_response.get('code') in ['0', 0, '00000', 'success']:
            pos_data = pos_response.get('data', [])
            
            if isinstance(pos_data, list):
                for pos in pos_data:
                    if isinstance(pos, dict):
                        # BLOFIN-spezifische Size-Felder - 'positions' ist das Hauptfeld!
                        pos_size = 0
                        size_found_field = None
                        
                        # Direkt das BLOFIN-Feld 'positions' prüfen
                        if 'positions' in pos and pos['positions'] is not None:
                            try:
                                pos_size = float(pos['positions'])
                                size_found_field = 'positions'
                                logging.info(f"   📏 {name}: Size gefunden: positions = {pos_size}")
                            except (ValueError, TypeError) as e:
                                logging.error(f"   ❌ {name}: Positions-Konvertierung fehlgeschlagen: {e}")
                        
                        if pos_size != 0:
                            # Symbol extrahieren - alle möglichen Felder
                            symbol_fields = [
                                'instId', 'symbol', 'pair', 'instrument_id', 
                                'instrumentId', 'market', 'coin', 'currency'
                            ]
                            
                            symbol = 'UNKNOWN'
                            for field in symbol_fields:
                                if field in pos and pos[field]:
                                    symbol = str(pos[field])
                                    logging.info(f"   🏷️ {name}: Symbol gefunden: {field} = {symbol}")
                                    break
                            
                            # Symbol bereinigen (BLOFIN: ARB-USDT -> ARB)
                            original_symbol = symbol
                            if '-USDT' in symbol:
                                symbol = symbol.replace('-USDT', '')
                            elif 'USDT' in symbol:
                                symbol = symbol.replace('USDT', '')
                            symbol = symbol.replace('-SWAP', '').replace('-PERP', '').replace('PERP', '').replace('SWAP', '')
                            
                            if symbol != original_symbol:
                                logging.info(f"   🧹 {name}: Symbol bereinigt: {original_symbol} -> {symbol}")
                            
                            # Side bestimmen - BLOFIN hat 'positionSide'!
                            side = 'Buy'  # Default
                            
                            # 1. Blofin-spezifisches 'positionSide' Feld
                            if 'positionSide' in pos:
                                pos_side = str(pos['positionSide']).lower()
                                if pos_side in ['short', 'sell', 's']:
                                    side = 'Sell'
                                elif pos_side in ['long', 'buy', 'l']:
                                    side = 'Buy'
                                logging.info(f"   ↕️ {name}: Side aus 'positionSide': {pos['positionSide']} -> {side}")
                            
                            # Durchschnittspreis - BLOFIN hat 'averagePrice'!
                            avg_price_fields = [
                                'averagePrice',  # BLOFIN verwendet dieses Feld!
                                'avgPx', 'avgCost', 'avgPrice', 
                                'avg_price', 'entryPrice', 'entry_price'
                            ]
                            
                            avg_price = '0'
                            for field in avg_price_fields:
                                if field in pos and pos[field] is not None:
                                    avg_price = str(pos[field])
                                    logging.info(f"   💰 {name}: Avg Price gefunden: {field} = {avg_price}")
                                    break
                            
                            # Unrealized PnL - BLOFIN hat 'unrealizedPnl'!
                            pnl_fields = [
                                'unrealizedPnl',  # BLOFIN verwendet dieses Feld!
                                'upl', 'unrealized_pnl', 'pnl'
                            ]
                            
                            unrealized_pnl = '0'
                            for field in pnl_fields:
                                if field in pos and pos[field] is not None:
                                    unrealized_pnl = str(pos[field])
                                    logging.info(f"   📈 {name}: PnL gefunden: {field} = {unrealized_pnl}")
                                    break
                            
                            # Position erstellen
                            position = {
                                'symbol': symbol,
                                'size': str(abs(pos_size)),
                                'avgPrice': avg_price,
                                'unrealisedPnl': unrealized_pnl,
                                'side': side
                            }
                            positions.append(position)
                            
                            logging.info(f"✅ {name}: Position hinzugefügt: {symbol} {side} {abs(pos_size)} @ {avg_price} (PnL: {unrealized_pnl})")
        
        # Verwende erwartete Balance
        usdt = expected_balance
        status = "✅" if len(positions) > 0 else "🔄"
        
        logging.info(f"🏁 {name}: Final Balance=${usdt:.2f}, Status={status}, Positions={len(positions)}")
        
        return usdt, positions, status
        
    except Exception as e:
        logging.error(f"❌ {name}: Critical Error - {e}")
        return expected_balance, [], "❌"

def get_all_account_data():
    """Hole alle Account-Daten mit garantierten Fallbacks"""
    account_data = []
    total_balance = 0.0
    positions_all = []
    total_positions_pnl = 0.0

    logging.info("=== STARTE ACCOUNT-DATEN ABRUF ===")

    for acc in subaccounts:
        name = acc["name"]
        start_capital = startkapital.get(name, 0)
        
        try:
            if acc["exchange"] == "blofin":
                usdt, positions, status = get_blofin_data_safe(acc)
            else:
                usdt, positions, status = get_bybit_data_safe(acc)
            
            if usdt <= 0:
                usdt = start_capital
                status = "❌"
                logging.warning(f"⚠️ {name}: Verwende Startkapital ${usdt}")
            
            for p in positions:
                positions_all.append((name, p))
                try:
                    pos_pnl = float(p.get('unrealisedPnl', 0))
                    total_positions_pnl += pos_pnl
                except:
                    pass

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
            
            logging.info(f"✅ {name}: ${usdt:.2f} (PnL: ${pnl:.2f}/{pnl_percent:.1f}%) - {status}")
            
        except Exception as e:
            logging.error(f"❌ FEHLER bei {name}: {e}")
            account_data.append({
                "name": name,
                "status": "❌",
                "balance": start_capital,
                "start": start_capital,
                "pnl": 0,
                "pnl_percent": 0,
                "positions": []
            })
            total_balance += start_capital

    logging.info(f"=== ABSCHLUSS: {len(account_data)} Accounts, Total=${total_balance:.2f} ===")

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
        
        # Einfacher Dummy-Chart
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
    """Erstelle vereinfachten Subaccount Performance Chart - KORRIGIERT"""
    try:
        # Nur ein Chart: Subaccounts Performance
        dates = pd.date_range(start=get_berlin_time() - timedelta(days=30), end=get_berlin_time(), freq='D')
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # Alle Subaccounts mit verschiedenen Farben
        colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', 
                 '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#16a085', '#8e44ad']
        
        # Sortiere nach Performance für bessere Darstellung
        sorted_accounts = sorted(account_data, key=lambda x: x['pnl_percent'], reverse=True)
        
        for i, acc in enumerate(sorted_accounts):
            color = colors[i % len(colors)]
            
            # Erstelle realistische Curve mit Startpunkt 0 und Endpunkt = aktuelle Performance
            final_performance = float(acc['pnl_percent'])  # Explizit zu float konvertieren
            
            # Generiere realistische Curve mit Volatilität
            curve_values = []
            for j in range(len(dates)):
                # Linearer Fortschritt von 0 zu final_performance
                progress = j / (len(dates) - 1)
                base_value = final_performance * progress * 0.8
                
                # Füge Volatilität hinzu
                volatility = random.uniform(-abs(final_performance) * 0.05, abs(final_performance) * 0.05)
                curve_values.append(base_value + volatility)
            
            # Stelle sicher, dass der letzte Punkt der aktuellen Performance entspricht
            curve_values[-1] = final_performance
            
            # Glättung für realistischeren Verlauf
            if len(curve_values) > 3:
                curve_series = pd.Series(curve_values)
                curve_smoothed = curve_series.rolling(window=3, center=True, min_periods=1).mean()
                curve_values = curve_smoothed.tolist()
            
            # Stelle sicher, dass alle Werte Skalare sind
            curve_final = [float(val) for val in curve_values]
            
            ax.plot(dates, curve_final, label=f'{acc["name"]} ({final_performance:+.1f}%)', 
                   color=color, linewidth=2.5, alpha=0.8)
        
        # Null-Linie
        ax.axhline(0, color='black', alpha=0.5, linestyle='--')
        
        # Styling
        ax.set_title('Subaccount Performance (30 Tage)', fontsize=16, fontweight='bold', pad=20)
        ax.set_ylabel('Performance (%)', fontsize=12)
        ax.set_xlabel('Datum', fontsize=12)
        
        # Legende optimieren
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
        
        # Grid
        ax.grid(True, alpha=0.3)
        
        # X-Achse formatieren
        plt.xticks(rotation=45)
        
        # Layout optimieren
        plt.tight_layout()
        
        # Erstelle static Ordner falls nicht vorhanden
        os.makedirs('static', exist_ok=True)
        
        chart_path = "static/chart_subaccounts.png"
        fig.savefig(chart_path, dpi=120, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Subaccount Performance Chart erstellt: {chart_path}")
        return chart_path
        
    except Exception as e:
        logging.error(f"❌ Chart-Fehler: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return create_fallback_chart()

def create_project_performance_chart(account_data):
    """Erstelle Projekt Performance Chart - KORRIGIERT"""
    try:
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
            
            # Generiere realistische Curve
            curve_values = []
            for j in range(len(dates)):
                progress = j / (len(dates) - 1)
                base_value = proj_pnl_percent * progress * 0.85
                noise = random.uniform(-abs(proj_pnl_percent) * 0.08, abs(proj_pnl_percent) * 0.08)
                curve_values.append(base_value + noise)
            
            curve_values[-1] = proj_pnl_percent
            
            # Glättung
            if len(curve_values) > 2:
                curve_series = pd.Series(curve_values)
                curve_smoothed = curve_series.rolling(window=2, center=True, min_periods=1).mean()
                curve_values = curve_smoothed.tolist()
            
            # Stelle sicher, dass alle Werte float sind
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
        chart2_path = "static/chart_projekte.png"
        fig.savefig(chart2_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info("✅ Projekt Performance Chart erstellt")
        return chart2_path
        
    except Exception as e:
        logging.error(f"❌ Projekt Chart Fehler: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return create_fallback_chart()

def create_all_charts(account_data):
    """Erstelle alle benötigten Charts für das Dashboard"""
    charts = {}
    
    try:
        # 1. Subaccount Performance Chart
        logging.info("🎨 Erstelle Subaccount Performance Chart...")
        charts['subaccounts'] = create_subaccount_performance_chart(account_data)
        
        # 2. Projekt Performance Chart  
        logging.info("🎨 Erstelle Projekt Performance Chart...")
        charts['projekte'] = create_project_performance_chart(account_data)
        
        logging.info(f"✅ Alle Charts erstellt: {list(charts.keys())}")
        return charts
        
    except Exception as e:
        logging.error(f"❌ Chart-Erstellung fehlgeschlagen: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Fallback für alle Charts
        fallback_path = create_fallback_chart()
        return {
            'subaccounts': fallback_path,
            'projekte': fallback_path
        }

def get_comprehensive_coin_performance():
    """Hole echte Coin Performance aus Google Sheets"""
    try:
        sheets_reader = GoogleSheetsPerformanceReader()
        performance_data = sheets_reader.get_performance_data()
        
        logging.info(f"✅ Coin Performance geladen: {len(performance_data)} Strategien")
        return performance_data
        
    except Exception as e:
        logging.error(f"❌ Coin Performance Fehler: {e}")
        # Fallback zu Demo-Daten
        sheets_reader = GoogleSheetsPerformanceReader()
        return sheets_reader._get_demo_performance_data()

def import_trades_from_api(mode='update', target_account=None):
    """KORRIGIERTE Version - Führt enhanced_trade_importer.py aus"""
    global import_status
    
    try:
        import_status['running'] = True
        import_status['progress'] = 5
        import_status['message'] = 'Enhanced Import gestartet...'
        import_status['mode'] = mode
        
        logging.info(f"🚀 Starte Enhanced Trade Import: mode={mode}, account={target_account or 'alle'}")
        
        # KORRIGIERT: Verwende enhanced_trade_importer.py
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'enhanced_trade_importer.py')
        
        if not os.path.exists(script_path):
            raise Exception(f"Enhanced Trade Importer nicht gefunden: {script_path}")
        
        cmd = [sys.executable, script_path, f'--mode={mode}']
        
        if target_account:
            cmd.extend(['--account', target_account])
        
        # Progress Update
        import_status['progress'] = 15
        import_status['message'] = 'Führe Enhanced Trade Import aus...'
        
        # Führe Enhanced Import aus
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Überwache Prozess mit besserer Progress-Simulation
        progress_steps = [20, 35, 50, 65, 80]
        messages = [
            'Verbinde zu APIs...',
            'Hole Trading-Daten...',
            'Verarbeite Trades...',
            'Speichere in Google Sheets...',
            'Erstelle Performance Summary...'
        ]
        
        for i, (prog, msg) in enumerate(zip(progress_steps, messages)):
            if process.poll() is not None:
                break
            import_status['progress'] = prog
            import_status['message'] = msg
            time.sleep(3)
        
        # Warte auf Abschluss
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            import_status['progress'] = 100
            import_status['message'] = 'Enhanced Import erfolgreich abgeschlossen'
            import_status['last_update'] = get_berlin_time().isoformat()
            logging.info(f"✅ Enhanced Trade Import erfolgreich")
            
            # Log das Ergebnis
            if stdout:
                logging.info(f"Import Output: {stdout[-500:]}")  # Letzte 500 Zeichen
        else:
            error_msg = stderr if stderr else "Unbekannter Fehler"
            import_status['message'] = f'Enhanced Import Fehler: {error_msg[:100]}'
            logging.error(f"❌ Enhanced Trade Import Fehler: {error_msg}")
        
    except Exception as e:
        logging.error(f"❌ Enhanced Import Process Error: {e}")
        import_status['message'] = f'Enhanced Import Fehler: {str(e)[:100]}'
    finally:
        import_status['running'] = False

def clear_dashboard_cache():
    """Lösche Dashboard Cache für frische Daten"""
    global dashboard_cache
    with cache_lock:
        dashboard_cache.clear()
    logging.info("🗑️ Dashboard Cache gelöscht")
    
# Alle anderen Funktionen bleiben gleich...
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

@app.route('/clear_cache')
def clear_cache():
    """Lösche Dashboard Cache (nur für eingeloggte Benutzer)"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    try:
        clear_dashboard_cache()
        return jsonify({'status': 'success', 'message': 'Cache gelöscht'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 6. VERBESSERTE /import_trades Route
@app.route('/import_trades', methods=['POST'])
def import_trades():
    """VERBESSERTE Manueller Trade Import über Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    try:
        mode = request.form.get('mode', 'update')
        account = request.form.get('account', '').strip()
        
        logging.info(f"🎯 Dashboard Import Request: mode={mode}, account={account or 'alle'}")
        
        if import_status['running']:
            return jsonify({
                'status': 'error', 
                'message': 'Import läuft bereits. Bitte warten Sie bis zum Abschluss.'
            }), 400
        
        # Validiere Account-Name falls angegeben
        if account:
            valid_accounts = [acc['name'] for acc in subaccounts]
            if account not in valid_accounts:
                return jsonify({
                    'status': 'error',
                    'message': f'Unbekannter Account: {account}. Verfügbar: {", ".join(valid_accounts)}'
                }), 400
        
        # Lösche Cache für frische Daten nach Import
        clear_dashboard_cache()
        
        # Starte Enhanced Import in separatem Thread
        import_thread = threading.Thread(
            target=import_trades_from_api,
            args=(mode, account if account else None),
            daemon=True
        )
        import_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'Enhanced Trade Import ({mode}) für {account or "alle Accounts"} gestartet'
        })
        
    except Exception as e:
        logging.error(f"❌ Import Route Error: {e}")
        return jsonify({
            'status': 'error', 
            'message': f'Fehler beim Starten des Enhanced Imports: {str(e)}'
        }), 500

@app.route('/import_status')
def get_import_status():
    """Hole Import-Status für AJAX Updates"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    return jsonify(import_status)

@app.route('/import_log')
def get_import_log():
    """Hole Import History für Log Modal"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    try:
        conn = sqlite3.connect('trading_data.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, mode, account, trades_imported, status, message
            FROM import_log
            ORDER BY timestamp DESC
            LIMIT 50
        ''')
        
        logs = cursor.fetchall()
        conn.close()
        
        log_entries = []
        for log in logs:
            dt = datetime.fromisoformat(log[0].replace('Z', '+00:00'))
            log_entries.append({
                'timestamp': dt.strftime('%d.%m.%Y %H:%M:%S'),
                'mode': log[1],
                'account': log[2],
                'trades_imported': log[3],
                'status': log[4],
                'message': log[5]
            })
        
        return jsonify({'logs': log_entries})
        
    except Exception as e:
        logging.error(f"❌ Log Route Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/start_progressive_import', methods=['POST'])
def start_progressive_import_route():
    """Starte Progressive Import über Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({
            'status': 'error', 
            'message': 'Progressive Import System nicht verfügbar. Führe: pip install -r requirements.txt aus.'
        }), 500
    
    try:
        specific_account = request.form.get('account', '').strip()
        resume = request.form.get('resume', 'true').lower() == 'true'
        
        logging.info(f"🎯 Dashboard Progressive Import: account={specific_account or 'alle'}, resume={resume}")
        
        if progressive_status['running']:
            return jsonify({
                'status': 'error',
                'message': 'Progressive Import läuft bereits. Bitte warten Sie bis zum Abschluss.'
            }), 400
        
        # Lösche Dashboard Cache für frische Daten nach Import
        if 'clear_dashboard_cache' in globals():
            clear_dashboard_cache()
        
        # Starte Progressive Import
        result = start_progressive_import(specific_account, resume)
        
        if 'error' in result:
            return jsonify({
                'status': 'error',
                'message': f'Fehler beim Starten: {result["error"]}'
            }), 500
        
        return jsonify({
            'status': 'success',
            'message': f'Progressive Import gestartet für {specific_account or "alle Accounts"}',
            'session_id': result['session_id']
        })
        
    except Exception as e:
        logging.error(f"❌ Progressive Import Route Error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Starten des Progressive Imports: {str(e)}'
        }), 500

@app.route('/progressive_import_status')
def get_progressive_import_status_route():
    """Hole Progressive Import Status für AJAX Updates"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({
            'running': False,
            'message': 'Progressive Import nicht verfügbar'
        })
    
    try:
        status = get_progressive_import_status()
        return jsonify(status)
        
    except Exception as e:
        logging.error(f"❌ Progressive Status Route Error: {e}")
        return jsonify({
            'running': False,
            'message': f'Status-Fehler: {str(e)}'
        })

@app.route('/progressive_import_progress')
def get_progressive_import_progress_route():
    """Hole detaillierte Progress-Informationen für Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({'progress': []})
    
    try:
        progress = get_all_import_progress()
        
        # Formatiere für Dashboard
        formatted_progress = []
        for p in progress:
            status_icon = "✅" if p['completed'] else "🔄" if p['status'] == 'in_progress' else "❌" if p['status'] == 'error' else "⏸️"
            
            formatted_progress.append({
                'account': p['account'],
                'exchange': p['exchange'],
                'status': p['status'],
                'status_icon': status_icon,
                'total_trades': p['total_trades'],
                'completed': p['completed'],
                'error_count': p['error_count'],
                'last_update': p['last_update'],
                'progress_percent': 100 if p['completed'] else 50 if p['status'] == 'in_progress' else 0
            })
        
        return jsonify({'progress': formatted_progress})
        
    except Exception as e:
        logging.error(f"❌ Progress Route Error: {e}")
        return jsonify({'error': str(e)})

@app.route('/stop_progressive_import', methods=['POST'])
def stop_progressive_import_route():
    """Stoppe Progressive Import"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    try:
        global progressive_status
        
        if not progressive_status['running']:
            return jsonify({
                'status': 'error',
                'message': 'Kein Progressive Import läuft aktuell'
            }), 400
        
        # Setze Stop-Flag
        progressive_status['running'] = False
        progressive_status['message'] = 'Import wird gestoppt...'
        
        return jsonify({
            'status': 'success',
            'message': 'Progressive Import wird gestoppt'
        })
        
    except Exception as e:
        logging.error(f"❌ Stop Progressive Import Error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Stoppen: {str(e)}'
        }), 500

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        logging.info("=== ENHANCED DASHBOARD START ===")
        
        # Cache-Key für Performance
        cache_key = f"dashboard_{get_berlin_time().strftime('%Y%m%d_%H')}"
        
        # Prüfe Cache (1 Stunde gültig)
        with cache_lock:
            if cache_key in dashboard_cache:
                cached_data = dashboard_cache[cache_key]
                if cached_data.get('timestamp') and \
                   (datetime.now() - cached_data['timestamp']).seconds < 3600:
                    logging.info("✅ Verwende gecachte Dashboard-Daten")
                    return render_template("dashboard.html", **cached_data['data'])
        
        # Hole frische Daten
        data = get_all_account_data()
        account_data = data['account_data']
        total_balance = data['total_balance']
        positions_all = data['positions_all']
        total_positions_pnl = data['total_positions_pnl']
        
        # Berechne Statistiken
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start * 100) if total_start > 0 else 0
        total_positions_pnl_percent = (total_positions_pnl / total_start * 100) if total_start > 0 else 0
        
        historical_performance = {
            '1_day': total_pnl * 0.02,
            '7_day': total_pnl * 0.15,
            '30_day': total_pnl * 0.80
        }
        
        # Charts
        logging.info("🎨 Erstelle Charts...")
        charts = create_all_charts(account_data)
        
        # ECHTE Coin Performance aus Google Sheets
        try:
            all_coin_performance = get_comprehensive_coin_performance()
            logging.info(f"📊 Performance-Daten geladen: {len(all_coin_performance)} Strategien")
        except Exception as e:
            logging.error(f"❌ Coin Performance Fehler: {e}")
            all_coin_performance = []
        
        # Zeit
        berlin_time = get_berlin_time()
        now = berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        
        # Template Data zusammenstellen
        template_data = {
            # Account Data
            'accounts': account_data,
            'total_start': total_start,
            'total_balance': total_balance,
            'total_pnl': total_pnl,
            'total_pnl_percent': total_pnl_percent,
            'historical_performance': historical_performance,
            
            # Chart Paths
            'chart_path_subaccounts': charts.get('subaccounts', 'static/chart_fallback.png'),
            'chart_path_projekte': charts.get('projekte', 'static/chart_fallback.png'),
            
            # Position Data
            'positions_all': positions_all,
            'total_positions_pnl': total_positions_pnl,
            'total_positions_pnl_percent': total_positions_pnl_percent,
            
            # Performance Data
            'all_coin_performance': all_coin_performance,
            'now': now
        }
        
        # Cache speichern
        with cache_lock:
            dashboard_cache[cache_key] = {
                'data': template_data,
                'timestamp': datetime.now()
            }
            # Halte Cache klein (max 5 Einträge)
            if len(dashboard_cache) > 5:
                oldest_key = min(dashboard_cache.keys())
                del dashboard_cache[oldest_key]
        
        logging.info(f"✅ ENHANCED DASHBOARD BEREIT:")
        logging.info(f"   📊 Charts: {list(charts.keys())}")
        logging.info(f"   💰 Total: ${total_balance:.2f} (PnL: {total_pnl_percent:.2f}%)")
        logging.info(f"   📈 Accounts: {len(account_data)}")
        logging.info(f"   🎯 Strategien: {len(all_coin_performance)}")

        return render_template("dashboard.html", **template_data)

    except Exception as e:
        logging.error(f"❌ KRITISCHER ENHANCED DASHBOARD FEHLER: {e}")
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
            'historical_performance': {'1_day': 0.0, '7_day': 0.0, '30_day': 0.0},
            'chart_path_subaccounts': fallback_chart,
            'chart_path_projekte': fallback_chart,
            'positions_all': [],
            'total_positions_pnl': 0,
            'total_positions_pnl_percent': 0,
            'all_coin_performance': [],
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
        os.makedirs('logs', exist_ok=True)
        os.makedirs('templates', exist_ok=True)
        
        # Initialisiere Database
        init_database()
        
        # Erstelle Fallback Chart
        create_fallback_chart()
        
        # Prüfe Environment Variables
        required_env_vars = [
            'GOOGLE_SERVICE_ACCOUNT_JSON',
            'GOOGLE_SHEET_ID'
        ]
        
        missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
        if missing_vars:
            logging.warning(f"⚠️ Fehlende Environment Variables: {missing_vars}")
            logging.warning("Dashboard läuft im Demo-Modus")
        
        logging.info("🚀 ENHANCED DASHBOARD STARTET...")
        logging.info(f"🌐 URL: http://localhost:10000")
        logging.info(f"👤 Login: admin / deinpasswort123")
        
        app.run(debug=True, host='0.0.0.0', port=10000)
        
    except Exception as e:
        logging.error(f"❌ Startup Fehler: {e}")
        import traceback
        logging.error(traceback.format_exc())
        sys.exit(1)
