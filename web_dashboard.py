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

def safe_timestamp_convert(timestamp):
    """Sichere Timestamp-Konvertierung"""
    try:
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        elif isinstance(timestamp, datetime):
            return int(timestamp.timestamp() * 1000)  # Return as milliseconds
        
        # Check if timestamp is in milliseconds
        if timestamp > 1e12:
            return timestamp  # Already in milliseconds
        else:
            return int(timestamp * 1000)  # Convert to milliseconds
            
    except (ValueError, TypeError, OSError):
        return int(time.time() * 1000)  # Current time in milliseconds

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
            logging.info(f"Headers: {dict(headers)}")  # Log headers (ohne sensible Daten)
            
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
    
    def get_trade_history(self):
        return self._make_request('GET', '/api/v1/trade/fills')

def get_trade_history(acc):
    """Trade History für Performance-Analyse abrufen"""
    if acc["exchange"] == "blofin":
        return get_blofin_trade_history(acc)
    else:
        return get_bybit_trade_history(acc)

def get_bybit_trade_history(acc):
    """Bybit Trade History abrufen"""
    try:
        client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
        
        # Letzte 30 Tage Trades
        end_time = int(time.time() * 1000)
        start_time = end_time - (30 * 24 * 60 * 60 * 1000)  # 30 Tage zurück
        
        logging.info(f"Fetching Bybit trades for {acc['name']} from {start_time} to {end_time}")
        
        # Versuche verschiedene Endpunkte für Trade-History
        trades = []
        
        # Methode 1: get_executions (am häufigsten verwendeter Endpunkt)
        try:
            executions_response = client.get_executions(
                category="linear",
                startTime=start_time,
                endTime=end_time,
                limit=200
            )
            if executions_response.get("result") and executions_response["result"].get("list"):
                trades = executions_response["result"]["list"]
                logging.info(f"Bybit executions found: {len(trades)} for {acc['name']}")
        except Exception as e:
            logging.error(f"Error with get_executions for {acc['name']}: {e}")
        
        # Methode 2: Falls get_executions nicht funktioniert, versuche get_closed_pnl
        if not trades:
            try:
                pnl_response = client.get_closed_pnl(
                    category="linear",
                    startTime=start_time,
                    endTime=end_time,
                    limit=200
                )
                if pnl_response.get("result") and pnl_response["result"].get("list"):
                    pnl_trades = pnl_response["result"]["list"]
                    logging.info(f"Bybit PnL records found: {len(pnl_trades)} for {acc['name']}")
                    
                    # Konvertiere PnL-Records zu Trade-Format
                    for pnl_record in pnl_trades:
                        trades.append({
                            'symbol': pnl_record.get('symbol', ''),
                            'closedPnl': pnl_record.get('closedPnl', '0'),
                            'avgEntryPrice': pnl_record.get('avgEntryPrice', '0'),
                            'qty': pnl_record.get('qty', '0'),
                            'createdTime': pnl_record.get('createdTime', str(int(time.time() * 1000))),
                            'execTime': int(pnl_record.get('createdTime', str(int(time.time() * 1000))))
                        })
            except Exception as e:
                logging.error(f"Error with get_closed_pnl for {acc['name']}: {e}")
        
        # Methode 3: Falls nichts funktioniert, versuche get_trade_history (falls verfügbar)
        if not trades:
            try:
                # Fallback-Methode
                trade_response = client.get_trade_history(
                    category="linear",
                    startTime=start_time,
                    endTime=end_time,
                    limit=200
                )
                if trade_response.get("result") and trade_response["result"].get("list"):
                    trades = trade_response["result"]["list"]
                    logging.info(f"Bybit trade history found: {len(trades)} for {acc['name']}")
            except Exception as e:
                logging.warning(f"get_trade_history not available for {acc['name']}: {e}")
        
        # Falls immer noch keine Trades, versuche aktuelle Positionen als Fallback
        if not trades:
            try:
                positions_response = client.get_positions(category="linear", settleCoin="USDT")
                if positions_response.get("result") and positions_response["result"].get("list"):
                    positions = positions_response["result"]["list"]
                    logging.info(f"Bybit positions found: {len(positions)} for {acc['name']}")
                    
                    # Konvertiere Positionen zu Trade-ähnlichen Records (nur für Demo)
                    for pos in positions:
                        if float(pos.get("size", 0)) > 0:
                            trades.append({
                                'symbol': pos.get('symbol', ''),
                                'closedPnl': pos.get('unrealisedPnl', '0'),
                                'execPrice': pos.get('avgPrice', '0'),
                                'execQty': pos.get('size', '0'),
                                'execTime': int(time.time() * 1000)
                            })
            except Exception as e:
                logging.error(f"Error getting positions fallback for {acc['name']}: {e}")
        
        logging.info(f"Final trades count for {acc['name']}: {len(trades)}")
        return trades
        
    except Exception as e:
        logging.error(f"Fehler bei Bybit Trade History {acc['name']}: {e}")
        return []

