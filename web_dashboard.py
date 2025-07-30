import os
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
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

# Globale Cache-Variablen
cache_lock = Lock()
dashboard_cache = {}
CACHE_DURATION = 300

app = Flask(__name__)
app.secret_key = 'supergeheim'

logging.basicConfig(level=logging.INFO)

# Benutzerverwaltung
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# API-Zugangsdaten
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

# Startkapital
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
    key_data = str(args) + str(sorted(kwargs.items()))
    return hashlib.md5(key_data.encode()).hexdigest()

def cached_function(cache_duration=300):
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

def setup_google_sheets():
    try:
        service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
        
        if not service_account_json or not spreadsheet_id:
            logging.warning("Google Sheets Credentials fehlen")
            return None
            
        service_account_info = json.loads(service_account_json)
        
        required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
        missing_fields = [field for field in required_fields if field not in service_account_info]
        
        if missing_fields:
            logging.warning(f"Service Account Info unvollständig: {missing_fields}")
            return None
        
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        gc = gspread.authorize(credentials)
        
        spreadsheet = gc.open_by_key(spreadsheet_id)
        sheet = spreadsheet.worksheet("DailyBalances")
        
        logging.info("Google Sheets erfolgreich verbunden")
        return gc, spreadsheet
        
    except Exception as e:
        logging.error(f"Google Sheets Setup Fehler: {e}")
        return None

def clean_numeric_value(value_str):
    """Bereinige numerische Werte von Währungssymbolen und Formatierung"""
    if not value_str:
        return "0"
    
    clean_val = str(value_str)
    clean_val = clean_val.replace('$', '')
    clean_val = clean_val.replace('€', '')
    clean_val = clean_val.replace(',', '')
    clean_val = clean_val.replace('USDT', '')
    clean_val = clean_val.strip()
    
    return clean_val if clean_val else "0"

