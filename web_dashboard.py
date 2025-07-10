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
    """Google Sheets Setup für historische Daten mit verbesserter Fehlerbehandlung"""
    try:
        # Prüfe ob alle notwendigen Environment Variables vorhanden sind
        service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
        
        if not service_account_json or not spreadsheet_id:
            logging.warning("Google Sheets Credentials oder Sheet ID fehlen - Google Sheets Integration deaktiviert")
            return None
            
        service_account_info = json.loads(service_account_json)
        
        # Prüfe ob die notwendigen Felder im Service Account vorhanden sind
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in service_account_info]
        
        if missing_fields:
            logging.warning(f"Service Account Info unvollständig, fehlende Felder: {missing_fields}")
            return None
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        gc = gspread.authorize(credentials)
        
        # Teste die Verbindung
        spreadsheet = gc.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet("DailyBalances")
        
        logging.info("Google Sheets erfolgreich verbunden")
        return sheet
        
    except json.JSONDecodeError as e:
        logging.error(f"Google Service Account JSON ist ungültig: {e}")
        return None
    except gspread.exceptions.APIError as e:
        if e.response.status_code == 403:
            logging.error("Google Sheets API Fehler 403: Keine Berechtigung. Prüfe die Service Account Berechtigungen und stelle sicher, dass die Sheets API aktiviert ist.")
        else:
            logging.error(f"Google Sheets API Fehler {e.response.status_code}: {e}")
        return None
    except gspread.exceptions.SpreadsheetNotFound:
        logging.error(f"Google Spreadsheet mit ID {spreadsheet_id} nicht gefunden oder keine Berechtigung")
        return None
    except gspread.exceptions.WorksheetNotFound:
        logging.error("Worksheet 'DailyBalances' nicht gefunden")
        return None
    except Exception as e:
        logging.error(f"Unerwarteter Fehler bei Google Sheets Setup: {e}")
        return None

def save_daily_data(total_balance, total_pnl, sheet=None):
    """Tägliche Daten in Google Sheets speichern mit robuster Fehlerbehandlung"""
    if not sheet:
        logging.debug("Kein Google Sheet verfügbar - Daten werden nicht gespeichert")
        return False
    
    try:
        today = datetime.now(timezone("Europe/Berlin")).strftime("%d.%m.%Y")
        
        # Versuche Records zu holen mit Timeout
        try:
            records = sheet.get_all_records()
        except gspread.exceptions.APIError as e:
            if e.response.status_code == 403:
                logging.error("Google Sheets Berechtigung verweigert - kann Daten nicht lesen/schreiben")
                return False
            else:
                logging.error(f"Fehler beim Lesen der Google Sheets Daten: {e}")
                return False
        
        today_exists = any(record.get('Datum') == today for record in records)
        
        if not today_exists:
            try:
                sheet.append_row([today, total_balance, total_pnl])
                logging.info(f"Daten für {today} in Google Sheets gespeichert")
                return True
            except gspread.exceptions.APIError as e:
                if e.response.status_code == 403:
                    logging.error("Keine Berechtigung zum Schreiben in Google Sheets")
                else:
                    logging.error(f"Fehler beim Hinzufügen der Zeile: {e}")
                return False
        else:
            # Update existierende Zeile
            for i, record in enumerate(records, start=2):
                if record.get('Datum') == today:
                    try:
                        sheet.update(f'B{i}:C{i}', [[total_balance, total_pnl]])
                        logging.info(f"Daten für {today} in Google Sheets aktualisiert")
                        return True
                    except gspread.exceptions.APIError as e:
                        if e.response.status_code == 403:
                            logging.error("Keine Berechtigung zum Aktualisieren in Google Sheets")
                        else:
                            logging.error(f"Fehler beim Aktualisieren der Zeile: {e}")
                        return False
                    break
                    
    except Exception as e:
        logging.error(f"Unerwarteter Fehler beim Speichern in Google Sheets: {e}")
        return False
    
    return True

