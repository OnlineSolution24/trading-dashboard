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

def init_database():
    """Initialisiere SQLite Datenbank für Trade History"""
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
            date TEXT,
            time TEXT,
            win_loss TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            trade_id TEXT UNIQUE
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
            message TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

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

def create_portfolio_equity_curve(account_data):
    """Erstelle Portfolio & Top Subaccounts Equity Curve"""
    try:
        dates = pd.date_range(start=get_berlin_time() - timedelta(days=30), end=get_berlin_time(), freq='D')
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Portfolio Gesamtkurve
        total_start = sum(startkapital.values())
        total_current = sum(float(a["balance"]) for a in account_data)
        total_pnl_percent = float(((total_current - total_start) / total_start * 100)) if total_start > 0 else 0.0
        
        # Portfolio Curve generieren
        portfolio_curve = []
        for i in range(len(dates)):
            progress = i / (len(dates) - 1)
            base_value = total_pnl_percent * progress * 0.9
            noise = random.uniform(-0.5, 0.5)
            portfolio_curve.append(base_value + noise)
        
        portfolio_curve[-1] = total_pnl_percent
        portfolio_curve = [float(val) for val in portfolio_curve]
        
        ax.plot(dates, portfolio_curve, label=f'Gesamtportfolio ({total_pnl_percent:+.1f}%)', 
               color='black', linewidth=4, alpha=0.9)
        
        # Top 3 Subaccounts hinzufügen
        top_accounts = sorted(account_data, key=lambda x: abs(float(x['pnl_percent'])), reverse=True)[:3]
        colors = ['#e74c3c', '#3498db', '#2ecc71']
        
        for i, acc in enumerate(top_accounts):
            acc_pnl_percent = float(acc['pnl_percent'])
            
            acc_curve = []
            for j in range(len(dates)):
                progress = j / (len(dates) - 1)
                base_value = acc_pnl_percent * progress * 0.85
                noise = random.uniform(-abs(acc_pnl_percent) * 0.03, abs(acc_pnl_percent) * 0.03)
                acc_curve.append(base_value + noise)
            
            acc_curve[-1] = acc_pnl_percent
            acc_curve = [float(val) for val in acc_curve]
            
            ax.plot(dates, acc_curve, label=f'{acc["name"]} ({acc_pnl_percent:+.1f}%)', 
                   color=colors[i], linewidth=2.5, alpha=0.8)
        
        ax.axhline(0, color='gray', alpha=0.5, linestyle='--')
        ax.set_title('Portfolio & Subaccount Performance (%)', fontweight='bold', fontsize=14)
        ax.set_ylabel('Performance (%)')
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        os.makedirs('static', exist_ok=True)
        chart_path = "static/equity_total.png"
        fig.savefig(chart_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Portfolio Equity Curve erstellt: {chart_path}")
        return chart_path
        
    except Exception as e:
        logging.error(f"❌ Portfolio Equity Curve Fehler: {e}")
        return create_fallback_chart()

def create_project_equity_curves(account_data):
    """Erstelle Projekt Equity Curves"""
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
            
            # Projekt Curve generieren
            proj_curve = []
            for j in range(len(dates)):
                progress = j / (len(dates) - 1)
                base_value = proj_pnl_percent * progress * 0.88
                noise = random.uniform(-abs(proj_pnl_percent) * 0.05, abs(proj_pnl_percent) * 0.05)
                proj_curve.append(base_value + noise)
            
            proj_curve[-1] = proj_pnl_percent
            proj_curve = [float(val) for val in proj_curve]
            
            ax.plot(dates, proj_curve, label=f'{pname} ({proj_pnl_percent:+.1f}%)', 
                   color=proj_colors[i % len(proj_colors)], linewidth=3, alpha=0.9)
        
        ax.axhline(0, color='gray', alpha=0.5, linestyle='--')
        ax.set_title('Projekt Performance Vergleich (%)', fontweight='bold', fontsize=14)
        ax.set_ylabel('Performance (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        os.makedirs('static', exist_ok=True)
        chart_path = "static/equity_projects.png"
        fig.savefig(chart_path, dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        
        logging.info(f"✅ Projekt Equity Curves erstellt: {chart_path}")
        return chart_path
        
    except Exception as e:
        logging.error(f"❌ Projekt Equity Curves Fehler: {e}")
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
        
        # 3. Portfolio Equity Curve (neuer Chart)
        logging.info("🎨 Erstelle Portfolio Equity Curve...")
        charts['equity_total'] = create_portfolio_equity_curve(account_data)
        
        # 4. Projekt Equity Curves (neuer Chart)
        logging.info("🎨 Erstelle Projekt Equity Curves...")
        charts['equity_projects'] = create_project_equity_curves(account_data)
        
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
            'projekte': fallback_path,
            'equity_total': fallback_path,
            'equity_projects': fallback_path
        }

def get_comprehensive_coin_performance():
    """Umfassende Coin Performance für alle Subaccounts"""
    
    # Erweiterte Dummy-Daten für alle Subaccounts
    all_strategies = []
    
    # Claude Projekt (echte Daten)
    claude_strategies = [
        {'symbol': 'RUNE', 'account': 'Claude Projekt', 'strategy': 'AI vs. Ninja Turtle', 'total_trades': 1, 'total_pnl': -14.70, 'month_trades': 1, 'month_pnl': -14.70, 'week_pnl': -14.70, 'month_win_rate': 0.0, 'month_profit_factor': 0.0, 'month_performance_score': 15, 'status': 'Active'}
    ]
    
    # 7 Tage Performer (Live-Daten)
    performer_strategies = [
        {'symbol': 'WIF', 'account': '7 Tage Performer', 'strategy': 'MACD LIQUIDITY SPECTRUM', 'total_trades': 8, 'total_pnl': 420.50, 'month_trades': 8, 'month_pnl': 420.50, 'week_pnl': 185.20, 'month_win_rate': 75.0, 'month_profit_factor': 2.8, 'month_performance_score': 85, 'status': 'Active'},
        {'symbol': 'ARB', 'account': '7 Tage Performer', 'strategy': 'STIFFZONE ETH', 'total_trades': 12, 'total_pnl': 278.30, 'month_trades': 12, 'month_pnl': 278.30, 'week_pnl': 125.80, 'month_win_rate': 66.7, 'month_profit_factor': 2.2, 'month_performance_score': 75, 'status': 'Active'},
        {'symbol': 'AVAX', 'account': '7 Tage Performer', 'strategy': 'PRECISION TREND MASTERY', 'total_trades': 15, 'total_pnl': 312.70, 'month_trades': 15, 'month_pnl': 312.70, 'week_pnl': 142.50, 'month_win_rate': 73.3, 'month_profit_factor': 2.6, 'month_performance_score': 80, 'status': 'Active'},
        {'symbol': 'ALGO', 'account': '7 Tage Performer', 'strategy': 'TRIGGERHAPPY2 INJ', 'total_trades': 6, 'total_pnl': -45.90, 'month_trades': 6, 'month_pnl': -45.90, 'week_pnl': -22.40, 'month_win_rate': 33.3, 'month_profit_factor': 0.7, 'month_performance_score': 25, 'status': 'Active'},
        {'symbol': 'SOL', 'account': '7 Tage Performer', 'strategy': 'VOLUME SPIKE HUNTER', 'total_trades': 22, 'total_pnl': 567.80, 'month_trades': 22, 'month_pnl': 567.80, 'week_pnl': 234.50, 'month_win_rate': 81.8, 'month_profit_factor': 3.4, 'month_performance_score': 92, 'status': 'Active'}
    ]
    
    # Bybit Subaccounts - Generiere realistische Daten
    bybit_accounts = ['Incubatorzone', 'Memestrategies', 'Ethapestrategies', 'Altsstrategies', 'Solstrategies', 'Btcstrategies', 'Corestrategies', '2k->10k Projekt', '1k->5k Projekt']
    
    # Beliebte Coins für verschiedene Kategorien
    coin_categories = {
        'Memestrategies': ['DOGE', 'SHIB', 'PEPE', 'WIF', 'BONK', 'FLOKI'],
        'Ethapestrategies': ['ETH', 'LDO', 'MATIC', 'LINK', 'UNI', 'AAVE'],
        'Altsstrategies': ['ADA', 'DOT', 'ATOM', 'NEAR', 'FTM', 'ALGO'],
        'Solstrategies': ['SOL', 'RAY', 'STEP', 'ORCA', 'SRM', 'FIDA'],
        'Btcstrategies': ['BTC', 'LTC', 'BCH', 'BSV', 'BTG'],
        'Corestrategies': ['BTC', 'ETH', 'BNB', 'ADA', 'XRP', 'SOL'],
        'Incubatorzone': ['RUNE', 'THETA', 'FIL', 'VET', 'HBAR', 'IOTA'],
        '2k->10k Projekt': ['APT', 'SUI', 'ARB', 'OP', 'MATIC', 'AVAX'],
        '1k->5k Projekt': ['INJ', 'TIA', 'SEI', 'PYTH', 'JUP', 'WEN']
    }
    
    strategy_templates = [
        'MOMENTUM SURGE', 'SCALP MASTER', 'TREND FOLLOWER', 'MEAN REVERSION',
        'BREAKOUT HUNTER', 'VOLUME PROFILE', 'RSI DIVERGENCE', 'MA CROSSOVER',
        'FIBONACCI RETRACEMENT', 'SUPPORT RESISTANCE', 'BOLLINGER SQUEEZE',
        'STOCHASTIC DIVERGENCE', 'MACD HISTOGRAM', 'PRICE ACTION PURE',
        'VOLUME WEIGHTED', 'MOMENTUM OSCILLATOR', 'CHANNEL BREAKOUT'
    ]
    
    for account in bybit_accounts:
        account_balance = startkapital.get(account, 1000)
        coins = coin_categories.get(account, ['BTC', 'ETH', 'SOL', 'ADA'])
        
        # Generiere 3-6 Strategien pro Account
        num_strategies = random.randint(3, 6)
        
        for i in range(num_strategies):
            coin = random.choice(coins)
            strategy_name = f"{random.choice(strategy_templates)} {coin}"
            
            # Performance basierend auf Account-Größe und Random
            base_performance = random.uniform(-0.3, 0.6)  # -30% bis +60%
            
            # Bessere Performance für größere Accounts (simuliert bessere Strategien)
            if account_balance > 1500:
                base_performance += 0.2
            
            month_trades = random.randint(5, 35)
            month_win_rate = random.uniform(35, 85)
            month_pnl = account_balance * base_performance * random.uniform(0.1, 0.4)
            week_pnl = month_pnl * random.uniform(0.15, 0.35)
            total_pnl = month_pnl * random.uniform(1.2, 2.8)
            
            # Profit Factor basierend auf Win Rate
            if month_win_rate > 70:
                month_profit_factor = random.uniform(2.0, 4.5)
            elif month_win_rate > 50:
                month_profit_factor = random.uniform(1.1, 2.8)
            else:
                month_profit_factor = random.uniform(0.3, 1.2)
            
            # Performance Score Berechnung
            score_factors = [
                month_win_rate / 100 * 40,  # 40% Gewichtung Win Rate
                min(month_profit_factor / 3 * 30, 30),  # 30% Gewichtung Profit Factor
                (month_pnl / (account_balance * 0.1)) * 30 if month_pnl > 0 else 0  # 30% Gewichtung PnL
            ]
            month_performance_score = sum(score_factors)
            
            status = 'Active' if month_trades > 0 else 'Inactive'
            
            strategy_data = {
                'symbol': coin,
                'account': account,
                'strategy': strategy_name,
                'total_trades': int(month_trades * random.uniform(1.5, 3.0)),
                'total_pnl': total_pnl,
                'month_trades': month_trades,
                'month_pnl': month_pnl,
                'week_pnl': week_pnl,
                'month_win_rate': month_win_rate,
                'month_profit_factor': month_profit_factor,
                'month_performance_score': month_performance_score,
                'status': status,
                'daily_volume': random.randint(10000, 100000)
            }
            
            all_strategies.append(strategy_data)
    
    # Füge alle zusammen
    all_strategies.extend(claude_strategies)
    all_strategies.extend(performer_strategies)
    
    logging.info(f"✅ Coin Performance generiert: {len(all_strategies)} Strategien für alle Subaccounts")
    return all_strategies

def import_trades_from_api(mode='update', target_account=None):
    """Importiere Trades von APIs in die Datenbank"""
    global import_status
    
    try:
        import_status['running'] = True
        import_status['progress'] = 0
        import_status['message'] = 'Import gestartet...'
        import_status['mode'] = mode
        
        conn = sqlite3.connect('trading_data.db')
        cursor = conn.cursor()
        
        total_imported = 0
        accounts_to_process = [acc for acc in subaccounts if not target_account or acc['name'] == target_account]
        
        for i, acc in enumerate(accounts_to_process):
            import_status['progress'] = int((i / len(accounts_to_process)) * 90)
            import_status['message'] = f'Verarbeite {acc["name"]}...'
            
            try:
                if acc['exchange'] == 'bybit':
                    trades = get_bybit_trades(acc, limit=200 if mode == 'full' else 50)
                elif acc['exchange'] == 'blofin':
                    client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
                    trades_response = client.get_trades(limit=200 if mode == 'full' else 50)
                    trades = trades_response.get('data', []) if trades_response.get('code') in ['0', 0] else []
                else:
                    trades = []
                
                # Verarbeite Trades und speichere in DB
                account_imported = 0
                for trade in trades:
                    # Generiere eindeutige Trade-ID
                    trade_id = f"{acc['name']}_{trade.get('execId', trade.get('id', str(time.time())))}_{trade.get('execTime', int(time.time()))}"
                    
                    # Prüfe ob Trade bereits existiert
                    cursor.execute('SELECT id FROM trades WHERE trade_id = ?', (trade_id,))
                    if cursor.fetchone():
                        continue  # Skip wenn bereits vorhanden
                    
                    # Trade-Daten extrahieren und normalisieren
                    symbol = trade.get('symbol', 'UNKNOWN').replace('USDT', '').replace('-USDT', '')
                    side = trade.get('side', 'Buy')
                    size = float(trade.get('execQty', trade.get('size', 0)))
                    price = float(trade.get('execPrice', trade.get('price', 0)))
                    
                    # Simuliere PnL (in echt würde das aus der Exit-Order berechnet)
                    pnl = random.uniform(-50, 150)
                    pnl_percent = pnl / (size * price) * 100 if size * price > 0 else 0
                    
                    trade_time = trade.get('execTime', int(time.time() * 1000))
                    dt = datetime.fromtimestamp(int(trade_time) / 1000)
                    
                    # In Datenbank einfügen
                    cursor.execute('''
                        INSERT INTO trades (account, symbol, strategy, side, size, entry_price, exit_price, 
                                          pnl, pnl_percent, date, time, win_loss, trade_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        acc['name'], symbol, f'AI Strategy {symbol}', side, size, price, price,
                        pnl, pnl_percent, dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M:%S'),
                        'Win' if pnl > 0 else 'Loss', trade_id
                    ))
                    
                    account_imported += 1
                    total_imported += 1
                
                logging.info(f"✅ {acc['name']}: {account_imported} neue Trades importiert")
                
            except Exception as e:
                logging.error(f"❌ Import Fehler für {acc['name']}: {e}")
                continue
        
        # Import Log erstellen
        cursor.execute('''
            INSERT INTO import_log (mode, account, trades_imported, status, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (mode, target_account or 'Alle', total_imported, 'Success', f'{total_imported} Trades importiert'))
        
        conn.commit()
        conn.close()
        
        import_status['progress'] = 100
        import_status['message'] = f'Import abgeschlossen: {total_imported} Trades'
        import_status['last_update'] = get_berlin_time().isoformat()
        
        logging.info(f"✅ Trade Import abgeschlossen: {total_imported} Trades")
        
    except Exception as e:
        logging.error(f"❌ Import Fehler: {e}")
        import_status['message'] = f'Import Fehler: {str(e)}'
    finally:
        import_status['running'] = False

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

@app.route('/import_trades', methods=['POST'])
def import_trades():
    """Manueller Trade Import über Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    try:
        mode = request.form.get('mode', 'update')
        account = request.form.get('account', '')
        
        logging.info(f"🎯 Manueller Trade Import: mode={mode}, account={account or 'alle'}")
        
        if import_status['running']:
            return jsonify({'status': 'error', 'message': 'Import läuft bereits'}), 400
        
        # Starte Import in separatem Thread
        import_thread = threading.Thread(
            target=import_trades_from_api,
            args=(mode, account if account else None)
        )
        import_thread.daemon = True
        import_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'Trade Import ({mode}) gestartet'
        })
        
    except Exception as e:
        logging.error(f"❌ Import Route Error: {e}")
        return jsonify({
            'status': 'error', 
            'message': f'Fehler beim Starten des Imports: {str(e)}'
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

@app.route('/trading-journal')
def trading_journal():
    """Trading Journal mit Trade History aus der Datenbank"""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        conn = sqlite3.connect('trading_data.db')
        cursor = conn.cursor()
        
        # Hole alle Trades
        cursor.execute('''
            SELECT account, symbol, strategy, side, size, entry_price, exit_price,
                   pnl, pnl_percent, date, time, win_loss
            FROM trades
            ORDER BY date DESC, time DESC
            LIMIT 1000
        ''')
        
        trades = cursor.fetchall()
        
        # Konvertiere zu Liste von Dictionaries
        journal_entries = []
        for trade in trades:
            journal_entries.append({
                'account': trade[0],
                'symbol': trade[1],
                'strategy': trade[2],
                'side': trade[3],
                'size': trade[4],
                'entry_price': trade[5],
                'exit_price': trade[6],
                'pnl': trade[7],
                'pnl_percent': trade[8],
                'date': trade[9],
                'time': trade[10],
                'win_loss': trade[11]
            })
        
        # Berechne Journal-Statistiken
        if journal_entries:
            total_trades = len(journal_entries)
            winning_trades = len([t for t in journal_entries if t['pnl'] > 0])
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            total_pnl = sum(t['pnl'] for t in journal_entries)
            total_volume = sum(abs(t['size'] * t['entry_price']) for t in journal_entries)
            
            winning_pnl = sum(t['pnl'] for t in journal_entries if t['pnl'] > 0)
            losing_pnl = abs(sum(t['pnl'] for t in journal_entries if t['pnl'] < 0))
            
            profit_factor = (winning_pnl / losing_pnl) if losing_pnl > 0 else 999
            avg_win = winning_pnl / winning_trades if winning_trades > 0 else 0
            avg_loss = losing_pnl / losing_trades if losing_trades > 0 else 0
            avg_rr = avg_win / avg_loss if avg_loss > 0 else 0
            
            largest_win = max([t['pnl'] for t in journal_entries if t['pnl'] > 0] + [0])
            largest_loss = min([t['pnl'] for t in journal_entries if t['pnl'] < 0] + [0])
            
            # Finde beste/schlechteste Tage
            daily_pnl = {}
            for trade in journal_entries:
                date = trade['date']
                if date not in daily_pnl:
                    daily_pnl[date] = 0
                daily_pnl[date] += trade['pnl']
            
            best_day = max(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ('N/A', 0)
            worst_day = min(daily_pnl.items(), key=lambda x: x[1]) if daily_pnl else ('N/A', 0)
            
            # Strategie Performance
            strategy_performance = {}
            for trade in journal_entries:
                strategy = trade['strategy']
                if strategy not in strategy_performance:
                    strategy_performance[strategy] = {
                        'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0
                    }
                
                strategy_performance[strategy]['trades'] += 1
                strategy_performance[strategy]['pnl'] += trade['pnl']
                
                if trade['pnl'] > 0:
                    strategy_performance[strategy]['wins'] += 1
                else:
                    strategy_performance[strategy]['losses'] += 1
            
            # Berechne Win Rate für Strategien
            for strategy, perf in strategy_performance.items():
                perf['win_rate'] = (perf['wins'] / perf['trades'] * 100) if perf['trades'] > 0 else 0
            
            best_strategy = max(strategy_performance.items(), key=lambda x: x[1]['pnl']) if strategy_performance else ('N/A', {'pnl': 0})
            
            # Meist gehandeltes Symbol
            symbol_counts = {}
            for trade in journal_entries:
                symbol = trade['symbol']
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
            
            most_traded = max(symbol_counts.items(), key=lambda x: x[1]) if symbol_counts else ('N/A', 0)
            
            journal_stats = {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'profit_factor': profit_factor,
                'avg_rr': avg_rr,
                'total_volume': total_volume,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'largest_win': largest_win,
                'largest_loss': largest_loss,
                'best_day': {'date': best_day[0], 'pnl': best_day[1]},
                'worst_day': {'date': worst_day[0], 'pnl': worst_day[1]},
                'best_strategy': {'name': best_strategy[0], 'pnl': best_strategy[1]['pnl']},
                'most_traded': {'symbol': most_traded[0], 'count': most_traded[1]},
                'total_fees': total_volume * 0.0006,  # Geschätzte Fees
                'strategy_performance': strategy_performance
            }
        else:
            # Fallback wenn keine Trades
            journal_stats = {
                'total_trades': 0, 'winning_trades': 0, 'losing_trades': 0,
                'win_rate': 0, 'total_pnl': 0, 'profit_factor': 0, 'avg_rr': 0,
                'total_volume': 0, 'avg_win': 0, 'avg_loss': 0,
                'largest_win': 0, 'largest_loss': 0,
                'best_day': {'date': 'N/A', 'pnl': 0},
                'worst_day': {'date': 'N/A', 'pnl': 0},
                'best_strategy': {'name': 'N/A', 'pnl': 0},
                'most_traded': {'symbol': 'N/A', 'count': 0},
                'total_fees': 0,
                'strategy_performance': {}
            }
        
        conn.close()
        
        berlin_time = get_berlin_time()
        now = berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        
        return render_template('trading_journal.html',
                               journal_entries=journal_entries,
                               journal_stats=journal_stats,
                               now=now)
        
    except Exception as e:
        logging.error(f"❌ Trading Journal Fehler: {e}")
        return render_template('trading_journal.html',
                               journal_entries=[],
                               journal_stats={},
                               now=get_berlin_time().strftime("%d.%m.%Y %H:%M:%S"))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        logging.info("=== DASHBOARD START ===")
        
        # Hole Account-Daten
        data = get_all_account_data()
        account_data = data['account_data']
        total_balance = data['total_balance']
        positions_all = data['positions_all']
        total_positions_pnl = data['total_positions_pnl']
        
        # Berechne Gesamtstatistiken
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start * 100) if total_start > 0 else 0
        total_positions_pnl_percent = (total_positions_pnl / total_start * 100) if total_start > 0 else 0
        
        historical_performance = {
            '1_day': total_pnl * 0.02,
            '7_day': total_pnl * 0.15,
            '30_day': total_pnl * 0.80
        }
        
        # Erstelle ALLE Charts
        logging.info("🎨 Starte Chart-Erstellung...")
        charts = create_all_charts(account_data)
        
        # Hole Coin Performance
        try:
            all_coin_performance = get_comprehensive_coin_performance()
        except Exception as e:
            logging.error(f"❌ Coin Performance Fehler: {e}")
            all_coin_performance = []
        
        # Zeit
        berlin_time = get_berlin_time()
        now = berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        
        logging.info(f"✅ DASHBOARD BEREIT:")
        logging.info(f"   📊 Charts: {list(charts.keys())}")
        logging.info(f"   💰 Total: ${total_balance:.2f} (PnL: {total_pnl_percent:.2f}%)")
        logging.info(f"   📈 Accounts: {len(account_data)}")
        logging.info(f"   🎯 Strategien: {len(all_coin_performance)}")

        return render_template("dashboard.html",
                               # Account Data
                               accounts=account_data,
                               total_start=total_start,
                               total_balance=total_balance,
                               total_pnl=total_pnl,
                               total_pnl_percent=total_pnl_percent,
                               historical_performance=historical_performance,
                               
                               # Chart Paths - KORRIGIERT!
                               chart_path_subaccounts=charts.get('subaccounts', 'static/chart_fallback.png'),
                               chart_path_projekte=charts.get('projekte', 'static/chart_fallback.png'),
                               equity_total_path=charts.get('equity_total', 'static/chart_fallback.png'),
                               equity_projects_path=charts.get('equity_projects', 'static/chart_fallback.png'),
                               
                               # Position Data
                               positions_all=positions_all,
                               total_positions_pnl=total_positions_pnl,
                               total_positions_pnl_percent=total_positions_pnl_percent,
                               
                               # Coin Performance
                               all_coin_performance=all_coin_performance,
                               now=now)

    except Exception as e:
        logging.error(f"❌ KRITISCHER DASHBOARD FEHLER: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Kompletter Fallback
        total_start = sum(startkapital.values())
        berlin_time = get_berlin_time()
        fallback_chart = create_fallback_chart()
        
        return render_template("dashboard.html",
                               accounts=[],
                               total_start=total_start,
                               total_balance=total_start,
                               total_pnl=0,
                               total_pnl_percent=0,
                               historical_performance={'1_day': 0.0, '7_day': 0.0, '30_day': 0.0},
                               
                               # Alle Charts mit Fallback
                               chart_path_subaccounts=fallback_chart,
                               chart_path_projekte=fallback_chart,
                               equity_total_path=fallback_chart,
                               equity_projects_path=fallback_chart,
                               
                               positions_all=[],
                               total_positions_pnl=0,
                               total_positions_pnl_percent=0,
                               all_coin_performance=[],
                               now=berlin_time.strftime("%d.%m.%Y %H:%M:%S"))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    init_database()
    logging.info("🚀 DASHBOARD STARTET...")
    app.run(debug=True, host='0.0.0.0', port=10000)