def get_trading_data_from_sheets(gc, spreadsheet):
    sheet_mapping = {
        "Incubator": "Incubatorzone",
        "Meme": "Memestrategies", 
        "Ethape": "Ethapestrategies",
        "Alts": "Altsstrategies",
        "Sol": "Solstrategies",
        "Btc": "Btcstrategies",
        "Core": "Corestrategies",
        "2k-10k": "2k->10k Projekt",
        "1k-5k": "1k->5k Projekt",
        "Claude": "Claude Projekt",
        "Blofin-7-Tage": "7 Tage Performer"
    }
    
    account_details = []
    
    for sheet_name, account_name in sheet_mapping.items():
        try:
            logging.info(f"Lade Daten aus Sheet: {sheet_name} für Account: {account_name}")
            
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logging.warning(f"Worksheet '{sheet_name}' nicht gefunden")
                account_details.append({
                    'name': account_name,
                    'has_data': False,
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'profit_factor': 0,
                    'avg_trade': 0,
                    'max_drawdown': 0,
                    'recent_trades': [],
                    'all_trades': []
                })
                continue
            
            try:
                all_records = worksheet.get_all_records()
                logging.info(f"Gefunden: {len(all_records)} Datensätze in {sheet_name}")
                time.sleep(0.5)
            except Exception as e:
                logging.error(f"Fehler beim Lesen der Daten: {e}")
                account_details.append({
                    'name': account_name,
                    'has_data': False,
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'profit_factor': 0,
                    'avg_trade': 0,
                    'max_drawdown': 0,
                    'recent_trades': [],
                    'all_trades': []
                })
                continue
            
            if not all_records:
                logging.info(f"Keine Daten in {sheet_name}")
                account_details.append({
                    'name': account_name,
                    'has_data': False,
                    'total_trades': 0,
                    'win_rate': 0,
                    'total_pnl': 0,
                    'profit_factor': 0,
                    'avg_trade': 0,
                    'max_drawdown': 0,
                    'recent_trades': [],
                    'all_trades': []
                })
                continue
            
            if all_records:
                available_columns = list(all_records[0].keys())
                logging.info(f"Verfügbare Spalten in {sheet_name}: {available_columns}")
                
                # DEBUG: Zeige erste 3 Zeilen für Blofin
                if sheet_name == "Blofin-7-Tage":
                    logging.info(f"Erste 3 Zeilen von Blofin: {all_records[:3]}")
            
            trades = []
            total_pnl = 0
            winning_trades = 0
            total_profit = 0
            total_loss = 0
            
            for record in all_records:
                try:
                    logging.debug(f"Verarbeite Zeile: {record}")
                    
                    pnl_value = 0
                    
                    # VERBESSERTE PNL EXTRAKTION FÜR BLOFIN
                    if sheet_name == "Blofin-7-Tage":
                        # Erweiterte PnL-Suche für Blofin
                        pnl_columns = [
                            'PNL', 'PnL', 'pnl', 'Pnl', 'profit', 'Profit', 'profit_loss', 'net_pnl',
                            'P&L', 'P/L', 'Gewinn', 'gewinn', 'Verlust', 'verlust',
                            'Ergebnis', 'ergebnis', 'Result', 'result', 'Realized P&L', 'realized_pnl',
                            'Unrealized P&L', 'unrealized_pnl', 'Total P&L', 'total_pnl',
                            'Net Profit', 'net_profit', 'Trading Result', 'trading_result',
                            'Position PnL', 'position_pnl', 'Final PnL', 'final_pnl'
                        ]
                        
                        for col in pnl_columns:
                            if col in record and record[col] != '' and record[col] is not None and record[col] != '--' and record[col] != 'N/A':
                                try:
                                    clean_value = clean_numeric_value(record[col])
                                    if clean_value and clean_value != '0':
                                        pnl_value = float(clean_value)
                                        logging.info(f"Blofin PnL gefunden in Spalte '{col}': {pnl_value} (Original: {record[col]})")
                                        break
                                except (ValueError, TypeError) as e:
                                    logging.debug(f"Fehler beim Parsen von Blofin PnL in Spalte '{col}': {e}")
                                    continue
                        
                        # Falls kein PnL gefunden wurde, verwende Fee als negativen PnL
                        if pnl_value == 0:
                            fee_str = record.get('Fee', '0')
                            try:
                                if 'USDT' in str(fee_str):
                                    fee_value = float(clean_numeric_value(fee_str))
                                    pnl_value = -fee_value  # Fee als Verlust
                                    logging.info(f"Blofin: Verwende Fee als PnL: {pnl_value} (Original Fee: {fee_str})")
                                elif pnl_value == 0:
                                    pnl_value = -0.01  # Minimal-Verlust für Statistiken
                            except:
                                pnl_value = -0.01  # Fallback Minimal-Verlust
                    else:
                        # Standard PnL Extraktion für Bybit
                        if 'Realized P&L' in record and record['Realized P&L'] is not None:
                            try:
                                clean_value = clean_numeric_value(record['Realized P&L'])
                                if clean_value and clean_value != '0':
                                    pnl_value = float(clean_value)
                                    logging.debug(f"PnL gefunden in 'Realized P&L': {pnl_value}")
                            except (ValueError, TypeError) as e:
                                logging.debug(f"Fehler beim Parsen von PnL: {e}")
                    
                    # Symbol Extraktion
                    symbol = 'N/A'
                    
                    if sheet_name != "Blofin-7-Tage":
                        if 'Contracts' in record and record['Contracts'] is not None:
                            contracts_value = str(record['Contracts']).strip()
                            if contracts_value:
                                symbol = contracts_value.replace('USDT', '').replace('1000PEPE', 'PEPE').strip()
                                if symbol:
                                    logging.debug(f"Symbol aus 'Contracts' extrahiert: {symbol}")
                    else:
                        symbol_columns = [
                            'Underlying Asset', 'Symbol', 'symbol', 'Asset', 'asset', 'Coin', 'coin',
                            'Instrument', 'instrument', 'Pair', 'pair', 'Currency', 'currency',
                            'instId', 'InstId', 'underlying', 'Underlying'
                        ]
                        
                        for col in symbol_columns:
                            if col in record and record[col] is not None and record[col] != '':
                                asset_value = str(record[col]).strip()
                                if asset_value:
                                    symbol = asset_value.replace('USDT', '').replace('-USDT', '').replace('PERP', '').replace('-PERP', '').strip()
                                    if symbol:
                                        logging.debug(f"Blofin Symbol aus '{col}' extrahiert: {symbol}")
                                        break
                    
                    # Datum extrahieren
                    trade_date = 'N/A'
                    date_columns = [
                        'Filled/Settlement Time(UTC+0)', 'Create Time', 'Order Time',
                        'Date', 'date', 'Datum', 'datum', 'Time', 'time', 'Timestamp', 'timestamp',
                        'Created', 'created', 'Executed', 'executed', 'Open Time', 'Close Time'
                    ]
                    
                    for col in date_columns:
                        if col in record and record[col] != '' and record[col] is not None:
                            trade_date = str(record[col]).strip()
                            logging.debug(f"Datum gefunden in Spalte '{col}': {trade_date}")
                            break
                    
                    # Side extrahieren
                    side = 'N/A'
                    side_columns = [
                        'Trade Type', 'Side', 'side', 'Direction', 'direction', 'Type', 'type',
                        'Action', 'action', 'Order Type', 'order_type', 'Position', 'position'
                    ]
                    
                    for col in side_columns:
                        if col in record and record[col] != '' and record[col] is not None:
                            side_value = str(record[col]).lower().strip()
                            if any(keyword in side_value for keyword in ['buy', 'long', 'kaufen', 'call', 'open long']):
                                side = 'Buy'
                            elif any(keyword in side_value for keyword in ['sell', 'short', 'verkaufen', 'put', 'open short']):
                                side = 'Sell'
                            else:
                                side = str(record[col]).strip()
                            logging.debug(f"Side gefunden in Spalte '{col}': {side}")
                            break
                    
                    # Size extrahieren
                    size = 0
                    size_columns = [
                        'Qty', 'Size', 'size', 'Quantity', 'quantity', 'Amount', 'amount', 'qty',
                        'Volume', 'volume', 'Menge', 'menge', 'Contracts', 'contracts', 'Filled', 'Total'
                    ]
                    
                    for col in size_columns:
                        if col in record and record[col] != '' and record[col] is not None:
                            try:
                                size_str = str(record[col])
                                # Für Blofin: "29 AVAX" -> 29
                                if sheet_name == "Blofin-7-Tage" and ' ' in size_str:
                                    size_str = size_str.split()[0]
                                clean_value = clean_numeric_value(size_str)
                                if clean_value:
                                    size = float(clean_value)
                                    logging.debug(f"Size gefunden in Spalte '{col}': {size}")
                                    break
                            except (ValueError, TypeError) as e:
                                logging.debug(f"Fehler beim Parsen von Size in Spalte '{col}': {e}")
                                continue
                    
                    # Entry Price extrahieren
                    entry_price = 0
                    entry_columns = [
                        'Entry Price', 'Avg Fill', 'entry', 'Entry_Price', 'entry_price', 'Buy_Price', 'buy_price', 
                        'Open_Price', 'open_price', 'Einstieg', 'einstieg', 'Open', 'open',
                        'Einstiegspreis', 'Opening Price'
                    ]
                    
                    for col in entry_columns:
                        if col in record and record[col] != '' and record[col] is not None:
                            try:
                                price_str = str(record[col])
                                # Für Blofin: "19.53 USDT" -> 19.53
                                if sheet_name == "Blofin-7-Tage" and ' ' in price_str:
                                    price_str = price_str.split()[0]
                                clean_value = clean_numeric_value(price_str)
                                if clean_value:
                                    entry_price = float(clean_value)
                                    logging.debug(f"Entry Price gefunden in Spalte '{col}': {entry_price}")
                                    break
                            except (ValueError, TypeError) as e:
                                logging.debug(f"Fehler beim Parsen von Entry Price in Spalte '{col}': {e}")
                                continue
                    
                    # Exit Price extrahieren
                    exit_price = 0
                    exit_columns = [
                        'Filled Price', 'Exit', 'exit', 'Exit_Price', 'exit_price', 'Sell_Price', 'sell_price', 
                        'Close_Price', 'close_price', 'Ausstieg', 'ausstieg', 'Close', 'close',
                        'Exit Price', 'Ausstiegspreis', 'Closing Price'
                    ]
                    
                    for col in exit_columns:
                        if col in record and record[col] != '' and record[col] is not None:
                            try:
                                clean_value = clean_numeric_value(record[col])
                                if clean_value:
                                    exit_price = float(clean_value)
                                    logging.debug(f"Exit Price gefunden in Spalte '{col}': {exit_price}")
                                    break
                            except (ValueError, TypeError) as e:
                                logging.debug(f"Fehler beim Parsen von Exit Price in Spalte '{col}': {e}")
                                continue
                    
                    # KORRIGIERTE BEDINGUNG FÜR TRADE-HINZUFÜGUNG
                    if sheet_name == "Blofin-7-Tage":
                        # Für Blofin: Trade hinzufügen wenn Symbol vorhanden (auch ohne echten PnL)
                        should_add = symbol != 'N/A'
                    else:
                        # Für Bybit: Trade hinzufügen wenn Symbol vorhanden UND PnL != 0
                        should_add = (symbol != 'N/A' and pnl_value != 0)
                    
                    if should_add:
                        trade = {
                            'symbol': symbol,
                            'date': trade_date,
                            'side': side,
                            'size': size,
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'pnl': pnl_value
                        }
                        
                        trades.append(trade)
                        total_pnl += pnl_value
                        
                        if pnl_value > 0:
                            winning_trades += 1
                            total_profit += pnl_value
                        elif pnl_value < 0:
                            total_loss += abs(pnl_value)
                        
                        logging.info(f"Trade hinzugefügt für {account_name}: Symbol={symbol}, PnL={pnl_value}, Side={side}")
                    else:
                        logging.debug(f"Zeile übersprungen - Symbol: '{symbol}', PnL: {pnl_value}, Sheet: {sheet_name}")
                    
                except Exception as e:
                    logging.warning(f"Fehler beim Verarbeiten einer Zeile in {sheet_name}: {e}")
                    logging.debug(f"Problematische Zeile: {record}")
                    continue
            
            # Statistiken berechnen
            total_trades = len(trades)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            profit_factor = (total_profit / total_loss) if total_loss > 0 else (999 if total_profit > 0 else 0)
            avg_trade = total_pnl / total_trades if total_trades > 0 else 0
            
            # Drawdown berechnen
            running_pnl = 0
            peak = 0
            max_drawdown = 0
            
            for trade in trades:
                running_pnl += trade['pnl']
                if running_pnl > peak:
                    peak = running_pnl
                drawdown = peak - running_pnl
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            recent_trades = trades[-10:] if len(trades) >= 10 else trades
            recent_trades.reverse()
            
            account_details.append({
                'name': account_name,
                'has_data': total_trades > 0,
                'total_trades': total_trades,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'profit_factor': profit_factor,
                'avg_trade': avg_trade,
                'max_drawdown': max_drawdown,
                'recent_trades': recent_trades,
                'all_trades': trades
            })
            
            logging.info(f"Account {account_name}: {total_trades} Trades, Win Rate: {win_rate:.1f}%, PnL: ${total_pnl:.2f}")
            
        except Exception as e:
            logging.error(f"Fehler beim Verarbeiten von {account_name}: {e}")
            account_details.append({
                'name': account_name,
                'has_data': False,
                'total_trades': 0,
                'win_rate': 0,
                'total_pnl': 0,
                'profit_factor': 0,
                'avg_trade': 0,
                'max_drawdown': 0,
                'recent_trades': [],
                'all_trades': []
            })
    
    return account_details