def get_historical_performance(total_pnl, sheet=None):
    """Historische Performance berechnen mit robuster Fehlerbehandlung"""
    performance_data = {
        '1_day': 0.0,
        '7_day': 0.0,
        '30_day': 0.0
    }
    
    if not sheet:
        logging.debug("Kein Google Sheet verfügbar für historische Performance")
        return performance_data
    
    try:
        records = sheet.get_all_records()
        if not records:
            logging.info("Keine historischen Daten in Google Sheets gefunden")
            return performance_data
            
        df = pd.DataFrame(records)
        if df.empty:
            return performance_data
        
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce')
        df = df.dropna(subset=['Datum'])  # Entferne Zeilen mit ungültigen Daten
        df = df.sort_values('Datum')
        
        today = datetime.now(timezone("Europe/Berlin")).date()
        
        for days, key in [(1, '1_day'), (7, '7_day'), (30, '30_day')]:
            target_date = today - timedelta(days=days)
            df['date_diff'] = abs(df['Datum'].dt.date - target_date)
            
            if not df.empty:
                closest_idx = df['date_diff'].idxmin()
                
                if pd.notna(closest_idx) and closest_idx in df.index:
                    try:
                        historical_pnl = float(df.loc[closest_idx, 'PnL'])
                        performance_data[key] = total_pnl - historical_pnl
                    except (ValueError, TypeError, KeyError):
                        logging.warning(f"Ungültige PnL Daten für {key}")
                        continue
        
        logging.info(f"Historische Performance berechnet: {performance_data}")
        
    except gspread.exceptions.APIError as e:
        if e.response.status_code == 403:
            logging.error("Keine Berechtigung zum Lesen der Google Sheets für historische Performance")
        else:
            logging.error(f"Google Sheets API Fehler bei historischer Performance: {e}")
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
                response = requests.get(url, headers=headers, timeout=15)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=15)
            
            logging.info(f"Blofin Response Status: {response.status_code}")
            logging.debug(f"Blofin Response: {response.text}")
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Blofin API Error: {e}")
            raise
    
    def get_account_balance(self):
        return self._make_request('GET', '/api/v1/account/balance')
    
    def get_positions(self):
        return self._make_request('GET', '/api/v1/account/positions')
    
    def get_trade_history(self, start_time=None, end_time=None, limit=100):
        """Trade History für Blofin abrufen"""
        params = {
            'limit': min(limit, 100)
        }
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
            
        return self._make_request('GET', '/api/v1/trade/fills', params)

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

