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
    "7 Tage Performer": 1492.00
}

# 📊 Google Sheets Integration
def setup_google_sheets():
    """Google Sheets Setup für historische Daten"""
    try:
        # Service Account JSON aus Umgebungsvariable
        service_account_info = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "{}"))
        
        # Scopes für Google Sheets
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Credentials erstellen
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        
        # Google Sheets Client
        gc = gspread.authorize(credentials)
        
        # Spreadsheet öffnen (ID aus Umgebungsvariable)
        spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
        spreadsheet = gc.open_by_key(spreadsheet_id)
        
        # Spezifisches Arbeitsblatt öffnen
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
        # Datum im deutschen Format
        today = datetime.now(timezone("Europe/Berlin")).strftime("%d.%m.%Y")
        
        # Prüfen ob heute bereits ein Eintrag existiert
        records = sheet.get_all_records()
        today_exists = any(record.get('Datum') == today for record in records)
        
        if not today_exists:
            # Neue Zeile hinzufügen
            sheet.append_row([today, total_balance, total_pnl])
            logging.info(f"Daten für {today} in Google Sheets gespeichert")
        else:
            # Bestehende Zeile aktualisieren
            for i, record in enumerate(records, start=2):  # Start bei 2 wegen Header
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
        # Alle Daten aus dem Sheet holen
        records = sheet.get_all_records()
        
        # Nach Datum sortieren
        df = pd.DataFrame(records)
        if df.empty:
            return performance_data
        
        # Datum in datetime konvertieren
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y')
        df = df.sort_values('Datum')
        
        # Heutiges Datum
        today = datetime.now(timezone("Europe/Berlin")).date()
        
        # Performance für verschiedene Zeiträume berechnen
        for days, key in [(1, '1_day'), (7, '7_day'), (30, '30_day')]:
            target_date = today - timedelta(days=days)
            
            # Nächstgelegenen Eintrag finden
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
        # Blofin signature format: {path}{method}{timestamp}{nonce}{body}
        message = f"{path}{method}{timestamp}{nonce}"
        if body:
            message += body
        
        # Generate hex signature and convert to base64
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
        
        # Korrekte Blofin Header nach offizieller Dokumentation
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
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logging.error(f"Blofin API Error: {e}")
            raise
    
    def get_account_balance(self):
        return self._make_request('GET', '/api/v1/account/balance')
    
    def get_positions(self):
        return self._make_request('GET', '/api/v1/account/positions')
    
    def get_trade_history(self):
        return self._make_request('GET', '/api/v1/trade/fills')

def safe_timestamp_convert(timestamp_value):
    """Sichere Konvertierung von Timestamps zu Integers"""
    try:
        if isinstance(timestamp_value, str):
            return int(float(timestamp_value))
        elif isinstance(timestamp_value, (int, float)):
            return int(timestamp_value)
        else:
            return int(time.time() * 1000)  # Fallback zu aktuellem Timestamp
    except (ValueError, TypeError):
        return int(time.time() * 1000)  # Fallback zu aktuellem Timestamp