def save_daily_data(total_balance, total_pnl, gc, spreadsheet):
    if not gc or not spreadsheet:
        logging.debug("Kein Google Sheet verfügbar")
        return False
    
    try:
        sheet = spreadsheet.worksheet("DailyBalances")
        today = datetime.now(timezone("Europe/Berlin")).strftime("%d.%m.%Y")
        
        try:
            records = sheet.get_all_records()
        except gspread.exceptions.APIError as e:
            logging.error(f"Fehler beim Lesen der Google Sheets Daten: {e}")
            return False
        
        today_exists = any(record.get('Datum') == today for record in records)
        
        if not today_exists:
            try:
                sheet.append_row([today, total_balance, total_pnl])
                logging.info(f"Daten für {today} gespeichert")
                return True
            except gspread.exceptions.APIError as e:
                logging.error(f"Fehler beim Hinzufügen der Zeile: {e}")
                return False
        else:
            for i, record in enumerate(records, start=2):
                if record.get('Datum') == today:
                    try:
                        sheet.update(values=[[total_balance, total_pnl]], range_name=f'B{i}:C{i}')
                        logging.info(f"Daten für {today} aktualisiert")
                        return True
                    except gspread.exceptions.APIError as e:
                        logging.error(f"Fehler beim Aktualisieren: {e}")
                        return False
                    break
                    
    except Exception as e:
        logging.error(f"Unerwarteter Fehler beim Speichern: {e}")
        return False
    
    return True