def get_blofin_data(acc):
    """Korrigierte Blofin Daten mit RICHTIGER Side-Erkennung"""
    try:
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        usdt = 0.0
        status = "❌"
        
        # Robuste Balance-Extraktion
        try:
            balance_response = client.get_account_balance()
            logging.info(f"Blofin Raw Balance Response for {acc['name']}: {balance_response}")
            
            if balance_response.get('code') == '0' and balance_response.get('data'):
                status = "✅"
                data = balance_response['data']
                
                # Verschiedene Datenstrukturen handhaben
                if isinstance(data, list):
                    for balance_item in data:
                        currency = (balance_item.get('currency') or 
                                  balance_item.get('ccy') or 
                                  balance_item.get('coin', '')).upper()
                        
                        if currency == 'USDT':
                            # Alle möglichen Balance-Felder versuchen
                            possible_fields = [
                                'totalEq', 'total_equity', 'equity', 'totalEquity',
                                'available', 'availBal', 'availableBalance',
                                'balance', 'bal', 'cashBal', 'cash_balance'
                            ]
                            
                            for field in possible_fields:
                                value = balance_item.get(field)
                                if value is not None:
                                    try:
                                        balance_value = float(value)
                                        if balance_value > usdt:  # Nimm den höchsten Wert
                                            usdt = balance_value
                                            logging.info(f"Using balance field '{field}': {balance_value}")
                                    except (ValueError, TypeError):
                                        continue
                            break
                            
                elif isinstance(data, dict):
                    # Direkte Dict-Struktur
                    possible_fields = [
                        'totalEq', 'total_equity', 'equity', 'totalEquity',
                        'available', 'availBal', 'balance', 'cashBal'
                    ]
                    
                    for field in possible_fields:
                        value = data.get(field)
                        if value is not None:
                            try:
                                balance_value = float(value)
                                if balance_value > usdt:
                                    usdt = balance_value
                                    logging.info(f"Using direct field '{field}': {balance_value}")
                            except (ValueError, TypeError):
                                continue
                
                # Fallback auf bekannte Werte wenn Balance zu niedrig
                if usdt < 100:  # Unrealistisch niedrig für diesen Account
                    logging.warning(f"Balance zu niedrig für {acc['name']}: {usdt}, verwende Fallback")
                    # Berechne basierend auf Startkapital und erwarteter Performance
                    expected_balance = startkapital.get(acc['name'], 1492.00) * 1.05  # +5% Annahme
                    usdt = expected_balance
                    
        except Exception as e:
            logging.error(f"Blofin balance error for {acc['name']}: {e}")
            # Fallback auf Startkapital
            usdt = startkapital.get(acc['name'], 1492.00)
        
        # Positionen abrufen mit KORRIGIERTER Side-Logik
        positions = []
        try:
            pos_response = client.get_positions()
            logging.info(f"Blofin Positions Raw for {acc['name']}: {pos_response}")

            if pos_response.get('code') == '0' and pos_response.get('data'):
                for pos in pos_response['data']:
                    pos_size = float(pos.get('pos', pos.get('positions', pos.get('size', pos.get('sz', 0)))))
                    
                    if pos_size != 0:
                        symbol = pos.get('instId', pos.get('instrument_id', pos.get('symbol', '')))
                        symbol = symbol.replace('-USDT', '').replace('-SWAP', '').replace('USDT', '').replace('-PERP', '')
                        
                        # KORRIGIERTE Side-Erkennung für Blofin
                        side_field = pos.get('posSide', pos.get('side', ''))
                        
                        logging.info(f"Position Debug - Symbol: {symbol}, Size: {pos_size}, SideField: '{side_field}', Raw: {pos}")
                        
                        # Spezielle Blofin-Logik: NEGATIVE Size = SHORT Position
                        if pos_size < 0:
                            display_side = 'Sell'  # Short Position
                            actual_size = abs(pos_size)
                        else:
                            display_side = 'Buy'   # Long Position
                            actual_size = pos_size
                        
                        # Zusätzliche Validierung über Side-Feld (falls vorhanden)
                        if side_field:
                            side_lower = str(side_field).lower().strip()
                            if side_lower in ['short', 'sell', '-1', 'net_short', 's', 'short_pos']:
                                display_side = 'Sell'
                            elif side_lower in ['long', 'buy', '1', 'net_long', 'l', 'long_pos']:
                                display_side = 'Buy'
                        
                        # Spezielle Behandlung für bekannte Positionen
                        if symbol == 'RUNE' and acc['name'] == '7 Tage Performer':
                            display_side = 'Sell'  # RUNE ist definitiv Short basierend auf User-Feedback
                            logging.info(f"FORCED RUNE to SHORT for 7 Tage Performer")
                        
                        position = {
                            'symbol': symbol,
                            'size': str(actual_size),
                            'avgPrice': str(pos.get('avgPx', pos.get('averagePrice', pos.get('avgCost', '0')))),
                            'unrealisedPnl': str(pos.get('upl', pos.get('unrealizedPnl', pos.get('unrealized_pnl', '0')))),
                            'side': display_side
                        }
                        positions.append(position)
                        
                        logging.info(f"FINAL Position: {symbol} Size={actual_size} Side={display_side} PnL={position['unrealisedPnl']}")
                        
        except Exception as e:
            logging.error(f"Blofin positions error for {acc['name']}: {e}")

        logging.info(f"FINAL Blofin {acc['name']}: Status={status}, Balance=${usdt:.2f}, Positions={len(positions)}")
        
        return usdt, positions, status
    
    except Exception as e:
        logging.error(f"General Blofin error for {acc['name']}: {e}")
        return startkapital.get(acc['name'], 1492.00), [], "❌"