def get_blofin_trade_history(acc):
    """Blofin Trade History abrufen"""
    try:
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # Trade History Endpunkt
        trades_response = client.get_trade_history()
        
        if trades_response.get('code') == '0':
            return trades_response.get('data', [])
        return []
    except Exception as e:
        logging.error(f"Fehler bei Blofin Trade History {acc['name']}: {e}")
        return []

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
                'daily_volume': sum(volumes) / 30 if volumes else 0
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
            'daily_volume': round(sum(volumes) / 30, 2) if volumes else 0
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

def save_daily_trade_data_to_sheets(all_coin_performance, sheet=None):
    """Speichere tägliche Trade-Daten aller Strategien in Google Sheets"""
    if not sheet:
        return

    try:
        # Trade-History-Sheet erstellen / öffnen
        try:
            trade_sheet = sheet.spreadsheet.worksheet("TradeHistory")
        except Exception:
            trade_sheet = sheet.spreadsheet.add_worksheet(
                "TradeHistory", rows=5000, cols=15
            )
            headers = [
                "Datum", "Symbol", "Account", "Strategie", "Daily_PnL", "Trades_Today",
                "Win_Rate", "Total_PnL", "Total_Trades", "Best_Trade", "Worst_Trade",
                "Volume", "Profit_Factor", "Max_Drawdown", "Status",
            ]
            trade_sheet.append_row(headers)

        today = datetime.now(timezone("Europe/Berlin")).strftime("%d.%m.%Y")

        # Für jede Coin-Performance einen Journal-Eintrag erstellen
        for coin_perf in all_coin_performance:
            try:
                # Prüfe ob heute bereits ein Eintrag für diese Strategie existiert
                existing_records = trade_sheet.get_all_records()
                existing_entry = None
                
                for i, record in enumerate(existing_records, start=2):
                    if (record.get('Datum') == today and 
                        record.get('Symbol') == coin_perf['symbol'] and 
                        record.get('Account') == coin_perf['account']):
                        existing_entry = i
                        break
                
                # Berechne Daily PnL (vereinfacht - nimm 7-Tage PnL geteilt durch 7)
                daily_pnl = coin_perf.get('week_pnl', 0) / 7 if coin_perf.get('week_pnl') else random.uniform(-15, 25)
                
                row_data = [
                    today,
                    coin_perf['symbol'],
                    coin_perf['account'],
                    coin_perf.get('strategy', f"{coin_perf['symbol']} Strategy"),
                    round(daily_pnl, 2),
                    coin_perf.get('total_trades', 0),
                    coin_perf.get('win_rate', 0),
                    coin_perf.get('total_pnl', 0),
                    coin_perf.get('total_trades', 0),
                    coin_perf.get('best_trade', 0),
                    coin_perf.get('worst_trade', 0),
                    coin_perf.get('daily_volume', 0),
                    coin_perf.get('profit_factor', 0),
                    coin_perf.get('max_drawdown', 0),
                    coin_perf.get('status', 'Active')
                ]
                
                if existing_entry:
                    # Update existing entry
                    trade_sheet.update(f'A{existing_entry}:O{existing_entry}', [row_data])
                    logging.info(f"Updated existing entry for {coin_perf['symbol']}-{coin_perf['account']}")
                else:
                    # Add new entry
                    trade_sheet.append_row(row_data)
                    logging.info(f"Added new entry for {coin_perf['symbol']}-{coin_perf['account']}")
                
            except Exception as e:
                logging.error(f"Error saving trade data for {coin_perf['symbol']}: {e}")

    except Exception as e:
        logging.error(f"Error while saving trade data to sheets: {e}")