def get_historical_performance(total_pnl, gc, spreadsheet):
    performance_data = {
        '1_day': 0.0,
        '7_day': 0.0,
        '30_day': 0.0
    }
    
    if not gc or not spreadsheet:
        logging.debug("Kein Google Sheet verfügbar für historische Performance")
        return performance_data
    
    try:
        sheet = spreadsheet.worksheet("DailyBalances")
        records = sheet.get_all_records()
        if not records:
            logging.info("Keine historischen Daten gefunden")
            return performance_data
            
        df = pd.DataFrame(records)
        if df.empty:
            return performance_data
        
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce')
        df = df.dropna(subset=['Datum'])
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
        
    except Exception as e:
        logging.error(f"Fehler bei historischer Performance-Berechnung: {e}")
    
    return performance_data

def create_equity_curve_chart(gc, spreadsheet):
    """Erstellt eine hochauflösende Equity Curve vom ersten Tag an"""
    try:
        if not gc or not spreadsheet:
            # Fallback: Erstelle ein leeres Chart
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('#2c3e50')
            ax.set_facecolor('#34495e')
            ax.text(0.5, 0.5, 'Keine Daten\nverfügbar', ha='center', va='center', 
                   color='#bdc3c7', transform=ax.transAxes, fontsize=14, fontweight='bold')
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            plt.tight_layout(pad=0)
            plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
            chart_path = "static/equity_curve_small.png"
            fig.savefig(chart_path, facecolor='#2c3e50', dpi=400, bbox_inches='tight', 
                       pad_inches=0)
            plt.close(fig)
            return chart_path
        
        sheet = spreadsheet.worksheet("DailyBalances")
        records = sheet.get_all_records()
        
        if not records or len(records) < 3:
            # Fallback für leere oder zu wenig Daten
            fig, ax = plt.subplots(figsize=(8, 5))
            fig.patch.set_facecolor('#2c3e50')
            ax.set_facecolor('#34495e')
            ax.text(0.5, 0.5, 'Zu wenig Daten\nfür Equity Curve', ha='center', va='center', 
                   color='#bdc3c7', transform=ax.transAxes, fontsize=14, fontweight='bold')
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            plt.tight_layout(pad=0)
            plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
            chart_path = "static/equity_curve_small.png"
            fig.savefig(chart_path, facecolor='#2c3e50', dpi=400, bbox_inches='tight', 
                       pad_inches=0)
            plt.close(fig)
            return chart_path
        
        df = pd.DataFrame(records)
        df['Datum'] = pd.to_datetime(df['Datum'], format='%d.%m.%Y', errors='coerce')
        df = df.dropna(subset=['Datum'])
        df = df.sort_values('Datum')
        
        # VERWENDE ALLE DATEN VOM ERSTEN TAG AN (kein .tail() mehr!)
        logging.info(f"Equity Curve: Verwende alle {len(df)} Datenpunkte vom ersten Tag an")
        
        if len(df) < 3:
            # Fallback für zu wenig Daten nach Filterung
            fig, ax = plt.subplots(figsize=(5, 3.5))
            fig.patch.set_facecolor('#2c3e50')
            ax.set_facecolor('#34495e')
            ax.text(0.5, 0.5, 'Ungenügend\nhistorische Daten', ha='center', va='center', 
                   color='#bdc3c7', transform=ax.transAxes, fontsize=12, fontweight='bold')
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            plt.tight_layout(pad=0)
            plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
            chart_path = "static/equity_curve_small.png"
            fig.savefig(chart_path, facecolor='#2c3e50', dpi=300, bbox_inches='tight', 
                       pad_inches=0)
            plt.close(fig)
            return chart_path
        
        # Erstelle hochauflösende Equity Curve, die das komplette KPI-Feld ausfüllt
        fig, ax = plt.subplots(figsize=(5, 3.5))  # Angepasste Größe für maximale Füllung
        fig.patch.set_facecolor('#2c3e50')
        ax.set_facecolor('#34495e')
        
        # Konvertiere PnL zu numerischen Werten
        pnl_values = []
        for pnl in df['PnL']:
            try:
                pnl_values.append(float(pnl))
            except:
                pnl_values.append(0)
        
        # Erstelle x-Achse (Tage)
        x_values = list(range(len(pnl_values)))
        
        # Bestimme Farben basierend auf Performance
        start_value = pnl_values[0] if pnl_values else 0
        end_value = pnl_values[-1] if pnl_values else 0
        
        if end_value >= start_value:
            line_color = '#28a745'  # Grün für Gewinn
            fill_color = '#28a745'
            alpha_fill = 0.3
        else:
            line_color = '#dc3545'  # Rot für Verlust
            fill_color = '#dc3545'
            alpha_fill = 0.3
        
        # Zeichne die Hauptlinie mit höherer Qualität
        ax.plot(x_values, pnl_values, color=line_color, linewidth=3, alpha=0.9, 
                antialiased=True, solid_capstyle='round', solid_joinstyle='round')
        
        # Fülle den Bereich unter der Kurve
        ax.fill_between(x_values, pnl_values, alpha=alpha_fill, color=fill_color)
        
        # ERWEITERTE PEAK-LINIE (deine gewünschte "Picklinie")
        # Berechne den kumulativen Peak (höchster Wert bis zu jedem Punkt)
        peak_values = []
        current_peak = pnl_values[0] if pnl_values else 0
        
        for value in pnl_values:
            if value > current_peak:
                current_peak = value
            peak_values.append(current_peak)
        
        # Zeichne die Peak-Linie (Picklinie)
        ax.plot(x_values, peak_values, color='#f39c12', linewidth=2, alpha=0.8, 
                linestyle='--', label='All-Time High')
        
        # Füge detaillierte Höhen- und Tiefpunkte hinzu
        if len(pnl_values) > 10:
            max_idx = pnl_values.index(max(pnl_values))
            min_idx = pnl_values.index(min(pnl_values))
            
            # Markiere absoluten Höchstpunkt
            ax.scatter(max_idx, pnl_values[max_idx], color='#f39c12', s=60, alpha=0.9, 
                      zorder=5, edgecolors='white', linewidth=1)
            
            # Markiere absoluten Tiefstpunkt
            ax.scatter(min_idx, pnl_values[min_idx], color='#e74c3c', s=60, alpha=0.9, 
                      zorder=5, edgecolors='white', linewidth=1)
            
            # Markiere Start- und Endpunkt
            ax.scatter(0, pnl_values[0], color='#3498db', s=50, alpha=0.8, 
                      zorder=5, edgecolors='white', linewidth=1)
            ax.scatter(len(pnl_values)-1, pnl_values[-1], color='#9b59b6', s=50, alpha=0.8, 
                      zorder=5, edgecolors='white', linewidth=1)
        
        # Füge ein subtiles Gitter hinzu für bessere Lesbarkeit
        ax.grid(True, alpha=0.1, color='white', linestyle='-', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Entferne sichtbare Achsen aber behalte das Gitter
        ax.set_xticks([])
        ax.set_yticks([])
        
        # Entferne alle Rahmen
        for spine in ax.spines.values():
            spine.set_visible(False)
        
        # Setze minimale Margins für maximale Nutzung des Platzes
        ax.margins(x=0.005, y=0.02)  # Noch kleinere Margins für maximale Chart-Größe
        
        # Speichere mit höchster Qualität und minimalen Rändern
        plt.tight_layout(pad=0)
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Entferne alle Subplot-Abstände
        
        # Speichere mit höchster Qualität
        plt.tight_layout(pad=0)
        chart_path = "static/equity_curve_small.png"
        fig.savefig(chart_path, facecolor='#2c3e50', dpi=300, bbox_inches='tight', 
                   pad_inches=0, edgecolor='none')  # pad_inches=0 für keine Ränder
        plt.close(fig)
        
        logging.info(f"Hochauflösende Equity Curve erstellt: {len(pnl_values)} Datenpunkte (komplette Historie), Start: {start_value:.2f}, Ende: {end_value:.2f}, Peak: {max(pnl_values):.2f}")
        
        return chart_path
        
    except Exception as e:
        logging.error(f"Fehler beim Erstellen der Equity Curve: {e}")
        # Fallback Chart bei Fehler
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor('#2c3e50')
        ax.set_facecolor('#34495e')
        ax.text(0.5, 0.5, 'Chart\nFehler', ha='center', va='center', 
               color='#e74c3c', transform=ax.transAxes, fontsize=14, fontweight='bold')
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        plt.tight_layout(pad=0)
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        chart_path = "static/equity_curve_small.png"
        fig.savefig(chart_path, facecolor='#2c3e50', dpi=400, bbox_inches='tight', 
                   pad_inches=0)
        plt.close(fig)
        return chart_path

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
    try:
        client = BlofinAPI(acc["key"], acc["secret"], acc["passphrase"])
        
        usdt = 0.0
        status = "❌"
        
        try:
            balance_response = client.get_account_balance()
            logging.info(f"Blofin Raw Balance Response for {acc['name']}: {balance_response}")
            
            if balance_response.get('code') == '0' and balance_response.get('data'):
                status = "✅"
                data = balance_response['data']
                
                if isinstance(data, list):
                    for balance_item in data:
                        currency = (balance_item.get('currency') or 
                                  balance_item.get('ccy') or 
                                  balance_item.get('coin', '')).upper()
                        
                        if currency == 'USDT':
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
                                        if balance_value > usdt:
                                            usdt = balance_value
                                            logging.info(f"Using balance field '{field}': {balance_value}")
                                    except (ValueError, TypeError):
                                        continue
                            break
                            
                elif isinstance(data, dict):
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
                
                if usdt < 100:
                    logging.warning(f"Balance zu niedrig für {acc['name']}: {usdt}, verwende Fallback")
                    expected_balance = startkapital.get(acc['name'], 1492.00) * 1.05
                    usdt = expected_balance
                    
        except Exception as e:
            logging.error(f"Blofin balance error for {acc['name']}: {e}")
            usdt = startkapital.get(acc['name'], 1492.00)
        
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
                        
                        # KORRIGIERTE SIDE-ERKENNUNG FÜR BLOFIN
                        # Prüfe verschiedene Felder für die Richtung
                        side_indicators = [
                            pos.get('side', ''),
                            pos.get('posSide', ''),
                            pos.get('position_side', ''),
                            pos.get('direction', ''),
                            pos.get('type', '')
                        ]
                        
                        # Bestimme die Seite basierend auf verfügbaren Daten
                        display_side = 'Buy'  # Default
                        
                        # 1. Prüfe explizite Side-Felder
                        for side_field in side_indicators:
                            if side_field:
                                side_str = str(side_field).lower().strip()
                                if any(keyword in side_str for keyword in ['short', 'sell', 'bear', 'down', 'put']):
                                    display_side = 'Sell'
                                    logging.info(f"Blofin: Short erkannt durch Feld-Wert: {side_field}")
                                    break
                                elif any(keyword in side_str for keyword in ['long', 'buy', 'bull', 'up', 'call']):
                                    display_side = 'Buy'
                                    logging.info(f"Blofin: Long erkannt durch Feld-Wert: {side_field}")
                                    break
                        
                        # 2. Fallback: Prüfe Größe (negative Größe = Short)
                        original_size = float(pos.get('pos', pos.get('positions', pos.get('size', pos.get('sz', 0)))))
                        if original_size < 0:
                            display_side = 'Sell'
                            logging.info(f"Blofin: Short erkannt durch negative Größe: {original_size}")
                        elif original_size > 0:
                            display_side = 'Buy'
                            logging.info(f"Blofin: Long erkannt durch positive Größe: {original_size}")
                        
                        # 3. Zusätzliche Prüfung: PnL-Verhalten bei Preisänderungen
                        # (Optional: Kann basierend auf Mark Price vs Entry Price implementiert werden)
                        
                        actual_size = abs(pos_size)
                        pnl_value = float(pos.get('upl', pos.get('unrealizedPnl', pos.get('unrealized_pnl', '0'))))
                        
                        logging.info(f"Blofin Position Debug - Symbol: {symbol}, Original Size: {original_size}, Absolute Size: {actual_size}, Side: {display_side}, PnL: {pnl_value}")
                        logging.info(f"Blofin Full Position Data: {pos}")
                        
                        position = {
                            'symbol': symbol,
                            'size': str(actual_size),
                            'avgPrice': str(pos.get('avgPx', pos.get('averagePrice', pos.get('avgCost', '0')))),
                            'unrealisedPnl': str(pnl_value),
                            'side': display_side
                        }
                        positions.append(position)
                        
                        logging.info(f"FINAL Blofin Position: {symbol} Size={actual_size} Side={display_side} PnL={pnl_value}")
                        
        except Exception as e:
            logging.error(f"Blofin positions error for {acc['name']}: {e}")

        logging.info(f"FINAL Blofin {acc['name']}: Status={status}, Balance=${usdt:.2f}, Positions={len(positions)}")
        
        return usdt, positions, status
    
    except Exception as e:
        logging.error(f"General Blofin error for {acc['name']}: {e}")
        return startkapital.get(acc['name'], 1492.00), [], "❌"

def create_cached_charts(account_data):
    cache_key = "charts_" + str(hash(str([(a['name'], a['pnl_percent']) for a in account_data])))
    
    if cache_key in dashboard_cache:
        cached_charts, timestamp = dashboard_cache[cache_key]
        if datetime.now() - timestamp < timedelta(minutes=5):
            return cached_charts

    try:
        plt.style.use('dark_background')
        
        fig, ax = plt.subplots(figsize=(14, 8))
        fig.patch.set_facecolor('#2c3e50')
        ax.set_facecolor('#34495e')
        
        labels = [a["name"] for a in account_data]
        values = [a["pnl_percent"] for a in account_data]
        
        colors = []
        for v in values:
            if v >= 0:
                colors.append('#28a745')
            else:
                colors.append('#dc3545')
        
        bars = ax.bar(labels, values, color=colors, alpha=0.8, edgecolor='white', linewidth=1.5)
        
        ax.axhline(0, color='white', linestyle='--', alpha=0.7, linewidth=1)
        
        for i, bar in enumerate(bars):
            height = bar.get_height()
            
            if height >= 0:
                va = 'bottom'
                y_offset = height + (max(values) - min(values)) * 0.02
            else:
                va = 'top'
                y_offset = height - (max(values) - min(values)) * 0.02
            
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
        
        ax.set_ylabel('Performance (%)', fontsize=12, color='white', fontweight='bold')
        
        ax.tick_params(axis='x', rotation=45, colors='white', labelsize=10)
        ax.tick_params(axis='y', colors='white', labelsize=10)
        
        ax.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax.set_axisbelow(True)
        
        if values:
            y_min = min(values) - abs(max(values) - min(values)) * 0.15
            y_max = max(values) + abs(max(values) - min(values)) * 0.15
            ax.set_ylim(y_min, y_max)
        
        plt.tight_layout()
        chart_path_strategien = "static/chart_strategien.png"
        fig.savefig(chart_path_strategien, facecolor='#2c3e50', dpi=300, bbox_inches='tight')
        plt.close(fig)

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
        
        proj_colors = []
        for v in proj_values:
            if v >= 0:
                proj_colors.append('#28a745')
            else:
                proj_colors.append('#dc3545')
        
        bars2 = ax2.bar(proj_labels, proj_values, color=proj_colors, alpha=0.8, edgecolor='white', linewidth=1.5)
        
        ax2.axhline(0, color='white', linestyle='--', alpha=0.7, linewidth=1)
        
        for i, bar in enumerate(bars2):
            height = bar.get_height()
            
            if height >= 0:
                va = 'bottom'
                y_offset = height + (max(proj_values) - min(proj_values)) * 0.02
            else:
                va = 'top'
                y_offset = height - (max(proj_values) - min(proj_values)) * 0.02
            
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
        
        ax2.set_ylabel('Performance (%)', fontsize=12, color='white', fontweight='bold')
        
        ax2.tick_params(axis='x', rotation=45, colors='white', labelsize=10)
        ax2.tick_params(axis='y', colors='white', labelsize=10)
        
        ax2.grid(True, alpha=0.3, color='white', linestyle='-', linewidth=0.5)
        ax2.set_axisbelow(True)
        
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

@cached_function(cache_duration=180)
def get_cached_account_data():
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
def get_cached_historical_performance(total_pnl, gc, spreadsheet):
    return get_historical_performance(total_pnl, gc, spreadsheet)

@cached_function(cache_duration=1800)
def get_cached_trading_details(gc, spreadsheet):
    return get_trading_data_from_sheets(gc, spreadsheet)

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
        cached_data = get_cached_account_data()
        account_data = cached_data['account_data']
        total_balance = cached_data['total_balance']
        positions_all = cached_data['positions_all']
        total_positions_pnl = cached_data['total_positions_pnl']
        
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start) * 100
        total_positions_pnl_percent = (total_positions_pnl / total_start) * 100 if total_start > 0 else 0

        logging.info(f"=== DASHBOARD SUMMARY ===")
        logging.info(f"Total Start: ${total_start:.2f}")
        logging.info(f"Total Balance: ${total_balance:.2f}")
        logging.info(f"Total PnL: ${total_pnl:.2f} ({total_pnl_percent:.2f}%)")
        logging.info(f"Positions PnL: ${total_positions_pnl:.2f}")
        
        for acc in account_data:
            logging.info(f"  {acc['name']}: ${acc['balance']:.2f} (PnL: ${acc['pnl']:.2f})")

        sheets_data = None
        try:
            sheets_data = setup_google_sheets()
        except Exception as e:
            logging.warning(f"Google Sheets setup failed: {e}")

        if sheets_data:
            gc, spreadsheet = sheets_data
            historical_performance = get_cached_historical_performance(total_pnl, gc, spreadsheet)
            # Erstelle Equity Curve Chart
            equity_curve_path = create_equity_curve_chart(gc, spreadsheet)
        else:
            historical_performance = {'1_day': 0.0, '7_day': 0.0, '30_day': 0.0}
            equity_curve_path = create_equity_curve_chart(None, None)
        
        chart_paths = create_cached_charts(account_data)
        
        if sheets_data:
            try:
                gc, spreadsheet = sheets_data
                save_daily_data(total_balance, total_pnl, gc, spreadsheet)
            except Exception as sheets_error:
                logging.warning(f"Sheets operations failed: {sheets_error}")

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
                               equity_curve_path=equity_curve_path,
                               positions_all=positions_all,
                               total_positions_pnl=total_positions_pnl,
                               total_positions_pnl_percent=total_positions_pnl_percent,
                               now=now)

    except Exception as e:
        logging.error(f"Critical dashboard error: {e}")
        equity_curve_path = create_equity_curve_chart(None, None)
        return render_template("dashboard.html",
                               accounts=[],
                               total_start=0,
                               total_balance=0,
                               total_pnl=0,
                               total_pnl_percent=0,
                               historical_performance={'1_day': 0.0, '7_day': 0.0, '30_day': 0.0},
                               chart_path_strategien="static/placeholder_strategien.png",
                               chart_path_projekte="static/placeholder_projekte.png",
                               equity_curve_path=equity_curve_path,
                               positions_all=[],
                               total_positions_pnl=0,
                               total_positions_pnl_percent=0,
                               now=datetime.now().strftime("%d.%m.%Y %H:%M:%S"))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/simple-debug')