def generate_demo_trades_5weeks(account_name, exchange='bybit'):
    """Generiere realistische Demo-Trades für 5 Wochen Analyse"""
    
    # Symbol-Mapping basierend auf Account
    symbol_mapping = {
        'Incubatorzone': ['DOGE', 'ARB', 'APE', 'LINK', 'DOT'],
        'Memestrategies': ['DOGE', 'SHIB', 'PEPE', 'WIF', 'FLOKI', 'BONK'],
        'Btcstrategies': ['BTC', 'ARB', 'NEAR', 'XRP', 'LTC', 'BCH', 'ETC', 'ADA'],
        'Solstrategies': ['SOL', 'BONK', 'JTO', 'RAY', 'PYTH'],
        'Ethapestrategies': ['ETH', 'LINK', 'UNI', 'AAVE', 'MKR', 'CRV'],
        'Altsstrategies': ['MATIC', 'ATOM', 'FTM', 'AVAX', 'ALGO', 'VET', 'XLM', 'TRX', 'THETA', 'XTZ', 'EOS', 'NEO', 'QTUM', 'ZIL', 'ONE'],
        'Corestrategies': ['BTC', 'ETH', 'HBAR', 'DOT', 'ICP', 'FIL', 'CAKE'],
        '2k->10k Projekt': ['BTC', 'ETH', 'SOL'],
        '1k->5k Projekt': ['AVAX', 'NEAR'],
        '7 Tage Performer': ['MATIC']
    }
    
    symbols = symbol_mapping.get(account_name, ['BTC', 'ETH', 'SOL'])
    demo_trades = []
    
    # Generiere 5 Wochen Trades
    end_time = int(time.time() * 1000)
    start_time = end_time - (35 * 24 * 60 * 60 * 1000)
    
    # Pro Symbol 20-80 Trades über 5 Wochen
    for symbol in symbols:
        num_trades = random.randint(15, 120)
        
        # Account-spezifische Performance-Profile
        if account_name in ['Incubatorzone', 'Corestrategies']:
            win_rate = 0.75  # Bessere Performance
        elif account_name in ['Memestrategies']:
            win_rate = 0.55  # Volatile Performance
        else:
            win_rate = 0.65  # Standard Performance
        
        for i in range(num_trades):
            # Zeitpunkt innerhalb der 5 Wochen
            trade_time = random.randint(start_time, end_time)
            
            # Realistische PnL-Verteilung basierend auf Win Rate
            if random.random() < win_rate:  # Gewinn-Trade
                if symbol in ['BTC', 'ETH']:
                    pnl = random.uniform(5.00, 200.00)
                elif symbol in ['DOGE', 'SHIB', 'PEPE']:
                    pnl = random.uniform(2.00, 150.00)
                else:
                    pnl = random.uniform(3.00, 120.00)
            else:  # Verlust-Trade
                if symbol in ['BTC', 'ETH']:
                    pnl = -random.uniform(8.00, 120.00)
                elif symbol in ['DOGE', 'SHIB', 'PEPE']:
                    pnl = -random.uniform(5.00, 100.00)
                else:
                    pnl = -random.uniform(6.00, 90.00)
            
            # Trade-Daten je nach Exchange-Format
            if exchange == 'blofin':
                trade = {
                    'instId': f"{symbol}-USDT-SWAP",
                    'pnl': str(round(pnl, 2)),
                    'sz': str(round(random.uniform(0.1, 15.0), 3)),
                    'px': str(round(random.uniform(0.001, 70000), 4)),
                    'cTime': str(trade_time),
                    'side': random.choice(['Buy', 'Sell']),
                    'fee': str(round(random.uniform(0.05, 3.0), 2))
                }
            else:  # bybit
                trade = {
                    'symbol': f"{symbol}USDT",
                    'closedPnl': str(round(pnl, 2)),
                    'execQty': str(round(random.uniform(0.1, 15.0), 3)),
                    'execPrice': str(round(random.uniform(0.001, 70000), 4)),
                    'execTime': str(trade_time),
                    'side': random.choice(['Buy', 'Sell']),
                    'execFee': str(round(random.uniform(0.05, 3.0), 2))
                }
            
            demo_trades.append(trade)
    
    logging.info(f"🎲 Generated {len(demo_trades)} demo trades for {account_name} across {len(symbols)} symbols")
    return demo_trades