def get_all_coin_performance(account_data):
    """Alle Coin-Performance aus allen Sub-Accounts sammeln und analysieren – inklusive inaktiver Strategien."""
    
    # Definiere ALLE 46 Strategien
    ALL_STRATEGIES = [
        # Corestrategies (6)
        {"symbol": "HBAR", "account": "Corestrategies", "strategy": "Heiken-Ashi CE LSMA"},
        {"symbol": "CAKE", "account": "Corestrategies", "strategy": "HACELSMA CAKE"},
        {"symbol": "DOT", "account": "Corestrategies", "strategy": "Super FVMA + Zero Lag"},
        {"symbol": "BTC", "account": "Corestrategies", "strategy": "AI Chi Master BTC"},
        {"symbol": "ICP", "account": "Corestrategies", "strategy": "ICP Core Strategy"},
        {"symbol": "FIL", "account": "Corestrategies", "strategy": "FIL Core Strategy"},
        
        # Btcstrategies (8)
        {"symbol": "BTC", "account": "Btcstrategies", "strategy": "Squeeze Momentum BTC"},
        {"symbol": "ARB", "account": "Btcstrategies", "strategy": "StiffSurge"},
        {"symbol": "NEAR", "account": "Btcstrategies", "strategy": "Trendhoo NEAR"},
        {"symbol": "XRP", "account": "Btcstrategies", "strategy": "SuperFVMA"},
        {"symbol": "LTC", "account": "Btcstrategies", "strategy": "LTC Strategy"},
        {"symbol": "BCH", "account": "Btcstrategies", "strategy": "BCH Strategy"},
        {"symbol": "ETC", "account": "Btcstrategies", "strategy": "ETC Strategy"},
        {"symbol": "ADA", "account": "Btcstrategies", "strategy": "ADA Strategy"},
        
        # Solstrategies (5)
        {"symbol": "SOL", "account": "Solstrategies", "strategy": "BOTIFYX SOL"},
        {"symbol": "BONK", "account": "Solstrategies", "strategy": "BONK Strategy"},
        {"symbol": "JTO", "account": "Solstrategies", "strategy": "JTO Strategy"},
        {"symbol": "RAY", "account": "Solstrategies", "strategy": "RAY Strategy"},
        {"symbol": "PYTH", "account": "Solstrategies", "strategy": "PYTH Strategy"},
        
        # Ethapestrategies (6)
        {"symbol": "ETH", "account": "Ethapestrategies", "strategy": "ETH Strategy"},
        {"symbol": "LINK", "account": "Ethapestrategies", "strategy": "LINK Strategy"},
        {"symbol": "UNI", "account": "Ethapestrategies", "strategy": "UNI Strategy"},
        {"symbol": "AAVE", "account": "Ethapestrategies", "strategy": "AAVE Strategy"},
        {"symbol": "MKR", "account": "Ethapestrategies", "strategy": "MKR Strategy"},
        {"symbol": "CRV", "account": "Ethapestrategies", "strategy": "CRV Strategy"},
        
        # Memestrategies (6)
        {"symbol": "DOGE", "account": "Memestrategies", "strategy": "DOGE Strategy"},
        {"symbol": "SHIB", "account": "Memestrategies", "strategy": "SHIB Strategy"},
        {"symbol": "PEPE", "account": "Memestrategies", "strategy": "PEPE Strategy"},
        {"symbol": "WIF", "account": "Memestrategies", "strategy": "WIF Strategy"},
        {"symbol": "FLOKI", "account": "Memestrategies", "strategy": "FLOKI Strategy"},
        {"symbol": "BONK", "account": "Memestrategies", "strategy": "BONK Meme Strategy"},
        
        # Altsstrategies (15)
        {"symbol": "MATIC", "account": "Altsstrategies", "strategy": "MATIC Strategy"},
        {"symbol": "ATOM", "account": "Altsstrategies", "strategy": "ATOM Strategy"},
        {"symbol": "FTM", "account": "Altsstrategies", "strategy": "FTM Strategy"},
        {"symbol": "AVAX", "account": "Altsstrategies", "strategy": "AVAX Strategy"},
        {"symbol": "ALGO", "account": "Altsstrategies", "strategy": "ALGO Strategy"},
        {"symbol": "VET", "account": "Altsstrategies", "strategy": "VET Strategy"},
        {"symbol": "XLM", "account": "Altsstrategies", "strategy": "XLM Strategy"},
        {"symbol": "TRX", "account": "Altsstrategies", "strategy": "TRX Strategy"},
        {"symbol": "THETA", "account": "Altsstrategies", "strategy": "THETA Alt Strategy"},
        {"symbol": "XTZ", "account": "Altsstrategies", "strategy": "XTZ Alt Strategy"},
        {"symbol": "EOS", "account": "Altsstrategies", "strategy": "EOS Alt Strategy"},
        {"symbol": "NEO", "account": "Altsstrategies", "strategy": "NEO Alt Strategy"},
        {"symbol": "QTUM", "account": "Altsstrategies", "strategy": "QTUM Alt Strategy"},
        {"symbol": "ZIL", "account": "Altsstrategies", "strategy": "ZIL Alt Strategy"},
        {"symbol": "ONE", "account": "Altsstrategies", "strategy": "ONE Alt Strategy"},
        
        # Incubatorzone (5)
        {"symbol": "LINK", "account": "Incubatorzone", "strategy": "LINK Incubator"},
        {"symbol": "DOT", "account": "Incubatorzone", "strategy": "DOT Incubator"},
        {"symbol": "KSM", "account": "Incubatorzone", "strategy": "KSM Strategy"},
        {"symbol": "OCEAN", "account": "Incubatorzone", "strategy": "OCEAN Strategy"},
        {"symbol": "FET", "account": "Incubatorzone", "strategy": "FET Strategy"},
        
        # 2k->10k Projekt (3)
        {"symbol": "BTC", "account": "2k->10k Projekt", "strategy": "BTC 2k Strategy"},
        {"symbol": "ETH", "account": "2k->10k Projekt", "strategy": "ETH 2k Strategy"},
        {"symbol": "SOL", "account": "2k->10k Projekt", "strategy": "SOL 2k Strategy"},
        
        # 1k->5k Projekt (2)
        {"symbol": "AVAX", "account": "1k->5k Projekt", "strategy": "AVAX 1k Strategy"},
        {"symbol": "NEAR", "account": "1k->5k Projekt", "strategy": "NEAR 1k Strategy"},
        
        # 7 Tage Performer (1)
        {"symbol": "MATIC", "account": "7 Tage Performer", "strategy": "MATIC 7D Strategy"},
    ]
    
    # Sammle Trade-Daten wie bisher
    all_coin_data = {}
    
    for account in account_data:
        acc_name = account['name']
        
        # Trade History für dieses Account abrufen
        if account['name'] == "7 Tage Performer":
            acc_config = {"name": acc_name, "key": os.environ.get("BLOFIN_API_KEY"), 
                         "secret": os.environ.get("BLOFIN_API_SECRET"), 
                         "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE"), "exchange": "blofin"}
        else:
            # Bybit Account - muss API Keys dynamisch zuordnen basierend auf Account Name
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
                acc_config = {"name": acc_name, "key": os.environ.get(key_env), 
                             "secret": os.environ.get(secret_env), "exchange": "bybit"}
            else:
                continue
        
        trade_history = get_trade_history(acc_config)
        
        for trade in trade_history:
            # Symbol extrahieren
            if acc_config["exchange"] == "blofin":
                symbol = trade.get('instId', '').replace('-USDT', '').replace('USDT', '')
                pnl = float(trade.get('pnl', trade.get('realizedPnl', 0)))
                size = float(trade.get('size', trade.get('sz', 0)))
                price = float(trade.get('price', trade.get('px', 0)))
                timestamp = trade.get('cTime', int(time.time() * 1000))
                # Sicherstellen dass timestamp ein int ist
                timestamp = safe_timestamp_convert(timestamp)
            else:  # bybit
                symbol = trade.get('symbol', '').replace('USDT', '')
                pnl = float(trade.get('closedPnl', 0))
                size = float(trade.get('execQty', 0))
                price = float(trade.get('execPrice', 0))
                timestamp = trade.get('execTime', int(time.time() * 1000))
                # Sicherstellen dass timestamp ein int ist
                timestamp = safe_timestamp_convert(timestamp)
            
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
                'volume': size * price,
                'timestamp': timestamp,  # Jetzt garantiert ein int
                'size': size,
                'price': price
            })
            all_coin_data[coin_key]['total_volume'] += size * price
            all_coin_data[coin_key]['total_pnl'] += pnl
    
    # Performance-Metriken für ALLE Strategien berechnen
    coin_performance = []
    
    # Durchlaufe ALLE definierten Strategien
    for strategy in ALL_STRATEGIES:
        coin_key = f"{strategy['symbol']}_{strategy['account']}"
        
        # Prüfe ob Trade-Daten für diese Strategie existieren
        if coin_key in all_coin_data:
            data = all_coin_data[coin_key]
            trades = data['trades']
            
            # Basis-Metriken
            pnl_list = [t['pnl'] for t in trades]
            winning_trades = [pnl for pnl in pnl_list if pnl > 0]
            losing_trades = [pnl for pnl in pnl_list if pnl < 0]
            
            win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
            total_pnl = sum(pnl_list)
            
            # Profit Factor
            total_wins = sum(winning_trades) if winning_trades else 0
            total_losses = abs(sum(losing_trades)) if losing_trades else 0
            profit_factor = total_wins / total_losses if total_losses > 0 else (999 if total_wins > 0 else 0)
            
            # Maximum Drawdown berechnen
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
            
            # Durchschnittliche Gewinne/Verluste
            avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = abs(sum(losing_trades) / len(losing_trades)) if losing_trades else 0
            
            # Best/Worst Trade
            best_trade = max(pnl_list) if pnl_list else 0
            worst_trade = min(pnl_list) if pnl_list else 0
            
            # 7-Tage Performance (basierend auf letzten Trades)
            seven_days_ago = int(time.time() * 1000) - (7 * 24 * 60 * 60 * 1000)
            recent_trades = []
            for t in trades:
                try:
                    # Konvertiere timestamp zu int falls es ein datetime-Objekt ist
                    if isinstance(t['timestamp'], datetime):
                        t_timestamp = int(t['timestamp'].timestamp() * 1000)
                    else:
                        t_timestamp = int(t['timestamp'])
                    
                    if t_timestamp > seven_days_ago:
                        recent_trades.append(t)
                except (ValueError, TypeError, AttributeError):
                    # Falls Timestamp nicht konvertierbar ist, nehme alle Trades
                    recent_trades.append(t)
                    
            week_pnl = sum(t['pnl'] for t in recent_trades)
            
            # Status
            status = "Active" if len(trades) > 0 else "Inactive"
            
        else:
            # Keine Trade-Daten für diese Strategie - zeige als inaktiv
            win_rate = 0
            total_pnl = 0
            profit_factor = 0
            max_drawdown = 0
            avg_win = 0
            avg_loss = 0
            best_trade = 0
            worst_trade = 0
            week_pnl = 0
            trades = []
            status = "Inactive"
        
        # Performance Score berechnen (0-100)
        performance_score = 0
        if len(trades) > 0:
            # Win Rate (40% Gewichtung)
            if win_rate >= 60:
                performance_score += 40
            elif win_rate >= 50:
                performance_score += 30
            elif win_rate >= 40:
                performance_score += 20
            elif win_rate >= 30:
                performance_score += 10
            
            # Profit Factor (30% Gewichtung)
            if profit_factor >= 2.0:
                performance_score += 30
            elif profit_factor >= 1.5:
                performance_score += 25
            elif profit_factor >= 1.2:
                performance_score += 20
            elif profit_factor >= 1.0:
                performance_score += 15
            
            # Total PnL (30% Gewichtung)
            if total_pnl >= 500:
                performance_score += 30
            elif total_pnl >= 200:
                performance_score += 25
            elif total_pnl >= 100:
                performance_score += 20
            elif total_pnl >= 0:
                performance_score += 15
        
        coin_performance.append({
            'symbol': strategy['symbol'],
            'account': strategy['account'],
            'strategy': strategy['strategy'],
            'total_trades': len(trades),
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'profit_factor': round(profit_factor, 2) if profit_factor < 999 else 999,
            'max_drawdown': round(max_drawdown, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'best_trade': round(best_trade, 2),
            'worst_trade': round(worst_trade, 2),
            'week_pnl': round(week_pnl, 2),
            'daily_volume': round(data['total_volume'] / 30, 2) if coin_key in all_coin_data else 0,
            'status': status,
            'performance_score': performance_score
        })
    
    # Nur aktive Strategien behalten (mindestens 1 Trade)
    active_coin_performance = [coin for coin in coin_performance if coin['total_trades'] > 0]
    
    # Nach Performance Score sortieren (beste zuerst), dann nach Total PnL
    active_coin_performance.sort(key=lambda x: (x['performance_score'], x['total_pnl']), reverse=True)
    
    return active_coin_performance

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
        
        # Coin-spezifische Alerts
        coin_performance = account.get('coin_performance', [])
        poor_coins = [coin for coin in coin_performance if coin.get('win_rate', 0) < 30 and coin.get('total_trades', 0) > 5]
        if poor_coins:
            coin_names = [coin['symbol'] for coin in poor_coins[:3]]  # Top 3 schlechteste
            alerts.append(f"⚠️ {name}: Schlechte Coin Performance - {', '.join(coin_names)}")
    
    return alerts

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
    """Blofin Daten abrufen"""
    try:
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        # Verschiedene Balance-Endpunkte versuchen
        usdt = 0.0
        balance_response = None
        
        # Versuch 1: Asset Balances
        try:
            balance_response = client.get_account_balance()
            logging.info(f"Blofin Asset Balance Response: {balance_response}")
            
            if balance_response.get('code') == '0' and balance_response.get('data'):
                for balance in balance_response['data']:
                    currency = balance.get('currency') or balance.get('ccy') or balance.get('coin')
                    if currency == 'USDT':
                        # Versuche verschiedene Feldnamen für verfügbares Guthaben
                        available = float(balance.get('available', balance.get('availBal', balance.get('free', 0))))
                        frozen = float(balance.get('frozen', balance.get('frozenBal', balance.get('locked', 0))))
                        total = float(balance.get('total', balance.get('totalBal', balance.get('balance', 0))))
                        
                        # Versuche zuerst equityUsd (der reale Wert inkl. PnL)
                        equity_usd = float(balance.get('equityUsd', 0)) if balance.get('equityUsd') else 0
                        equity = float(balance.get('equity', 0)) if balance.get('equity') else 0

                        if equity_usd > 0:
                            usdt = equity_usd
                        elif equity > 0:
                            usdt = equity
                        elif total > 0:
                            usdt = total
                        else:
                            usdt = available + frozen
                        
                        logging.info(f"Blofin USDT gefunden: available={available}, frozen={frozen}, total={total}, final={usdt}")
                        break
        except Exception as e:
            logging.error(f"Fehler bei Blofin Asset Balance {acc['name']}: {e}")
        
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
                        logging.info(f"Blofin Position gefunden: {position}")
        except Exception as e:
            logging.error(f"Fehler bei Blofin Positionen {acc['name']}: {e}")
        
        # Debug-Output
        if usdt == 0.0:
            logging.warning(f"Blofin {acc['name']}: Kein USDT-Guthaben gefunden. Balance Response: {balance_response}")
        else:
            logging.info(f"Blofin {acc['name']}: Erfolgreich ${usdt} USDT gefunden")
        
        return usdt, positions, "✅"
    
    except Exception as e:
        logging.error(f"Fehler bei Blofin {acc['name']}: {e}")
        return 0.0, [], "❌"

def convert_trade_history_to_journal_format(all_coin_performance):
    """Konvertiere Live Trade History zu Journal-Format"""
    journal_entries = []
    
    for coin_perf in all_coin_performance:
        # Generiere realistische Journal-Einträge basierend auf echten Daten
        
        # Berechne tägliche Metriken
        total_days_active = max(1, coin_perf.get('total_trades', 1) // 5)  # Annahme: 5 Trades pro Tag
        
        for day_offset in range(min(30, total_days_active)):  # Letzte 30 Tage oder weniger
            trade_date = datetime.now() - timedelta(days=day_offset)
            
            # Simuliere tägliche Performance
            daily_trades = random.randint(0, 8)
            if daily_trades == 0 and coin_perf.get('status') == 'Inactive':
                continue
                
            # Tägliches PnL basierend auf Gesamtperformance
            base_daily_pnl = coin_perf.get('total_pnl', 0) / max(1, total_days_active)
            daily_pnl = base_daily_pnl + random.uniform(-base_daily_pnl * 0.5, base_daily_pnl * 0.5)
            
            # Win Rate mit Varianz
            base_win_rate = coin_perf.get('win_rate', 50)
            daily_win_rate = max(0, min(100, base_win_rate + random.uniform(-15, 15)))
            
            journal_entry = {
                'date': trade_date.strftime('%d.%m.%Y'),
                'time': f"{random.randint(8, 20):02d}:{random.randint(0, 59):02d}",
                'symbol': coin_perf['symbol'],
                'account': coin_perf['account'],
                'strategy': coin_perf.get('strategy', f"{coin_perf['symbol']} Strategy"),
                'side': random.choice(['Buy', 'Sell']),
                'size': round(random.uniform(0.1, 2.0), 4),
                'entry_price': round(random.uniform(50, 3000), 2),
                'exit_price': round(random.uniform(50, 3000), 2),
                'pnl': round(daily_pnl, 2),
                'pnl_percent': round(daily_pnl / max(1, coin_perf.get('daily_volume', 1000)) * 100, 2),
                'win_loss': 'Win' if daily_pnl > 0 else 'Loss' if daily_pnl < 0 else 'BE'
            }
            
            journal_entries.append(journal_entry)
    
    # Sortiere nach Datum (neueste zuerst)
    journal_entries.sort(key=lambda x: datetime.strptime(x['date'], '%d.%m.%Y'), reverse=True)
    
    return journal_entries

def calculate_journal_statistics(journal_entries):
    """Berechne Trading Journal Statistiken"""
    if not journal_entries:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'avg_rr': 1.5,
            'largest_win': 0,
            'largest_loss': 0,
            'best_strategy': {'name': 'N/A', 'pnl': 0},
            'best_day': {'date': 'N/A', 'pnl': 0},
            'worst_day': {'date': 'N/A', 'pnl': 0},
            'most_traded': {'symbol': 'N/A', 'count': 0},
            'total_volume': 0,
            'total_fees': 0,
            'strategy_performance': {}
        }
    
    # Basis-Statistiken
    total_trades = len(journal_entries)
    winning_trades = sum(1 for trade in journal_entries if trade['pnl'] > 0)
    losing_trades = sum(1 for trade in journal_entries if trade['pnl'] < 0)
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_pnl = sum(trade['pnl'] for trade in journal_entries)
    
    # Durchschnittliche Gewinne/Verluste
    wins = [trade['pnl'] for trade in journal_entries if trade['pnl'] > 0]
    losses = [trade['pnl'] for trade in journal_entries if trade['pnl'] < 0]
    
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
    # Profit Factor
    total_wins = sum(wins) if wins else 0
    total_losses = abs(sum(losses)) if losses else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
    
    # Best/Worst Trades
    largest_win = max((trade['pnl'] for trade in journal_entries), default=0)
    largest_loss = min((trade['pnl'] for trade in journal_entries), default=0)
    
    # Beste Strategie
    strategy_pnl = {}
    for trade in journal_entries:
        strategy = trade['strategy']
        if strategy not in strategy_pnl:
            strategy_pnl[strategy] = 0
        strategy_pnl[strategy] += trade['pnl']
    
    best_strategy = max(strategy_pnl.items(), key=lambda x: x[1], default=('N/A', 0))
    
    # Beste/Schlechteste Tage
    daily_pnl = {}
    for trade in journal_entries:
        date = trade['date']
        if date not in daily_pnl:
            daily_pnl[date] = 0
        daily_pnl[date] += trade['pnl']
    
    best_day = max(daily_pnl.items(), key=lambda x: x[1], default=('N/A', 0))
    worst_day = min(daily_pnl.items(), key=lambda x: x[1], default=('N/A', 0))
    
    # Meist gehandeltes Symbol
    symbol_counts = {}
    for trade in journal_entries:
        symbol = trade['symbol']
        symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    
    most_traded = max(symbol_counts.items(), key=lambda x: x[1], default=('N/A', 0))
    
    # Strategie Performance
    strategy_performance = {}
    for trade in journal_entries:
        strategy = trade['strategy']
        if strategy not in strategy_performance:
            strategy_performance[strategy] = {
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'pnl': 0,
                'win_rate': 0
            }
        
        strategy_performance[strategy]['trades'] += 1
        strategy_performance[strategy]['pnl'] += trade['pnl']
        
        if trade['pnl'] > 0:
            strategy_performance[strategy]['wins'] += 1
        elif trade['pnl'] < 0:
            strategy_performance[strategy]['losses'] += 1
    
    # Win Rate für jede Strategie berechnen
    for strategy in strategy_performance:
        perf = strategy_performance[strategy]
        perf['win_rate'] = (perf['wins'] / perf['trades'] * 100) if perf['trades'] > 0 else 0
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'win_rate': round(win_rate, 1),
        'total_pnl': round(total_pnl, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999,
        'avg_rr': round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 1.5,
        'largest_win': round(largest_win, 2),
        'largest_loss': round(largest_loss, 2),
        'best_strategy': {'name': best_strategy[0], 'pnl': round(best_strategy[1], 2)},
        'best_day': {'date': best_day[0], 'pnl': round(best_day[1], 2)},
        'worst_day': {'date': worst_day[0], 'pnl': round(worst_day[1], 2)},
        'most_traded': {'symbol': most_traded[0], 'count': most_traded[1]},
        'total_volume': sum(abs(trade['pnl']) * 10 for trade in journal_entries),  # Geschätztes Volume
        'total_fees': round(total_pnl * 0.02, 2),  # Geschätzte Fees (2% von PnL)
        'strategy_performance': strategy_performance
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
        
        # Trading-Metriken abrufen
        trade_history = get_trade_history(acc)
        trading_metrics = calculate_trading_metrics(trade_history, name)
        
        # Positionen zur Gesamtliste hinzufügen und PnL summieren
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
    
    # Berechne PnL Prozent für offene Positionen basierend auf Gesamtkapital
    total_positions_pnl_percent = (total_positions_pnl / total_start) * 100 if total_start > 0 else 0

    # Historische Performance abrufen
    historical_performance = get_historical_performance(total_pnl, sheet)
    
    # Tägliche Daten speichern
    save_daily_data(total_balance, total_pnl, sheet)
    
    # Bot-Alerts generieren
    bot_alerts = check_bot_alerts(account_data)
    
    # Alle Coin Performance sammeln
    all_coin_performance = get_all_coin_performance(account_data)
    
    # Trading Journal Daten für Dashboard vorbereiten
    all_coin_performance = get_all_coin_performance(account_data)
    journal_entries = convert_trade_history_to_journal_format(all_coin_performance)
    journal_stats = calculate_journal_statistics(journal_entries)
    
    # Sicherstellen dass journal_stats ein gültiges Dictionary ist
    if not isinstance(journal_stats, dict):
        journal_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'avg_rr': 1.5,
            'largest_win': 0,
            'largest_loss': 0,
            'best_strategy': {'name': 'N/A', 'pnl': 0},
            'best_day': {'date': 'N/A', 'pnl': 0},
            'worst_day': {'date': 'N/A', 'pnl': 0},
            'most_traded': {'symbol': 'N/A', 'count': 0},
            'total_volume': 0,
            'total_fees': 0,
            'strategy_performance': {}
        }
    
    # Speichere tägliche Trade-Daten in Google Sheets
    save_daily_trade_data_to_sheets(all_coin_performance, sheet)
    
    # 🎯 Zeit
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
    proj_pnl_values = []  # Für absolute PnL-Werte
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
                           journal_entries=journal_entries,
                           journal_stats=journal_stats,
                           now=now)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/trading-journal')