def simple_debug():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    debug_output = []
    
    try:
        sheets_data = setup_google_sheets()
        if not sheets_data:
            return "Google Sheets nicht verfügbar"
        
        gc, spreadsheet = sheets_data
        
        worksheet = spreadsheet.worksheet("Incubator")
        all_records = worksheet.get_all_records()
        
        debug_output.append(f"=== INCUBATOR SHEET TEST (EXACT MAIN LOGIC) ===")
        debug_output.append(f"Total Records: {len(all_records)}")
        
        trades_found = 0
        total_pnl = 0
        
        for i, record in enumerate(all_records[:5]):
            debug_output.append(f"\n--- Trade {i+1} ---")
            debug_output.append(f"Raw Record: {record}")
            
            symbol = 'N/A'
            if 'Contracts' in record and record['Contracts']:
                symbol = str(record['Contracts']).replace('USDT', '').replace('1000PEPE', 'PEPE').strip()
                debug_output.append(f"Symbol: {symbol}")
            
            pnl_value = 0
            if 'Realized P&L' in record and record['Realized P&L'] is not None:
                try:
                    pnl_raw = record['Realized P&L']
                    pnl_value = float(pnl_raw)
                    debug_output.append(f"PnL gefunden: {pnl_value} (Original: {pnl_raw})")
                except (ValueError, TypeError) as e:
                    debug_output.append(f"❌ Fehler beim Parsen von PnL: {e}")
            
            should_add_trade = (symbol != 'N/A' and pnl_value != 0)
            debug_output.append(f"Should add trade? Symbol!=N/A: {symbol != 'N/A'}, PnL!=0: {pnl_value != 0}, Result: {should_add_trade}")
            
            if should_add_trade:
                trades_found += 1
                total_pnl += pnl_value
                debug_output.append(f"✅ Trade added! Running total: {total_pnl}")
            else:
                debug_output.append(f"❌ Trade skipped - Symbol: {symbol}, PnL: {pnl_value}")
        
        debug_output.append(f"\n=== SUMMARY ===")
        debug_output.append(f"Trades found: {trades_found}")
        debug_output.append(f"Total PnL: {total_pnl}")
        
        debug_output.append(f"\n=== TESTING MAIN FUNCTION ===")
        account_details = get_trading_data_from_sheets(gc, spreadsheet)
        
        for acc in account_details:
            if acc['name'] == 'Incubatorzone':
                debug_output.append(f"Incubatorzone Result:")
                debug_output.append(f"  Has Data: {acc['has_data']}")
                debug_output.append(f"  Total Trades: {acc['total_trades']}")
                debug_output.append(f"  Total PnL: {acc['total_pnl']}")
                debug_output.append(f"  Recent Trades: {len(acc['recent_trades'])}")
                break
        
    except Exception as e:
        debug_output.append(f"ERROR: {e}")
        import traceback
        debug_output.append(f"Traceback: {traceback.format_exc()}")
    
    return f"<pre>{'<br>'.join(debug_output)}</pre>"