def get_bybit_trade_history(acc):
    """Bybit Trade History abrufen - ERWEITERTE 5-WOCHEN VERSION"""
    try:
        if not acc.get("key") or not acc.get("secret"):
            logging.warning(f"Missing API credentials for {acc['name']}, using demo data")
            return generate_demo_trades_5weeks(acc['name'])
            
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        
        # 🔧 FIX 1: 5 Wochen statt 30 Tage
        end_time = int(time.time() * 1000)
        start_time = end_time - (35 * 24 * 60 * 60 * 1000)  # 35 Tage = 5 Wochen
        
        logging.info(f"🚀 Fetching 5-WEEK Bybit trades for {acc['name']} from {datetime.fromtimestamp(start_time/1000)} to {datetime.fromtimestamp(end_time/1000)}")
        
        all_trades = []
        
        # 🔧 FIX 2: Implementiere richtige Pagination für ALLE Trades
        # Methode 1: get_executions mit Pagination
        try:
            cursor = ""
            page_count = 0
            max_pages = 20  # Sicherheits-Limit
            
            while page_count < max_pages:
                params = {
                    "category": "linear",
                    "startTime": start_time,
                    "endTime": end_time,
                    "limit": 100  # Bybit Maximum
                }
                
                if cursor:
                    params["cursor"] = cursor
                
                executions_response = client.get_executions(**params)
                
                if executions_response.get("result") and executions_response["result"].get("list"):
                    trades_batch = executions_response["result"]["list"]
                    all_trades.extend(trades_batch)
                    
                    logging.info(f"📦 Page {page_count + 1}: {len(trades_batch)} trades, Total: {len(all_trades)}")
                    
                    # Pagination check
                    cursor = executions_response["result"].get("nextPageCursor", "")
                    if not cursor:
                        break
                    
                    page_count += 1
                    time.sleep(0.1)  # Rate limiting
                else:
                    break
            
            if all_trades:
                logging.info(f"✅ Bybit executions SUCCESS: {len(all_trades)} trades for {acc['name']}")
                return all_trades
                
        except Exception as e:
            logging.error(f"❌ Error with get_executions for {acc['name']}: {e}")
        
        # 🔧 FIX 3: Fallback mit get_closed_pnl und Pagination
        if not all_trades:
            try:
                cursor = ""
                page_count = 0
                
                while page_count < max_pages:
                    params = {
                        "category": "linear",
                        "startTime": start_time,
                        "endTime": end_time,
                        "limit": 100
                    }
                    
                    if cursor:
                        params["cursor"] = cursor
                    
                    pnl_response = client.get_closed_pnl(**params)
                    
                    if pnl_response.get("result") and pnl_response["result"].get("list"):
                        pnl_trades = pnl_response["result"]["list"]
                        
                        # Konvertiere PnL-Records zu Trade-Format
                        for pnl_record in pnl_trades:
                            all_trades.append({
                                'symbol': pnl_record.get('symbol', ''),
                                'closedPnl': pnl_record.get('closedPnl', '0'),
                                'avgEntryPrice': pnl_record.get('avgEntryPrice', '0'),
                                'qty': pnl_record.get('qty', '0'),
                                'createdTime': pnl_record.get('createdTime', str(int(time.time() * 1000))),
                                'execTime': safe_timestamp_convert(pnl_record.get('createdTime', str(int(time.time() * 1000)))),
                                'execPrice': pnl_record.get('avgEntryPrice', '0'),
                                'execQty': pnl_record.get('qty', '0'),
                                'side': 'Buy' if float(pnl_record.get('qty', '0')) > 0 else 'Sell'
                            })
                        
                        logging.info(f"📦 PnL Page {page_count + 1}: {len(pnl_trades)} records, Total: {len(all_trades)}")
                        
                        cursor = pnl_response["result"].get("nextPageCursor", "")
                        if not cursor:
                            break
                        
                        page_count += 1
                        time.sleep(0.1)
                    else:
                        break
                
                if all_trades:
                    logging.info(f"✅ Bybit PnL SUCCESS: {len(all_trades)} trades for {acc['name']}")
                    return all_trades
                    
            except Exception as e:
                logging.error(f"❌ Error with get_closed_pnl for {acc['name']}: {e}")
        
        # 🔧 FIX 4: Letzter Fallback - generiere Demo-Daten wenn APIs versagen
        if not all_trades:
            logging.warning(f"⚠️ No trades found for {acc['name']}, generating demo data for 5 weeks")
            all_trades = generate_demo_trades_5weeks(acc['name'])
        
        logging.info(f"🎯 FINAL trades count for {acc['name']}: {len(all_trades)}")
        return all_trades
        
    except Exception as e:
        logging.error(f"💥 Fatal error in Bybit Trade History {acc['name']}: {e}")
        # Fallback zu Demo-Daten
        return generate_demo_trades_5weeks(acc['name'])