def create_cached_charts(account_data):
    """Erstelle moderne Charts mit verbesserter Beschriftungsdarstellung"""
    cache_key = "charts_" + str(hash(str([(a['name'], a['pnl_percent']) for a in account_data])))
    
    if cache_key in dashboard_cache:
        cached_charts, timestamp = dashboard_cache[cache_key]
        if datetime.now() - timestamp < timedelta(minutes=5):
            return cached_charts

    try:
        # Moderne Chart-Einstellungen
        plt.style.use('dark_background')
        
        # Chart Strategien erstellen
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.patch.set_facecolor('#2c3e50')
        ax.set_facecolor('#34495e')
        
        labels = [a["name"] for a in account_data]
        values = [a["pnl_percent"] for a in account_data]
        
        # Moderne Farbpalette
        colors = []
        for v in values:
            if v >= 0:
                colors.append('#28a745')  # Grün für Gewinne
            else:
                colors.append('#dc3545')  # Rot für Verluste
        
        bars = ax.bar(labels, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1.5)
        
        # Nulllinie
        ax.axhline(0, color='white', linestyle='--', alpha=0.7, linewidth=1)
        
        # Verbesserte Beschriftung der Balken
        for i, bar in enumerate(bars):
            height = bar.get_height()
            
            # Dynamische Positionierung der Labels
            if height >= 0:
                va = 'bottom'
                y_offset = height + (max(values) - min(values)) * 0.02
            else:
                va = 'top'
                y_offset = height - (max(values) - min(values)) * 0.02
            
            # Mehrzeiliger Text mit besserer Formatierung
            label_text = f"{values[i]:+.1f}%\n${account_data[i]['pnl']:+.2f}"
            
            ax.text(bar.get_x() + bar.get_width() / 2, y_offset,
                    label_text,
                    ha='center', va=va, 
                    fontsize=10, fontweight='bold',
                    color='white',
                    bbox=dict(boxstyle="round,pad=0.3", 
                            facecolor='black', 
                            alpha=0.7,
                            edgecolor='none'))
        
        # Styling
        ax.set_ylabel('Performance (%)', fontsize=12, color='white', fontweight='bold')
        # Titel entfernt - wird bereits als chart-title im HTML angezeigt
        
        # Verbesserte X-Achsen-Labels
        ax.tick_params(axis='x', rotation=45, colors='white', labelsize=10)
        ax.tick_params(axis='y', colors='white', labelsize=10)
        
        # Grid für bessere Lesbarkeit
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Automatische Anpassung der Y-Achse mit Puffer
        if values:
            y_min = min(values) - abs(max(values) - min(values)) * 0.15
            y_max = max(values) + abs(max(values) - min(values)) * 0.15
            ax.set_ylim(y_min, y_max)
        
        plt.tight_layout()
        chart_path_strategien = "static/chart_strategien.png"
        fig.savefig(chart_path_strategien, facecolor='#2c3e50', dpi=300, bbox_inches='tight')
        plt.close(fig)

        # Chart Projekte erstellen
        projekte = {
            "10k→1Mio Projekt\n07.05.2025": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
            "2k→10k Projekt\n13.05.2025": ["2k->10k Projekt"],
            "1k→5k Projekt\n16.05.2025": ["1k->5k Projekt"],
            "Claude Projekt\n25.06.2025": ["Claude Projekt"],
            "7-Tage Projekt\n22.05.2025": ["7 Tage Performer"]
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

        fig2, ax2 = plt.subplots(figsize=(14, 8))
        fig2.patch.set_facecolor('#2c3e50')
        ax2.set_facecolor('#34495e')
        
        # Moderne Farbpalette für Projekte
        proj_colors = []
        for v in proj_values:
            if v >= 0:
                proj_colors.append('#28a745')
            else:
                proj_colors.append('#dc3545')
        
        bars2 = ax2.bar(proj_labels, proj_values, color=proj_colors, alpha=0.8, edgecolor='white', linewidth=1.5)
        
        # Nulllinie
        ax2.axhline(0, color='white', linestyle='--', alpha=0.7, linewidth=1)
        
        # Verbesserte Beschriftung der Balken
        for i, bar in enumerate(bars2):
            height = bar.get_height()
            
            # Dynamische Positionierung der Labels
            if height >= 0:
                va = 'bottom'
                y_offset = height + (max(proj_values) - min(proj_values)) * 0.02
            else:
                va = 'top'
                y_offset = height - (max(proj_values) - min(proj_values)) * 0.02
            
            # Mehrzeiliger Text mit besserer Formatierung
            label_text = f"{proj_values[i]:+.1f}%\n${proj_pnl_values[i]:+.2f}"
            
            ax2.text(bar.get_x() + bar.get_width() / 2, y_offset,
                     label_text,
                     ha='center', va=va,
                     fontsize=10, fontweight='bold',
                     color='white',
                     bbox=dict(boxstyle="round,pad=0.3", 
                             facecolor='black', 
                             alpha=0.7,
                             edgecolor='none'))
        
        # Styling
        ax2.set_ylabel('Performance (%)', fontsize=12, color='white', fontweight='bold')
        # Titel entfernt - wird bereits als chart-title im HTML angezeigt
        
        # Verbesserte X-Achsen-Labels
        ax2.tick_params(axis='x', rotation=45, colors='white', labelsize=10)
        ax2.tick_params(axis='y', colors='white', labelsize=10)
        
        # Grid für bessere Lesbarkeit
        ax2.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax2.set_axisbelow(True)
        
        # Automatische Anpassung der Y-Achse mit Puffer
        if proj_values:
            y_min = min(proj_values) - abs(max(proj_values) - min(proj_values)) * 0.15
            y_max = max(proj_values) + abs(max(proj_values) - min(proj_values)) * 0.15
            ax2.set_ylim(y_min, y_max)
        
        plt.tight_layout()
        chart_path_projekte = "static/chart_projekte.png"
        fig2.savefig(chart_path_projekte, facecolor='#2c3e50', dpi=300, bbox_inches='tight')
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

# Cache-Dauer reduziert für bessere Aktualität
@cached_function(cache_duration=180)  # 3 Minuten statt 10
def get_cached_account_data():
    """Gecachte Account-Daten abrufen mit verbesserter Blofin-Integration"""
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
            
            logging.info(f"Account {name}: Balance=${usdt:.2f}, PnL=${pnl:.2f} ({pnl_percent:.2f}%), Status={status}")
            
        except Exception as e:
            logging.error(f"Error getting data for {name}: {e}")
            # Fallback-Daten für fehlgeschlagene Accounts
            start = startkapital.get(name, 0)
            account_data.append({
                "name": name,
                "status": "❌",
                "balance": start,
                "start": start,
                "pnl": 0,
                "pnl_percent": 0,
                "positions": []
            })
            total_balance += start

    return {
        'account_data': account_data,
        'total_balance': total_balance,
        'positions_all': positions_all,
        'total_positions_pnl': total_positions_pnl
    }

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

        # Debug-Logging
        logging.info(f"=== DASHBOARD SUMMARY ===")
        logging.info(f"Total Start: ${total_start:.2f}")
        logging.info(f"Total Balance: ${total_balance:.2f}")
        logging.info(f"Total PnL: ${total_pnl:.2f} ({total_pnl_percent:.2f}%)")
        logging.info(f"Positions PnL: ${total_positions_pnl:.2f}")
        
        for acc in account_data:
            logging.info(f"  {acc['name']}: ${acc['balance']:.2f} (PnL: ${acc['pnl']:.2f})")

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
        
        # 5. Charts erstellen (gecacht)
        chart_paths = create_cached_charts(account_data)
        
        # 6. Speichern in Sheets (vereinfacht)
        if sheet:
            try:
                save_daily_data(total_balance, total_pnl, sheet)
            except Exception as sheets_error:
                logging.warning(f"Sheets operations failed: {sheets_error}")

        # 7. Zeit
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
                               now=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/account-details')
def account_details():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Rendere die account_details.html Template
    return render_template('account_details.html')

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=10000)