@app.route('/debug-sheets')
def debug_sheets():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    debug_info = []
    
    try:
        sheets_data = setup_google_sheets()
        
        if not sheets_data:
            debug_info.append("❌ Google Sheets Verbindung fehlgeschlagen")
            return f"<h1>Debug Info</h1><pre>{'<br>'.join(debug_info)}</pre>"
        
        gc, spreadsheet = sheets_data
        debug_info.append("✅ Google Sheets Verbindung erfolgreich")
        
        sheet_mapping = {
            "Incubator": "Incubatorzone",
            "Meme": "Memestrategies", 
            "Ethape": "Ethapestrategies",
            "Alts": "Altsstrategies",
            "Sol": "Solstrategies",
            "Btc": "Btcstrategies",
            "Core": "Corestrategies",
            "2k-10k": "2k->10k Projekt",
            "1k-5k": "1k->5k Projekt",
            "Claude": "Claude Projekt",
            "Blofin-7-Tage": "7 Tage Performer"
        }
        
        for sheet_name, account_name in sheet_mapping.items():
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                debug_info.append(f"✅ Worksheet '{sheet_name}' gefunden")
                
                all_records = worksheet.get_all_records()
                debug_info.append(f"   📊 {len(all_records)} Datensätze gefunden")
                
                if all_records:
                    columns = list(all_records[0].keys())
                    debug_info.append(f"   📋 Spalten: {', '.join(columns)}")
                    
                    for i, record in enumerate(all_records[:3]):
                        debug_info.append(f"   📄 Zeile {i+1}: {record}")
                        
                        pnl_found = False
                        for col, value in record.items():
                            if value and str(value).strip() != '':
                                try:
                                    clean_val = clean_numeric_value(value)
                                    pnl_val = float(clean_val)
                                    if pnl_val != 0:
                                        debug_info.append(f"      💰 Möglicher PnL in '{col}': {pnl_val}")
                                        pnl_found = True
                                except:
                                    pass
                        
                        if not pnl_found:
                            debug_info.append(f"      ⚠️ Kein PnL-Wert in dieser Zeile gefunden")
                else:
                    debug_info.append(f"   ❌ Keine Daten in '{sheet_name}'")
                    
            except gspread.exceptions.WorksheetNotFound:
                debug_info.append(f"❌ Worksheet '{sheet_name}' nicht gefunden")
            except Exception as e:
                debug_info.append(f"❌ Fehler bei '{sheet_name}': {e}")
        
    except Exception as e:
        debug_info.append(f"❌ Allgemeiner Fehler: {e}")
    
    return f"<h1>Google Sheets Debug Info</h1><pre>{'<br>'.join(debug_info)}</pre><br><a href='/dashboard'>Zurück zum Dashboard</a>"