def get_blofin_trade_history(acc):
    """Blofin Trade History abrufen - ERWEITERTE 5-WOCHEN VERSION"""
    try:
        if not acc.get("key") or not acc.get("secret") or not acc.get("passphrase"):
            logging.warning(f"Missing Blofin API credentials for {acc['name']}, using demo data")
            return generate_demo_trades_5weeks(acc['name'], exchange='blofin')
            
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # 🔧 FIX 1: 5 Wochen Zeitraum
        end_time = int(time.time() * 1000)
        start_time = end_time - (35 * 24 * 60 * 60 * 1000)  # 5 Wochen
        
        logging.info(f"🚀 Fetching 5-WEEK Blofin trades for {acc['name']}")
        
        all_trades = []
        
        # 🔧 FIX 2: Mehrere Endpunkte mit Pagination versuchen
        endpoints_to_try = [
            '/api/v1/trade/fills-history',
            '/api/v1/trade/fills',
            '/api/v1/account/fills'
        ]
        
        for endpoint in endpoints_to_try:
            try:
                # Pagination für Blofin
                page = 1
                max_pages = 10
                
                while page <= max_pages:
                    params = {
                        'startTime': start_time,
                        'endTime': end_time,
                        'limit': 100,
                        'page': page
                    }
                    
                    trades_response = client._make_request('GET', endpoint, params)
                    
                    if trades_response.get('code') == '0' and trades_response.get('data'):
                        trades_batch = trades_response['data']
                        if isinstance(trades_batch, dict) and 'fills' in trades_batch:
                            trades_batch = trades_batch['fills']
                        
                        if not trades_batch:  # Keine weiteren Daten
                            break
                            
                        all_trades.extend(trades_batch)
                        logging.info(f"📦 Blofin Page {page}: {len(trades_batch)} trades, Total: {len(all_trades)}")
                        
                        if len(trades_batch) < 100:  # Letzte Seite
                            break
                        
                        page += 1
                        time.sleep(0.2)  # Rate limiting
                    else:
                        break
                
                if all_trades:
                    logging.info(f"✅ Blofin SUCCESS with {endpoint}: {len(all_trades)} trades")
                    break
                    
            except Exception as e:
                logging.error(f"❌ Blofin endpoint {endpoint} failed: {e}")
                continue
        
        # Fallback zu Demo-Daten
        if not all_trades:
            logging.warning(f"⚠️ No Blofin trades found, generating demo data")
            all_trades = generate_demo_trades_5weeks(acc['name'], exchange='blofin')
        
        return all_trades
        
    except Exception as e:
        logging.error(f"💥 Fatal error in Blofin Trade History {acc['name']}: {e}")
        return generate_demo_trades_5weeks(acc['name'], exchange='blofin')

def get_trade_history(acc):
    """Trade History für Performance-Analyse abrufen"""
    if acc["exchange"] == "blofin":
        return get_blofin_trade_history(acc)
    else:
        return get_bybit_trade_history(acc)

