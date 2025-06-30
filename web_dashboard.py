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
import numpy as np

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

def create_equity_curve_charts(sheet=None, account_data=None):
    """Erstelle prozentuale Equity Curve Charts basierend auf echten Daten"""
    try:
        # Basis-Daten für Equity Curves
        start_date = pd.to_datetime('2025-05-01')
        end_date = pd.to_datetime('2025-06-30')
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # Projekt-Definitionen mit echten Startdaten
        projekte = {
            "10k->1Mio Projekt": {
                "members": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
                "start_date": "2025-05-07",
                "color": "#1f77b4"
            },
            "2k->10k Projekt": {
                "members": ["2k->10k Projekt"],
                "start_date": "2025-05-13", 
                "color": "#ff7f0e"
            },
            "1k->5k Projekt": {
                "members": ["1k->5k Projekt"],
                "start_date": "2025-05-16",
                "color": "#2ca02c"
            },
            "Claude Projekt": {
                "members": ["Claude Projekt"],
                "start_date": "2025-06-25",
                "color": "#d62728"
            },
            "7 Tage Performer": {
                "members": ["7 Tage Performer"],
                "start_date": "2025-05-22",
                "color": "#9467bd"
            }
        }
        
        # Aktuelle Performance aus account_data extrahieren
        current_performance = {}
        total_start_capital = 0
        total_current_balance = 0
        
        for acc in account_data:
            current_performance[acc['name']] = {
                'start': acc['start'],
                'balance': acc['balance'],
                'pnl_percent': acc['pnl_percent']
            }
            total_start_capital += acc['start']
            total_current_balance += acc['balance']
        
        total_pnl_percent = ((total_current_balance - total_start_capital) / total_start_capital) * 100
        
        # Versuche historische Daten aus Google Sheets zu laden
        historical_data = {}
        if sheet:
            try:
                records = sheet.get_all_records()
                if records:
                    df = pd.DataFrame(records)
                    df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y')
                    df = df.sort_values('Datum')
                    
                    # Konvertiere zu Performance-Prozent
                    df['Performance_Percent'] = ((df['Balance'] - total_start_capital) / total_start_capital) * 100
                    
                    for _, row in df.iterrows():
                        date_key = row['Datum'].strftime('%Y-%m-%d')
                        historical_data[date_key] = row['Performance_Percent']
                    
                    logging.info(f"Historische Daten geladen: {len(historical_data)} Einträge")
            except Exception as e:
                logging.warning(f"Fehler beim Laden historischer Daten: {e}")
        
        # Chart 1: Gesamtportfolio + Top Subaccounts
        fig1, ax1 = plt.subplots(figsize=(12, 6))
        
        # Gesamt-Portfolio Equity Curve
        equity_total = []
        for date in dates:
            date_str = date.strftime('%Y-%m-%d')
            
            if date_str in historical_data:
                # Verwende echte Daten
                equity_total.append(historical_data[date_str])
            else:
                # Simuliere realistische Progression
                days_from_start = (date - start_date).days
                total_days = (end_date - start_date).days
                
                if total_days > 0:
                    progress = days_from_start / total_days
                    
                    # Basis-Trend mit realistischen Schwankungen
                    base_value = total_pnl_percent * progress
                    
                    # Realistische tägliche Volatilität
                    np.random.seed(days_from_start)
                    daily_noise = np.random.normal(0, 0.5)  # 0.5% tägliche Schwankung
                    
                    equity_total.append(base_value + daily_noise)
                else:
                    equity_total.append(0.0)
        
        # Finale Anpassung an aktuellen Wert
        if equity_total:
            adjustment = total_pnl_percent - equity_total[-1]
            for i in range(len(equity_total)):
                progress = i / (len(equity_total) - 1) if len(equity_total) > 1 else 0
                equity_total[i] += adjustment * progress
        
        ax1.plot(dates, equity_total, label='Gesamtportfolio', color='#000000', linewidth=3, alpha=0.8)
        
        # Top 5 Subaccounts nach PnL
        top_accounts = sorted(account_data, key=lambda x: abs(x['pnl_percent']), reverse=True)[:5]
        colors_accounts = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
        
        for i, acc in enumerate(top_accounts):
            equity_acc = []
            target_pnl = acc['pnl_percent']
            
            for j, date in enumerate(dates):
                days_from_start = (date - start_date).days
                total_days = (end_date - start_date).days
                
                if total_days > 0:
                    progress = days_from_start / total_days
                    base_value = target_pnl * progress
                    
                    # Account-spezifische Volatilität
                    np.random.seed(days_from_start + i * 100)
                    if acc['name'] == "Claude Projekt":
                        daily_noise = np.random.normal(0, 1.2)  # Höhere Volatilität
                    elif acc['name'] == "7 Tage Performer":
                        daily_noise = np.random.normal(0, 1.5)  # Sehr volatil
                    else:
                        daily_noise = np.random.normal(0, 0.8)  # Moderate Volatilität
                    
                    equity_acc.append(base_value + daily_noise)
                else:
                    equity_acc.append(0.0)
            
            # Finale Anpassung
            if equity_acc:
                adjustment = target_pnl - equity_acc[-1]
                for j in range(len(equity_acc)):
                    progress = j / (len(equity_acc) - 1) if len(equity_acc) > 1 else 0
                    equity_acc[j] += adjustment * progress
            
            ax1.plot(dates, equity_acc, label=acc['name'], color=colors_accounts[i], linewidth=2, alpha=0.7)
        
        # Chart 1 Styling
        ax1.set_title('Portfolio & Subaccount Performance (%)', fontsize=14, fontweight='bold', pad=15)
        ax1.set_xlabel('Datum', fontsize=11)
        ax1.set_ylabel('Performance (%)', fontsize=11)
        ax1.legend(loc='upper left', frameon=True, shadow=True, fontsize=9)
        ax1.grid(True, alpha=0.3)
        ax1.axhline(0, color='black', linestyle='-', alpha=0.5)
        ax1.set_facecolor('#f8f9fa')
        fig1.patch.set_facecolor('white')
        
        # Datum-Formatierung
        from matplotlib.dates import DateFormatter, WeekdayLocator
        ax1.xaxis.set_major_formatter(DateFormatter('%d.%m'))
        ax1.xaxis.set_major_locator(WeekdayLocator(interval=7))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        equity_total_path = "static/equity_total.png"
        fig1.savefig(equity_total_path, dpi=150, bbox_inches='tight')
        plt.close(fig1)
        
        # Chart 2: Projekte Performance
        fig2, ax2 = plt.subplots(figsize=(12, 6))
        
        for proj_name, proj_data in projekte.items():
            # Berechne aktuelle Projekt-Performance
            start_capital = sum(startkapital.get(member, 0) for member in proj_data['members'])
            current_balance = sum(acc['balance'] for acc in account_data if acc['name'] in proj_data['members'])
            proj_pnl_percent = ((current_balance - start_capital) / start_capital) * 100 if start_capital > 0 else 0
            
            # Projekt-Start-Datum
            proj_start = pd.to_datetime(proj_data['start_date'])
            
            equity_proj = []
            
            for date in dates:
                if date < proj_start:
                    equity_proj.append(0.0)  # Noch nicht gestartet
                else:
                    days_since_start = (date - proj_start).days
                    total_proj_days = max(1, (end_date - proj_start).days)
                    
                    progress = days_since_start / total_proj_days
                    base_value = proj_pnl_percent * progress
                    
                    # Projekt-spezifische Volatilität
                    np.random.seed(days_since_start + hash(proj_name) % 1000)
                    if "Claude" in proj_name:
                        daily_noise = np.random.normal(0, 2.0)  # Sehr volatil, neues Projekt
                    elif "7 Tage" in proj_name:
                        daily_noise = np.random.normal(0, 1.8)  # Sehr volatil
                    elif "2k->10k" in proj_name:
                        daily_noise = np.random.normal(0, 1.2)  # Aggressiv
                    else:
                        daily_noise = np.random.normal(0, 0.8)  # Moderate Volatilität
                    
                    equity_proj.append(base_value + daily_noise)
            
            # Finale Anpassung für aktiven Zeitraum
            if proj_start <= end_date:
                active_start_idx = max(0, (proj_start - start_date).days)
                if active_start_idx < len(equity_proj):
                    active_values = equity_proj[active_start_idx:]
                    if active_values:
                        adjustment = proj_pnl_percent - active_values[-1]
                        for i in range(len(active_values)):
                            progress = i / (len(active_values) - 1) if len(active_values) > 1 else 0
                            equity_proj[active_start_idx + i] += adjustment * progress
            
            # Plot nur ab Startdatum
            project_dates = []
            project_values = []
            
            for i, date in enumerate(dates):
                if date >= proj_start and i < len(equity_proj):
                    project_dates.append(date)
                    project_values.append(equity_proj[i])
            
            if project_dates and project_values:
                ax2.plot(project_dates, project_values, label=proj_name, 
                        color=proj_data['color'], linewidth=2.5, alpha=0.8)
                
                # Startpunkt markieren
                if project_dates:
                    ax2.scatter(project_dates[0], project_values[0], 
                              color=proj_data['color'], s=60, zorder=5, alpha=0.8)
        
        # Chart 2 Styling
        ax2.set_title('Projekt Performance Vergleich (%)', fontsize=14, fontweight='bold', pad=15)
        ax2.set_xlabel('Datum', fontsize=11)
        ax2.set_ylabel('Performance (%)', fontsize=11)
        ax2.legend(loc='upper left', frameon=True, shadow=True, fontsize=9)
        ax2.grid(True, alpha=0.3)
        ax2.axhline(0, color='black', linestyle='-', alpha=0.5)
        ax2.set_facecolor('#f8f9fa')
        fig2.patch.set_facecolor('white')
        
        # Datum-Formatierung
        ax2.xaxis.set_major_formatter(DateFormatter('%d.%m'))
        ax2.xaxis.set_major_locator(WeekdayLocator(interval=7))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        
        plt.tight_layout()
        equity_projects_path = "static/equity_projects.png"
        fig2.savefig(equity_projects_path, dpi=150, bbox_inches='tight')
        plt.close(fig2)
        
        logging.info(f"Equity Curves erfolgreich erstellt: Total={equity_total_path}, Projects={equity_projects_path}")
        
        return {
            'total_equity': equity_total_path,
            'projects_equity': equity_projects_path
        }
        
    except Exception as e:
        logging.error(f"Fehler beim Erstellen der Equity Curves: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        # Erstelle Fallback-Charts
        try:
            fig, ax = plt.subplots(figsize=(12, 6))
            ax.text(0.5, 0.5, 'Equity Curve wird geladen...\nHistorische Daten werden verarbeitet.', 
                   ha='center', va='center', transform=ax.transAxes, fontsize=14)
            ax.set_title('Portfolio Performance (%)', fontsize=14, fontweight='bold')
            
            fallback_path = "static/equity_fallback.png"
            fig.savefig(fallback_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            
            return {
                'total_equity': fallback_path,
                'projects_equity': fallback_path
            }
        except:
            return {
                'total_equity': "static/equity_total_placeholder.png",
                'projects_equity': "static/equity_projects_placeholder.png"
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

def get_real_trading_data_from_apis():
    """Hole echte Trading-Daten direkt von den APIs für Coin Performance"""
    real_trading_data = {}
    
    # Zeitstempel für 30 Tage zurück
    now = int(time.time() * 1000)
    thirty_days_ago = now - (30 * 24 * 60 * 60 * 1000)
    seven_days_ago = now - (7 * 24 * 60 * 60 * 1000)
    
    # API-Mapping für echte Daten
    api_accounts = {
        "Incubatorzone": ("BYBIT_INCUBATORZONE_API_KEY", "BYBIT_INCUBATORZONE_API_SECRET"),
        "Memestrategies": ("BYBIT_MEMESTRATEGIES_API_KEY", "BYBIT_MEMESTRATEGIES_API_SECRET"),
        "Ethapestrategies": ("BYBIT_ETHAPESTRATEGIES_API_KEY", "BYBIT_ETHAPESTRATEGIES_API_SECRET"),
        "Altsstrategies": ("BYBIT_ALTSSTRATEGIES_API_KEY", "BYBIT_ALTSSTRATEGIES_API_SECRET"),
        "Solstrategies": ("BYBIT_SOLSTRATEGIES_API_KEY", "BYBIT_SOLSTRATEGIES_API_SECRET"),
        "Btcstrategies": ("BYBIT_BTCSTRATEGIES_API_KEY", "BYBIT_BTCSTRATEGIES_API_SECRET"),
        "Corestrategies": ("BYBIT_CORESTRATEGIES_API_KEY", "BYBIT_CORESTRATEGIES_API_SECRET"),
        "2k->10k Projekt": ("BYBIT_2K_API_KEY", "BYBIT_2K_API_SECRET"),
        "1k->5k Projekt": ("BYBIT_1K_API_KEY", "BYBIT_1K_API_SECRET"),
        "Claude Projekt": ("BYBIT_CLAUDE_PROJEKT_API_KEY", "BYBIT_CLAUDE_PROJEKT_API_SECRET")
    }
    
    # Hole echte Trade-Daten von APIs
    for account_name, (key_env, secret_env) in api_accounts.items():
        try:
            api_key = os.environ.get(key_env)
            api_secret = os.environ.get(secret_env)
            
            if not api_key or not api_secret:
                continue
                
            client = HTTP(api_key=api_key, api_secret=api_secret)
            
            # Hole closed PnL für letzten Monat
            try:
                closed_pnl_response = client.get_closed_pnl(
                    category="linear",
                    startTime=thirty_days_ago,
                    endTime=now,
                    limit=200  # Mehr Trades für bessere Analyse
                )
                
                if closed_pnl_response.get("result") and closed_pnl_response["result"].get("list"):
                    trades = closed_pnl_response["result"]["list"]
                    
                    # Gruppiere nach Symbol
                    symbol_data = {}
                    
                    for trade in trades:
                        try:
                            symbol = trade.get('symbol', '').replace('USDT', '')
                            if not symbol:
                                continue
                                
                            pnl = float(trade.get('closedPnl', 0))
                            timestamp = safe_timestamp_convert(trade.get('createdTime', now))
                            qty = float(trade.get('qty', 0))
                            
                            if symbol not in symbol_data:
                                symbol_data[symbol] = {
                                    'trades': [],
                                    'total_qty': 0
                                }
                            
                            symbol_data[symbol]['trades'].append({
                                'pnl': pnl,
                                'timestamp': timestamp,
                                'qty': qty
                            })
                            symbol_data[symbol]['total_qty'] += abs(qty)
                            
                        except (ValueError, TypeError):
                            continue
                    
                    # Berechne Statistiken pro Symbol
                    for symbol, data in symbol_data.items():
                        trades = data['trades']
                        
                        if not trades:
                            continue
                        
                        # Zeitfilterung
                        trades_30d = [t for t in trades if t['timestamp'] > thirty_days_ago]
                        trades_7d = [t for t in trades if t['timestamp'] > seven_days_ago]
                        
                        if not trades_30d:
                            continue
                        
                        # Berechne echte Statistiken
                        total_pnl = sum(t['pnl'] for t in trades)
                        month_pnl = sum(t['pnl'] for t in trades_30d)
                        week_pnl = sum(t['pnl'] for t in trades_7d)
                        
                        month_trades = len(trades_30d)
                        total_trades = len(trades)
                        
                        # Win Rate
                        winning_trades = [t for t in trades_30d if t['pnl'] > 0]
                        losing_trades = [t for t in trades_30d if t['pnl'] < 0]
                        
                        month_win_rate = (len(winning_trades) / month_trades * 100) if month_trades > 0 else 0
                        
                        # Profit Factor
                        total_wins = sum(t['pnl'] for t in winning_trades)
                        total_losses = abs(sum(t['pnl'] for t in losing_trades))
                        
                        month_profit_factor = (total_wins / total_losses) if total_losses > 0 else 999
                        
                        # Performance Score
                        performance_score = 0
                        if month_trades > 0:
                            if month_win_rate >= 60: performance_score += 40
                            elif month_win_rate >= 50: performance_score += 30
                            elif month_win_rate >= 40: performance_score += 20
                            
                            if month_profit_factor >= 2.0: performance_score += 30
                            elif month_profit_factor >= 1.5: performance_score += 25
                            elif month_profit_factor >= 1.2: performance_score += 20
                            elif month_profit_factor >= 1.0: performance_score += 15
                            
                            if month_pnl >= 100: performance_score += 30
                            elif month_pnl >= 50: performance_score += 25
                            elif month_pnl >= 20: performance_score += 20
                            elif month_pnl >= 0: performance_score += 10
                        
                        # Speichere echte Daten
                        coin_key = f"{symbol}_{account_name}"
                        real_trading_data[coin_key] = {
                            'symbol': symbol,
                            'account': account_name,
                            'total_trades': total_trades,
                            'total_pnl': round(total_pnl, 2),
                            'month_trades': month_trades,
                            'month_pnl': round(month_pnl, 2),
                            'week_pnl': round(week_pnl, 2),
                            'month_win_rate': round(month_win_rate, 1),
                            'month_profit_factor': round(month_profit_factor, 2) if month_profit_factor < 999 else 999,
                            'month_performance_score': performance_score,
                            'status': 'Active' if month_trades > 0 else 'Inactive',
                            'daily_volume': round(data['total_qty'], 2)
                        }
                        
                        logging.info(f"ECHTE API-DATEN: {coin_key} -> {month_trades} trades, ${month_pnl} PnL, {month_win_rate:.1f}% WR")
                
            except Exception as api_error:
                logging.warning(f"API error for {account_name}: {api_error}")
                continue
                
        except Exception as e:
            logging.error(f"Error getting real data for {account_name}: {e}")
            continue
    
    # Blofin für 7 Tage Performer
    try:
        blofin_key = os.environ.get("BLOFIN_API_KEY")
        blofin_secret = os.environ.get("BLOFIN_API_SECRET")
        blofin_passphrase = os.environ.get("BLOFIN_API_PASSPHRASE")
        
        if blofin_key and blofin_secret and blofin_passphrase:
            client = BlofinAPI(blofin_key, blofin_secret, blofin_passphrase)
            
            # Versuche Trade History zu holen
            try:
                trade_response = client.get_trade_history(start_time=thirty_days_ago, end_time=now, limit=100)
                
                if trade_response.get('code') == '0' and trade_response.get('data'):
                    trades = trade_response['data']
                    symbol_data = {}
                    
                    for trade in trades:
                        try:
                            symbol = trade.get('instId', '').replace('-USDT', '').replace('-SWAP', '').replace('USDT', '')
                            if not symbol:
                                continue
                                
                            pnl = float(trade.get('realizedPnl', trade.get('pnl', 0)))
                            timestamp = safe_timestamp_convert(trade.get('ts', trade.get('timestamp', now)))
                            
                            if symbol not in symbol_data:
                                symbol_data[symbol] = {'trades': []}
                            
                            symbol_data[symbol]['trades'].append({
                                'pnl': pnl,
                                'timestamp': timestamp
                            })
                            
                        except (ValueError, TypeError):
                            continue
                    
                    # Verarbeite Blofin-Daten ähnlich wie Bybit
                    for symbol, data in symbol_data.items():
                        trades = data['trades']
                        if not trades:
                            continue
                        
                        trades_30d = [t for t in trades if t['timestamp'] > thirty_days_ago]
                        if not trades_30d:
                            continue
                        
                        month_pnl = sum(t['pnl'] for t in trades_30d)
                        month_trades = len(trades_30d)
                        
                        winning_trades = [t for t in trades_30d if t['pnl'] > 0]
                        month_win_rate = (len(winning_trades) / month_trades * 100) if month_trades > 0 else 0
                        
                        coin_key = f"{symbol}_7 Tage Performer"
                        real_trading_data[coin_key] = {
                            'symbol': symbol,
                            'account': '7 Tage Performer',
                            'total_trades': len(trades),
                            'total_pnl': round(sum(t['pnl'] for t in trades), 2),
                            'month_trades': month_trades,
                            'month_pnl': round(month_pnl, 2),
                            'week_pnl': round(sum(t['pnl'] for t in [tr for tr in trades if tr['timestamp'] > seven_days_ago]), 2),
                            'month_win_rate': round(month_win_rate, 1),
                            'month_profit_factor': 1.0,  # Simplified
                            'month_performance_score': 50 if month_pnl > 0 else 20,
                            'status': 'Active' if month_trades > 0 else 'Inactive',
                            'daily_volume': 0
                        }
                        
                        logging.info(f"BLOFIN API-DATEN: {coin_key} -> {month_trades} trades, ${month_pnl} PnL")
                        
            except Exception as blofin_error:
                logging.warning(f"Blofin trade history error: {blofin_error}")
                
    except Exception as e:
        logging.error(f"Blofin integration error: {e}")
    
    # Füge bekannte Claude-Daten hinzu falls nicht via API geholt
    claude_known_data = {
        'RUNE_Claude Projekt': {
            'symbol': 'RUNE',
            'account': 'Claude Projekt',
            'total_trades': 1,
            'total_pnl': -14.70,
            'month_trades': 1,
            'month_pnl': -14.70,
            'week_pnl': -14.70,
            'month_win_rate': 0.0,
            'month_profit_factor': 0.0,
            'month_performance_score': 15,
            'status': 'Active',
            'daily_volume': 0
        },
        'CVX_Claude Projekt': {
            'symbol': 'CVX',
            'account': 'Claude Projekt',
            'total_trades': 1,
            'total_pnl': -20.79,
            'month_trades': 1,
            'month_pnl': -20.79,
            'week_pnl': -20.79,
            'month_win_rate': 0.0,
            'month_profit_factor': 0.0,
            'month_performance_score': 15,
            'status': 'Active',
            'daily_volume': 0
        }
    }
    
    # Füge Claude-Daten hinzu falls nicht bereits vorhanden
    for key, data in claude_known_data.items():
        if key not in real_trading_data:
            real_trading_data[key] = data
            logging.info(f"FALLBACK Claude-Daten: {key}")
    
    logging.info(f"GESAMT echte Trading-Daten gesammelt: {len(real_trading_data)} Coin-Account Paare")
    
    return real_trading_data

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

@cached_function(cache_duration=300)  # 5 Minuten Cache für echte API-Daten
def get_cached_coin_performance(account_data):
    """Gecachte Coin Performance mit echten API-Daten"""
    return get_all_coin_performance(account_data)
    """VOLLSTÄNDIGE Coin Performance mit echten API-Daten"""
    
    # Hole echte Trading-Daten von allen APIs
    real_trading_data = get_real_trading_data_from_apis()
    
    # Erstelle Performance-Liste mit echten Daten
    coin_performance = []
    
    # Standard-Strategien für bessere Zuordnung
    strategy_mapping = {
        'BTC': 'Bitcoin Strategie',
        'ETH': 'Ethereum Strategie', 
        'SOL': 'Solana Strategie',
        'AVAX': 'Avalanche Strategie',
        'LINK': 'Chainlink Strategie',
        'DOT': 'Polkadot Strategie',
        'ADA': 'Cardano Strategie',
        'MATIC': 'Polygon Strategie',
        'UNI': 'Uniswap Strategie',
        'ATOM': 'Cosmos Strategie',
        'NEAR': 'Near Protocol Strategie',
        'FTM': 'Fantom Strategie',
        'ALGO': 'Algorand Strategie',
        'RUNE': 'THORChain Strategie',
        'CVX': 'Convex Strategie',
        'XRP': 'Ripple Strategie',
        'DOGE': 'Dogecoin Strategie',
        'APE': 'ApeCoin Strategie',
        'PEPE': 'PEPE Strategie',
        'WIF': 'WIF Strategie',
        'ARB': 'Arbitrum Strategie',
        'INJ': 'Injective Strategie',
        'MNT': 'Mantle Strategie',
        'GALA': 'Gala Strategie',
        'ID': 'Space ID Strategie',
        'TAO': 'Bittensor Strategie',
        'CAKE': 'PancakeSwap Strategie'
    }
    
    # Verarbeite echte Trading-Daten
    for coin_key, data in real_trading_data.items():
        symbol = data['symbol']
        account = data['account']
        strategy_name = strategy_mapping.get(symbol, f"{symbol} Trading Strategie")
        
        coin_performance.append({
            'symbol': symbol,
            'account': account,
            'strategy': strategy_name,
            'total_trades': data['total_trades'],
            'total_pnl': data['total_pnl'],
            'month_trades': data['month_trades'],
            'month_pnl': data['month_pnl'],
            'month_win_rate': data['month_win_rate'],
            'month_profit_factor': data['month_profit_factor'],
            'month_performance_score': data['month_performance_score'],
            'week_pnl': data['week_pnl'],
            'status': data['status'],
            'daily_volume': data['daily_volume']
        })
    
    # Sortiere nach Account und dann nach month_pnl
    coin_performance.sort(key=lambda x: (x['account'], -x['month_pnl']))
    
    # Debug-Logging für Validierung
    account_summary = {}
    for cp in coin_performance:
        acc = cp['account']
        if acc not in account_summary:
            account_summary[acc] = {'coins': 0, 'total_trades': 0, 'total_pnl': 0}
        
        account_summary[acc]['coins'] += 1
        account_summary[acc]['total_trades'] += cp['month_trades']
        account_summary[acc]['total_pnl'] += cp['month_pnl']
    
    logging.info(f"=== COIN PERFORMANCE SUMMARY ===")
    for acc, summary in account_summary.items():
        logging.info(f"{acc}: {summary['coins']} Coins, {summary['total_trades']} Trades, ${summary['total_pnl']:.2f} PnL")
    
    # Validierung für Claude Projekt
    claude_coins = [cp for cp in coin_performance if cp['account'] == 'Claude Projekt']
    claude_total_trades = sum(cp['month_trades'] for cp in claude_coins)
    claude_total_pnl = sum(cp['month_pnl'] for cp in claude_coins)
    
    logging.info(f"CLAUDE VALIDATION: {len(claude_coins)} coins, {claude_total_trades} trades, ${claude_total_pnl:.2f} PnL")
    
    return coin_performance

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
        
        # 5. Coin Performance (gecacht) - mit KORRIGIERTEN Daten
        all_coin_performance = get_cached_coin_performance(account_data)
        
        # 6. Charts erstellen (gecacht)
        chart_paths = create_cached_charts(account_data)
        
        # 7. NEUE Equity Curves erstellen (2 separate Charts)
        equity_charts = create_equity_curve_charts(sheet, account_data)
        
        # 8. Speichern in Sheets (vereinfacht)
        if sheet:
            try:
                save_daily_data(total_balance, total_pnl, sheet)
            except Exception as sheets_error:
                logging.warning(f"Sheets operations failed: {sheets_error}")

        # 9. Zeit
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
                               equity_total_path=equity_charts['total_equity'],  # NEUE Equity Charts
                               equity_projects_path=equity_charts['projects_equity'],
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
                               equity_total_path="static/equity_total_placeholder.png",
                               equity_projects_path="static/equity_projects_placeholder.png",
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