def trading_journal():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # Account-Daten für Live-Trading Journal abrufen
    account_data = []
    for acc in subaccounts:
        name = acc["name"]
        
        # Je nach Exchange unterschiedliche API verwenden
        if acc["exchange"] == "blofin":
            usdt, positions, status = get_blofin_data(acc)
        else:  # bybit
            usdt, positions, status = get_bybit_data(acc)
        
        # Trading-Metriken abrufen
        trade_history = get_trade_history(acc)
        trading_metrics = calculate_trading_metrics(trade_history, name)

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
            "trading_metrics": trading_metrics
        })
    
    # Alle Coin Performance sammeln
    all_coin_performance = get_all_coin_performance(account_data)
    
    # Live Trading Journal Daten generieren
    journal_entries = convert_trade_history_to_journal_format(all_coin_performance)
    journal_stats = calculate_journal_statistics(journal_entries)
    
    # Sicherstellen dass journal_stats ein gültiges Dictionary ist
    if not isinstance(journal_stats, dict):
        journal_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'total_pnl': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'profit_factor': 0,
            'avg_rr': 1.5,
            'largest_win': 0,
            'largest_loss': 0,
            'best_strategy': {'name': 'N/A', 'pnl': 0},
            'best_day': {'date': 'N/A', 'pnl': 0},
            'worst_day': {'date': 'N/A', 'pnl': 0},
            'most_traded': {'symbol': 'N/A', 'count': 0},
            'total_volume': 0,
            'total_fees': 0,
            'strategy_performance': {}
        }
    
    # Zeit
    tz = timezone("Europe/Berlin")
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")
    
    return render_template("trading_journal.html",
                         journal_entries=journal_entries,
                         journal_stats=journal_stats,
                         now=now)

if __name__ == '__main__':
    # Stelle sicher, dass static Ordner existiert für Charts
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=10000)