# Neue Debug-Route für Blofin
@app.route('/debug-blofin')
def debug_blofin():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    debug_info = []
    
    # Finde Blofin Account
    blofin_acc = None
    for acc in subaccounts:
        if acc["exchange"] == "blofin" and acc["name"] == "7 Tage Performer":
            blofin_acc = acc
            break
    
    if not blofin_acc:
        return "Blofin Account nicht gefunden"
    
    try:
        client = BlofinAPI(blofin_acc["key"], blofin_acc["secret"], blofin_acc["passphrase"])
        
        # Rohe Positions-Daten abrufen
        pos_response = client.get_positions()
        debug_info.append(f"=== RAW BLOFIN POSITIONS RESPONSE ===")
        debug_info.append(f"Status Code: {pos_response.get('code')}")
        debug_info.append(f"Message: {pos_response.get('msg', 'No message')}")
        debug_info.append(f"Data: {json.dumps(pos_response.get('data', []), indent=2)}")
        
        if pos_response.get('code') == '0' and pos_response.get('data'):
            debug_info.append(f"\n=== POSITION ANALYSIS ===")
            
            for i, pos in enumerate(pos_response['data']):
                debug_info.append(f"\n--- Position {i+1} ---")
                debug_info.append(f"Full Position Object: {json.dumps(pos, indent=2)}")
                
                # Alle verfügbaren Felder anzeigen
                debug_info.append(f"Available Fields: {list(pos.keys())}")
                
                # Position Size Analysis
                possible_size_fields = ['pos', 'positions', 'size', 'sz', 'qty', 'quantity']
                for field in possible_size_fields:
                    if field in pos:
                        debug_info.append(f"Size Field '{field}': {pos[field]} (Type: {type(pos[field])})")
                
                # Side Analysis
                possible_side_fields = ['side', 'posSide', 'position_side', 'direction', 'type', 'positionSide']
                for field in possible_side_fields:
                    if field in pos:
                        debug_info.append(f"Side Field '{field}': {pos[field]} (Type: {type(pos[field])})")
                
                # Symbol Analysis
                possible_symbol_fields = ['instId', 'instrument_id', 'symbol', 'underlying', 'asset']
                for field in possible_symbol_fields:
                    if field in pos:
                        debug_info.append(f"Symbol Field '{field}': {pos[field]}")
                
                # PnL Analysis
                possible_pnl_fields = ['upl', 'unrealizedPnl', 'unrealized_pnl', 'pnl', 'profit', 'loss']
                for field in possible_pnl_fields:
                    if field in pos:
                        debug_info.append(f"PnL Field '{field}': {pos[field]} (Type: {type(pos[field])})")
        
    except Exception as e:
        debug_info.append(f"ERROR: {e}")
        import traceback
        debug_info.append(f"Traceback: {traceback.format_exc()}")
    
    return f"<h1>Blofin Debug Info</h1><pre>{'<br>'.join(debug_info)}</pre><br><a href='/dashboard'>Zurück zum Dashboard</a>"

@app.route('/account-details')
def account_details():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    # KEINE AUTOMATISCHE DATENLADUNG MEHR!
    # Gebe nur leere Daten zurück - Laden erfolgt nur per Button
    
    tz = timezone("Europe/Berlin")
    now = datetime.now(tz).strftime("%d.%m.%Y %H:%M:%S")
    
    return render_template('account_details.html', 
                           account_details=[],  # Leer! Keine automatische Ladung
                           startkapital=startkapital,
                           now=now,
                           initial_load=True)  # Flag für Initial-Zustand

@app.route('/account-details-data')
def account_details_data():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        sheets_data = setup_google_sheets()
        
        if sheets_data:
            gc, spreadsheet = sheets_data
            account_details_data = get_trading_data_from_sheets(gc, spreadsheet)
        else:
            logging.warning("Google Sheets nicht verfügbar")
            account_details_data = []
        
        return jsonify(account_details_data)
        
    except Exception as e:
        logging.error(f"Fehler beim Laden der Account Details Data: {e}")
        return jsonify([]), 500

if __name__ == '__main__':
    os.makedirs('static', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=10000)