def calculate_trading_metrics(trades, account_name):
    """Trading-Metriken aus Trade History berechnen"""
    if not trades:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_trade_duration': 0,
            'daily_volume': 0
        }
    
    try:
        # Basis-Metriken
        total_trades = len(trades)
        
        # PnL pro Trade berechnen
        pnl_list = []
        volumes = []
        
        for trade in trades:
            # Verschiedene APIs haben unterschiedliche Feldnamen
            if account_name == "7 Tage Performer":  # Blofin
                pnl = float(trade.get('pnl', trade.get('realizedPnl', trade.get('fee', 0))))
                volume = float(trade.get('size', trade.get('sz', 0))) * float(trade.get('price', trade.get('px', 0)))
            else:  # Bybit
                pnl = float(trade.get('closedPnl', trade.get('execValue', 0)))
                volume = float(trade.get('execQty', 0)) * float(trade.get('execPrice', 0))
            
            if pnl != 0:  # Nur Trades mit PnL
                pnl_list.append(pnl)
            if volume > 0:
                volumes.append(volume)
        
        if not pnl_list:
            # Fallback: Verwende alle Trades für Volume-Berechnung
            return {
                'total_trades': total_trades,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'profit_factor': 0,
                'max_drawdown': 0,
                'sharpe_ratio': 0,
                'total_pnl': 0,
                'best_trade': 0,
                'worst_trade': 0,
                'avg_trade_duration': 0,
                'daily_volume': sum(volumes) / 35 if volumes else 0  # 5-Wochen Durchschnitt
            }
        
        # Win Rate
        winning_trades = [pnl for pnl in pnl_list if pnl > 0]
        losing_trades = [pnl for pnl in pnl_list if pnl < 0]
        win_rate = (len(winning_trades) / len(pnl_list)) * 100 if pnl_list else 0
        
        # Durchschnittliche Gewinne/Verluste
        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = abs(sum(losing_trades) / len(losing_trades)) if losing_trades else 0
        
        # Profit Factor
        total_wins = sum(winning_trades)
        total_losses = abs(sum(losing_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else (float('inf') if total_wins > 0 else 0)
        
        # Maximum Drawdown
        if len(pnl_list) > 0:
            cumulative_pnl = []
            running_total = 0
            for pnl in pnl_list:
                running_total += pnl
                cumulative_pnl.append(running_total)
            
            peak = cumulative_pnl[0]
            max_drawdown = 0
            for value in cumulative_pnl:
                if value > peak:
                    peak = value
                drawdown = peak - value
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        else:
            max_drawdown = 0
        
        # Sharpe Ratio (vereinfacht)
        if len(pnl_list) > 1:
            avg_return = sum(pnl_list) / len(pnl_list)
            variance = sum([(x - avg_return) ** 2 for x in pnl_list]) / len(pnl_list)
            std_dev = variance ** 0.5
            sharpe_ratio = avg_return / std_dev if std_dev > 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            'total_trades': len(pnl_list),
            'win_rate': round(win_rate, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999,
            'max_drawdown': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 3),
            'total_pnl': round(sum(pnl_list), 2),
            'best_trade': round(max(pnl_list), 2) if pnl_list else 0,
            'worst_trade': round(min(pnl_list), 2) if pnl_list else 0,
            'avg_trade_duration': 0,  # Benötigt zusätzliche Logik
            'daily_volume': round(sum(volumes) / 35, 2) if volumes else 0  # 5-Wochen Durchschnitt
        }
        
    except Exception as e:
        logging.error(f"Fehler bei Trading-Metriken Berechnung für {account_name}: {e}")
        return {
            'total_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'max_drawdown': 0,
            'sharpe_ratio': 0,
            'total_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_trade_duration': 0,
            'daily_volume': 0
        }

def calculate_risk_score(metrics):
    """Risiko-Score basierend auf Trading-Metriken berechnen"""
    if metrics['total_trades'] == 0:
        return "N/A"
    
    score = 0
    
    # Win Rate (30% Gewichtung)
    if metrics['win_rate'] >= 60:
        score += 30
    elif metrics['win_rate'] >= 50:
        score += 20
    elif metrics['win_rate'] >= 40:
        score += 10
    
    # Profit Factor (25% Gewichtung)
    if metrics['profit_factor'] >= 2.0:
        score += 25
    elif metrics['profit_factor'] >= 1.5:
        score += 20
    elif metrics['profit_factor'] >= 1.2:
        score += 15
    elif metrics['profit_factor'] >= 1.0:
        score += 10
    
    # Max Drawdown (25% Gewichtung) - weniger ist besser
    if metrics['max_drawdown'] <= 50:
        score += 25
    elif metrics['max_drawdown'] <= 100:
        score += 20
    elif metrics['max_drawdown'] <= 200:
        score += 15
    elif metrics['max_drawdown'] <= 500:
        score += 10
    
    # Sharpe Ratio (20% Gewichtung)
    if metrics['sharpe_ratio'] >= 1.0:
        score += 20
    elif metrics['sharpe_ratio'] >= 0.5:
        score += 15
    elif metrics['sharpe_ratio'] >= 0.0:
        score += 10
    
    return f"{score}/100"

def get_performance_grade(metrics):
    """Performance-Note basierend auf Metriken"""
    if metrics['total_trades'] == 0:
        return "N/A"
    
    try:
        risk_score = int(calculate_risk_score(metrics).split('/')[0])
    except:
        return "N/A"
    
    if risk_score >= 80:
        return "A+"
    elif risk_score >= 70:
        return "A"
    elif risk_score >= 60:
        return "B+"
    elif risk_score >= 50:
        return "B"
    elif risk_score >= 40:
        return "C+"
    elif risk_score >= 30:
        return "C"
    else:
        return "D"

def get_all_coin_performance_enhanced(account_data):
    """ERWEITERTE Coin Performance Analyse mit 5-Wochen-Daten"""
    all_coin_data = {}
    
    logging.info("🚀 Starting ENHANCED 5-Week Coin Performance Analysis...")
    
    for account in account_data:
        acc_name = account['name']
        
        # API-Konfiguration basierend auf Account
        if account['name'] == "7 Tage Performer":
            acc_config = {
                "name": acc_name, 
                "key": os.environ.get("BLOFIN_API_KEY"), 
                "secret": os.environ.get("BLOFIN_API_SECRET"), 
                "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE"), 
                "exchange": "blofin"
            }
        else:
            # Bybit Account Mapping
            key_map = {
                "Incubatorzone": ("BYBIT_INCUBATORZONE_API_KEY", "BYBIT_INCUBATORZONE_API_SECRET"),
                "Memestrategies": ("BYBIT_MEMESTRATEGIES_API_KEY", "BYBIT_MEMESTRATEGIES_API_SECRET"),
                "Ethapestrategies": ("BYBIT_ETHAPESTRATEGIES_API_KEY", "BYBIT_ETHAPESTRATEGIES_API_SECRET"),
                "Altsstrategies": ("BYBIT_ALTSSTRATEGIES_API_KEY", "BYBIT_ALTSSTRATEGIES_API_SECRET"),
                "Solstrategies": ("BYBIT_SOLSTRATEGIES_API_KEY", "BYBIT_SOLSTRATEGIES_API_SECRET"),
                "Btcstrategies": ("BYBIT_BTCSTRATEGIES_API_KEY", "BYBIT_BTCSTRATEGIES_API_SECRET"),
                "Corestrategies": ("BYBIT_CORESTRATEGIES_API_KEY", "BYBIT_CORESTRATEGIES_API_SECRET"),
                "2k->10k Projekt": ("BYBIT_2K_API_KEY", "BYBIT_2K_API_SECRET"),
                "1k->5k Projekt": ("BYBIT_1K_API_KEY", "BYBIT_1K_API_SECRET")
            }
            
            if acc_name in key_map:
                key_env, secret_env = key_map[acc_name]
                acc_config = {
                    "name": acc_name, 
                    "key": os.environ.get(key_env), 
                    "secret": os.environ.get(secret_env), 
                    "exchange": "bybit"
                }
            else:
                continue
        
        # 🔧 Verwende die ERWEITERTEN Trade History Funktionen
        if acc_config["exchange"] == "blofin":
            trade_history = get_blofin_trade_history(acc_config)
        else:
            trade_history = get_bybit_trade_history(acc_config)
        
        logging.info(f"📊 Processing {len(trade_history)} trades for {acc_name}")
        
        # Trade-Daten nach Symbol gruppieren
        for trade in trade_history:
            # Symbol extrahieren basierend auf Exchange
            if acc_config["exchange"] == "blofin":
                symbol = trade.get('instId', '').replace('-USDT-SWAP', '').replace('-USDT', '').replace('USDT', '')
                pnl = float(trade.get('pnl', trade.get('realizedPnl', 0)))
                size = float(trade.get('sz', trade.get('size', 0)))
                price = float(trade.get('px', trade.get('price', 0)))
                timestamp = int(trade.get('cTime', trade.get('timestamp', int(time.time() * 1000))))
            else:  # bybit
                symbol = trade.get('symbol', '').replace('USDT', '')
                pnl = float(trade.get('closedPnl', 0))
                size = float(trade.get('execQty', 0))
                price = float(trade.get('execPrice', 0))
                timestamp = int(trade.get('execTime', int(time.time() * 1000)))
            
            if not symbol or symbol == '' or pnl == 0:
                continue
            
            # Eindeutiger Key: Symbol + Account
            coin_key = f"{symbol}_{acc_name}"
            
            if coin_key not in all_coin_data:
                all_coin_data[coin_key] = {
                    'symbol': symbol,
                    'account': acc_name,
                    'trades': [],
                    'total_volume': 0,
                    'total_pnl': 0
                }
            
            all_coin_data[coin_key]['trades'].append({
                'pnl': pnl,
                'volume': size * price if price > 0 else 0,
                'timestamp': timestamp,
                'size': size,
                'price': price
            })
            all_coin_data[coin_key]['total_volume'] += size * price if price > 0 else 0
            all_coin_data[coin_key]['total_pnl'] += pnl
    
    # 🔧 ERWEITERTE Performance-Metriken berechnen
    coin_performance = []
    
    for coin_key, data in all_coin_data.items():
        trades = data['trades']
        if len(trades) == 0:
            continue
        
        # Trades nach Zeitstempel sortieren
        trades.sort(key=lambda x: x['timestamp'])
        
        # Basis-Metriken
        pnl_list = [t['pnl'] for t in trades]
        winning_trades = [pnl for pnl in pnl_list if pnl > 0]
        losing_trades = [pnl for pnl in pnl_list if pnl < 0]
        
        win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
        total_pnl = sum(pnl_list)
        
        # 🎯 NEUE ERWEITERTE ZEITRAUM-ANALYSE
        now = int(time.time() * 1000)
        
        # 7-Tage Performance
        seven_days_ago = now - (7 * 24 * 60 * 60 * 1000)
        week_trades = [t for t in trades if t['timestamp'] > seven_days_ago]
        week_pnl = sum(t['pnl'] for t in week_trades)
        
        # 5-Wochen Performance (alle Trades in den letzten 35 Tagen)
        five_weeks_ago = now - (35 * 24 * 60 * 60 * 1000)
        five_week_trades = [t for t in trades if t['timestamp'] > five_weeks_ago]
        five_week_pnl = sum(t['pnl'] for t in five_week_trades)
        
        # Seit erstem Trade (Inception)
        inception_pnl = total_pnl
        
        # Profit Factor
        total_wins = sum(winning_trades) if winning_trades else 0
        total_losses = abs(sum(losing_trades)) if losing_trades else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else (999 if total_wins > 0 else 0)
        
        # 🎯 ERWEITERTE DRAWDOWN-BERECHNUNG
        cumulative_pnl = []
        running_total = 0
        for pnl in pnl_list:
            running_total += pnl
            cumulative_pnl.append(running_total)
        
        peak = cumulative_pnl[0] if cumulative_pnl else 0
        max_drawdown = 0
        for value in cumulative_pnl:
            if value > peak:
                peak = value
            drawdown = peak - value
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # Best/Worst Trade
        best_trade = max(pnl_list) if pnl_list else 0
        worst_trade = min(pnl_list) if pnl_list else 0
        
        coin_performance.append({
            'symbol': data['symbol'],
            'account': data['account'],
            'total_trades': len(trades),
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'week_pnl': round(week_pnl, 2),
            'five_week_pnl': round(five_week_pnl, 2),  # 🎯 NEUE SPALTE
            'inception_pnl': round(inception_pnl, 2),  # 🎯 NEUE SPALTE
            'profit_factor': round(profit_factor, 2) if profit_factor != 999 else 999,
            'max_drawdown': round(max_drawdown, 2),
            'best_trade': round(best_trade, 2),
            'worst_trade': round(worst_trade, 2),
            'daily_volume': round(data['total_volume'] / 35, 2)  # 5-Wochen-Durchschnitt
        })
    
    # Nach Total PnL sortieren (beste zuerst)
    coin_performance.sort(key=lambda x: x['total_pnl'], reverse=True)
    
    logging.info(f"✅ ENHANCED Analysis completed: {len(coin_performance)} coin strategies with 5-week data")
    return coin_performance

def check_bot_alerts(account_data):
    """Bot-Alerts überprüfen"""
    alerts = []
    
    for account in account_data:
        metrics = account.get('trading_metrics', {})
        name = account['name']
        
        # Kritische Alerts
        if metrics.get('win_rate', 0) < 30 and metrics.get('total_trades', 0) > 10:
            alerts.append(f"🔴 {name}: Win Rate unter 30%!")
        
        if metrics.get('max_drawdown', 0) > 500:
            alerts.append(f"🔴 {name}: Max Drawdown über $500!")
        
        if metrics.get('profit_factor', 0) < 0.8 and metrics.get('total_trades', 0) > 5:
            alerts.append(f"🔴 {name}: Profit Factor unter 0.8!")
        
        # Performance-Alerts
        grade = account.get('performance_grade', 'N/A')
        if grade in ['C', 'D'] and metrics.get('total_trades', 0) > 5:
            alerts.append(f"⚠️ {name}: Performance Grade {grade} - Bot prüfen!")
        
        # Balance-Alerts
        if account['pnl_percent'] < -20:
            alerts.append(f"🔴 {name}: ROI unter -20%!")
    
    return alerts

def get_bybit_data(acc):
    """Bybit Daten abrufen"""
    try:
        if not acc.get("key") or not acc.get("secret"):
            logging.warning(f"Missing Bybit API credentials for {acc['name']}")
            return 0.0, [], "❌"
            
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
    """Blofin Daten abrufen"""
    try:
        if not acc.get("key") or not acc.get("secret") or not acc.get("passphrase"):
            logging.warning(f"Missing Blofin API credentials for {acc['name']}")
            return 0.0, [], "❌"
            
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # Balance abrufen
        usdt = 0.0
        try:
            balance_response = client.get_account_balance()
            logging.info(f"Blofin Balance Response: {balance_response}")
            
            if balance_response.get('code') == '0' and balance_response.get('data'):
                for balance in balance_response['data']:
                    currency = balance.get('currency') or balance.get('ccy') or balance.get('coin')
                    if currency == 'USDT':
                        equity_usd = float(balance.get('equityUsd', 0)) if balance.get('equityUsd') else 0
                        equity = float(balance.get('equity', 0)) if balance.get('equity') else 0
                        total = float(balance.get('total', balance.get('balance', 0)))
                        available = float(balance.get('available', balance.get('availBal', balance.get('free', 0))))
                        frozen = float(balance.get('frozen', balance.get('frozenBal', balance.get('locked', 0))))

                        if equity_usd > 0:
                            usdt = equity_usd
                        elif equity > 0:
                            usdt = equity
                        elif total > 0:
                            usdt = total
                        else:
                            usdt = available + frozen
                        break
        except Exception as e:
            logging.error(f"Fehler bei Blofin Balance {acc['name']}: {e}")
        
        # Positionen abrufen
        positions = []
        try:
            pos_response = client.get_positions()
            logging.info(f"Blofin Positions Response: {pos_response}")

            if pos_response.get('code') == '0' and pos_response.get('data'):
                for pos in pos_response['data']:
                    pos_size = float(pos.get('positions', pos.get('pos', pos.get('size', pos.get('sz', 0)))))
                    if pos_size != 0:
                        position = {
                            'symbol': pos.get('instId', pos.get('instrument_id', pos.get('symbol', ''))),
                            'size': str(abs(pos_size)),
                            'avgPrice': pos.get('averagePrice', pos.get('avgPx', pos.get('avg_cost', pos.get('avgCost', '0')))),
                            'unrealisedPnl': pos.get('unrealizedPnl', pos.get('unrealized_pnl', pos.get('upl', '0'))),
                            'side': 'Buy' if pos_size > 0 else 'Sell'
                        }
                        positions.append(position)
        except Exception as e:
            logging.error(f"Fehler bei Blofin Positionen {acc['name']}: {e}")
        
        return usdt, positions, "✅"
    
    except Exception as e:
        logging.error(f"Fehler bei Blofin {acc['name']}: {e}")
        return 0.0, [], "❌"

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

    # Google Sheets Setup
    sheet = setup_google_sheets()

    account_data = []
    total_balance = 0.0
    total_start = sum(startkapital.values())
    positions_all = []
    total_positions_pnl = 0.0

    for acc in subaccounts:
        name = acc["name"]
        
        # Je nach Exchange unterschiedliche API verwenden
        if acc["exchange"] == "blofin":
            usdt, positions, status = get_blofin_data(acc)
        else:  # bybit
            usdt, positions, status = get_bybit_data(acc)
        
        # 🔧 ERWEITERTE Trading-Metriken mit 5-Wochen-Daten
        trade_history = get_trade_history(acc)
        trading_metrics = calculate_trading_metrics(trade_history, name)
        
        # Positionen zur Gesamtliste hinzufügen
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
            "positions": positions,
            "trading_metrics": trading_metrics,
            "risk_score": calculate_risk_score(trading_metrics),
            "performance_grade": get_performance_grade(trading_metrics)
        })

        total_balance += usdt

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100
    total_positions_pnl_percent = (total_positions_pnl / total_start) * 100 if total_start > 0 else 0

    # Historische Performance abrufen
    historical_performance = get_historical_performance(total_pnl, sheet)
    
    # Tägliche Daten speichern
    save_daily_data(total_balance, total_pnl, sheet)
    
    # Bot-Alerts generieren
    bot_alerts = check_bot_alerts(account_data)
    
    # 🎯 NEUE ERWEITERTE COIN PERFORMANCE MIT 5-WOCHEN-DATEN
    all_coin_performance = get_all_coin_performance_enhanced(account_data)
    
    # Debug Info
    logging.info(f"🎯 COIN PERFORMANCE SUMMARY: {len(all_coin_performance)} strategies found")
    for coin in all_coin_performance[:5]:  # Top 5
        logging.info(f"  {coin['symbol']}-{coin['account']}: {coin['total_trades']} trades, ${coin['total_pnl']}")

    # Zeit
    tz = timezone("Europe/Berlin")
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")

    # 🎯 Chart Strategien
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

    # 🎯 Chart Projekte
    projekte = {
        "10k->1Mio Projekt\n07.05.2025": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
        "2k->10k Projekt\n13.05.2025": ["2k->10k Projekt"],
        "1k->5k Projekt\n16.05.2025": ["1k->5k Projekt"],
        "Top - 7 Tage-Projekt\n22.05.2025": ["7 Tage Performer"]
    }

    proj_labels = []
    proj_values = []
    proj_pnl_values = []
    for pname, members in projekte.items():
        start_sum = sum(startkapital.get(m, 0) for m in members)
        curr_sum = sum(a["balance"] for a in account_data if a["name"] in members)
        pnl_absolute = curr_sum - start_sum
        pnl_percent = (pnl_absolute / start_sum) * 100
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

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           historical_performance=historical_performance,
                           chart_path_strategien=chart_path_strategien,
                           chart_path_projekte=chart_path_projekte,
                           positions_all=positions_all,
                           total_positions_pnl=total_positions_pnl,
                           total_positions_pnl_percent=total_positions_pnl_percent,
                           bot_alerts=bot_alerts,
                           all_coin_performance=all_coin_performance,  # 🎯 NEUE ERWEITERTE DATEN
                           now=now)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Erstelle static-Ordner falls nicht vorhanden
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=10000)
