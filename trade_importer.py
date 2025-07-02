#!/usr/bin/env python3
"""
Trade Import Script für alle Subaccounts
===========================================

Usage:
    python trade_importer.py --mode=full     # Vollständiger Import
    python trade_importer.py --mode=update   # Nur neue Trades
"""

import os
import logging
import json
import argparse
from datetime import datetime, timedelta
from pybit.unified_trading import HTTP
import gspread
from google.oauth2.service_account import Credentials
import requests
import hmac
import hashlib
import time
import base64
import uuid
from urllib.parse import urlencode
from pytz import timezone

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Account Konfiguration
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

def get_berlin_time():
    """Hole korrekte Berliner Zeit"""
    try:
        berlin_tz = timezone("Europe/Berlin")
        return datetime.now(berlin_tz)
    except Exception:
        return datetime.now()

class BlofinAPI:
    """Blofin API Client"""
    
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
            else:
                response = requests.request(method, url, headers=headers, data=body, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logging.error(f"Blofin API Error: {response.status_code}")
                return {"code": "error", "data": None}
                
        except Exception as e:
            logging.error(f"Blofin API Exception: {e}")
            return {"code": "error", "data": None}
    
    def get_trade_history(self, start_time=None, limit=100):
        """Hole Trade History"""
        endpoints = ['/api/v1/trade/fills', '/api/v1/account/fills']
        
        params = {}
        if start_time:
            params['begin'] = str(start_time)
        if limit:
            params['limit'] = str(limit)
        
        for endpoint in endpoints:
            response = self._make_request('GET', endpoint, params)
            if response.get('code') in ['0', 0] and response.get('data'):
                return response['data']
        
        return []

class GoogleSheetsManager:
    """Google Sheets Manager"""
    
    def __init__(self):
        self.gc = None
        self.spreadsheet = None
        self._connect()
    
    def _connect(self):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_file = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
            
            if not creds_file:
                raise Exception("GOOGLE_SERVICE_ACCOUNT_JSON nicht gefunden")
            
            creds_data = json.loads(creds_file)
            credentials = Credentials.from_service_account_info(creds_data, scopes=scope)
            self.gc = gspread.authorize(credentials)
            
            sheet_id = os.environ.get('GOOGLE_SHEET_ID')
            if not sheet_id:
                raise Exception("GOOGLE_SHEET_ID nicht gefunden")
            
            self.spreadsheet = self.gc.open_by_key(sheet_id)
            logging.info("✅ Google Sheets verbunden")
            
        except Exception as e:
            logging.error(f"❌ Google Sheets Fehler: {e}")
            raise
    
    def get_or_create_worksheet(self, account_name):
        """Hole oder erstelle Worksheet"""
        sheet_name_map = {
            'Claude Projekt': 'Claude_Trades',
            '7 Tage Performer': 'Blofin_Trades',
            'Incubatorzone': 'Incubator_Trades',
            'Memestrategies': 'Meme_Trades',
            'Ethapestrategies': 'Ethape_Trades',
            'Altsstrategies': 'Alts_Trades',
            'Solstrategies': 'Sol_Trades',
            'Btcstrategies': 'Btc_Trades',
            'Corestrategies': 'Core_Trades',
            '2k->10k Projekt': '2k10k_Trades',
            '1k->5k Projekt': '1k5k_Trades'
        }
        
        sheet_name = sheet_name_map.get(account_name, account_name.replace(' ', '_'))
        
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            logging.info(f"📋 Worksheet gefunden: {sheet_name}")
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=15)
            
            headers = [
                'Timestamp', 'Date', 'Symbol', 'Side', 'Size', 'Price', 
                'PnL', 'Fee', 'Strategy', 'Order_ID', 'Trade_ID', 
                'Exchange', 'Account', 'Status', 'Notes'
            ]
            worksheet.append_row(headers)
            logging.info(f"✅ Neues Worksheet erstellt: {sheet_name}")
        
        return worksheet
    
    def get_last_import_time(self, worksheet):
        """Hole letzte Import-Zeit"""
        try:
            all_records = worksheet.get_all_records()
            if not all_records:
                return None
            
            latest_timestamp = 0
            for record in all_records:
                if 'Timestamp' in record and record['Timestamp']:
                    try:
                        ts = int(record['Timestamp'])
                        latest_timestamp = max(latest_timestamp, ts)
                    except:
                        continue
            
            return latest_timestamp if latest_timestamp > 0 else None
            
        except Exception as e:
            logging.error(f"Fehler beim Abrufen der Import-Zeit: {e}")
            return None
    
    def append_trades(self, worksheet, trades):
        """Füge Trades hinzu"""
        if not trades:
            return
        
        rows = []
        for trade in trades:
            row = [
                trade.get('timestamp', ''),
                trade.get('date', ''),
                trade.get('symbol', ''),
                trade.get('side', ''),
                trade.get('size', ''),
                trade.get('price', ''),
                trade.get('pnl', ''),
                trade.get('fee', ''),
                trade.get('strategy', ''),
                trade.get('order_id', ''),
                trade.get('trade_id', ''),
                trade.get('exchange', ''),
                trade.get('account', ''),
                trade.get('status', 'Completed'),
                trade.get('notes', '')
            ]
            rows.append(row)
        
        if rows:
            worksheet.append_rows(rows)
            logging.info(f"✅ {len(rows)} Trades hinzugefügt")

class TradeImporter:
    """Trade Importer Hauptklasse"""
    
    def __init__(self):
        self.sheets_manager = GoogleSheetsManager()
    
    def normalize_trade_data(self, raw_trade, account_name, exchange):
        """Normalisiere Trade-Daten"""
        normalized = {
            'account': account_name,
            'exchange': exchange,
            'timestamp': '',
            'date': '',
            'symbol': '',
            'side': '',
            'size': '',
            'price': '',
            'pnl': '',
            'fee': '',
            'strategy': '',
            'order_id': '',
            'trade_id': '',
            'status': 'Completed'
        }
        
        try:
            if exchange == 'bybit':
                normalized.update({
                    'timestamp': raw_trade.get('execTime', ''),
                    'date': datetime.fromtimestamp(int(raw_trade.get('execTime', 0)) / 1000).strftime('%Y-%m-%d %H:%M:%S') if raw_trade.get('execTime') else '',
                    'symbol': raw_trade.get('symbol', '').replace('USDT', ''),
                    'side': raw_trade.get('side', ''),
                    'size': raw_trade.get('execQty', ''),
                    'price': raw_trade.get('execPrice', ''),
                    'fee': raw_trade.get('execFee', ''),
                    'order_id': raw_trade.get('orderId', ''),
                    'trade_id': raw_trade.get('execId', '')
                })
                
            elif exchange == 'blofin':
                normalized.update({
                    'timestamp': raw_trade.get('fillTime', ''),
                    'date': datetime.fromtimestamp(int(raw_trade.get('fillTime', 0)) / 1000).strftime('%Y-%m-%d %H:%M:%S') if raw_trade.get('fillTime') else '',
                    'symbol': raw_trade.get('instId', '').replace('-USDT', ''),
                    'side': raw_trade.get('side', ''),
                    'size': raw_trade.get('fillSz', ''),
                    'price': raw_trade.get('fillPx', ''),
                    'pnl': raw_trade.get('pnl', ''),
                    'fee': raw_trade.get('fee', ''),
                    'order_id': raw_trade.get('ordId', ''),
                    'trade_id': raw_trade.get('fillId', '')
                })
            
            # Strategy Mapping
            symbol = normalized['symbol']
            if symbol:
                strategy_map = {
                    'BTC': 'Bitcoin Strategy',
                    'ETH': 'Ethereum Strategy',
                    'SOL': 'Solana Strategy',
                    'AVAX': 'Avalanche Strategy',
                    'ALGO': 'Algorand Strategy',
                    'ARB': 'Arbitrum Strategy',
                    'WIF': 'WIF Strategy',
                    'RUNE': 'Thorchain Strategy'
                }
                normalized['strategy'] = strategy_map.get(symbol, f'{symbol} Strategy')
                
        except Exception as e:
            logging.error(f"Normalisierungsfehler: {e}")
        
        return normalized
    
    def import_bybit_trades(self, account, mode='full', last_import_time=None):
        """Importiere Bybit Trades"""
        name = account['name']
        
        if not account.get('key') or not account.get('secret'):
            logging.warning(f"❌ API-Schlüssel fehlen für {name}")
            return []
        
        try:
            client = HTTP(api_key=account['key'], api_secret=account['secret'])
            all_trades = []
            
            # Zeitraum bestimmen
            if mode == 'full':
                start_time = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
                logging.info(f"📥 {name}: Vollimport (6 Monate)")
            else:
                if last_import_time:
                    start_time = last_import_time
                else:
                    start_time = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
                logging.info(f"📥 {name}: Update-Import")
            
            # Trades laden
            cursor = None
            total_trades = 0
            
            while True:
                try:
                    params = {
                        'category': 'linear',
                        'startTime': start_time,
                        'limit': 1000
                    }
                    
                    if cursor:
                        params['cursor'] = cursor
                    
                    response = client.get_executions(**params)
                    
                    if not response or response.get('retCode') != 0:
                        break
                    
                    result = response.get('result', {})
                    trades = result.get('list', [])
                    
                    if not trades:
                        break
                    
                    for trade in trades:
                        normalized = self.normalize_trade_data(trade, name, 'bybit')
                        all_trades.append(normalized)
                    
                    total_trades += len(trades)
                    logging.info(f"📊 {name}: {len(trades)} Trades (Total: {total_trades})")
                    
                    cursor = result.get('nextPageCursor')
                    if not cursor:
                        break
                    
                    time.sleep(0.1)  # Rate limiting
                    
                except Exception as e:
                    logging.error(f"❌ {name}: Batch Error - {e}")
                    break
            
            logging.info(f"✅ {name}: {total_trades} Trades importiert")
            return all_trades
            
        except Exception as e:
            logging.error(f"❌ {name}: {e}")
            return []
    
    def import_blofin_trades(self, account, mode='full', last_import_time=None):
        """Importiere Blofin Trades"""
        name = account['name']
        
        if not all([account.get('key'), account.get('secret'), account.get('passphrase')]):
            logging.warning(f"❌ API-Schlüssel fehlen für {name}")
            return []
        
        try:
            client = BlofinAPI(account['key'], account['secret'], account['passphrase'])
            
            if mode == 'full':
                start_time = int((datetime.now() - timedelta(days=180)).timestamp() * 1000)
            else:
                start_time = last_import_time or int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
            
            trades = client.get_trade_history(start_time=start_time, limit=1000)
            
            all_trades = []
            for trade in trades:
                normalized = self.normalize_trade_data(trade, name, 'blofin')
                all_trades.append(normalized)
            
            logging.info(f"✅ {name}: {len(all_trades)} Trades importiert")
            return all_trades
            
        except Exception as e:
            logging.error(f"❌ {name}: {e}")
            return []
    
    def import_account(self, account, mode='full'):
        """Importiere einen Account"""
        name = account['name']
        exchange = account['exchange']
        
        logging.info(f"🚀 Import {name} ({exchange})")
        
        worksheet = self.sheets_manager.get_or_create_worksheet(name)
        
        last_import_time = None
        if mode == 'update':
            last_import_time = self.sheets_manager.get_last_import_time(worksheet)
        
        if exchange == 'bybit':
            trades = self.import_bybit_trades(account, mode, last_import_time)
        elif exchange == 'blofin':
            trades = self.import_blofin_trades(account, mode, last_import_time)
        else:
            logging.error(f"❌ Unbekannte Exchange: {exchange}")
            return
        
        if trades:
            self.sheets_manager.append_trades(worksheet, trades)
            logging.info(f"✅ {name}: {len(trades)} Trades gespeichert")
        else:
            logging.info(f"ℹ️ {name}: Keine neuen Trades")
    
    def import_all_accounts(self, mode='full', specific_account=None):
        """Importiere alle Accounts"""
        start_time = datetime.now()
        logging.info(f"🎯 Start Trade-Import ({mode})")
        
        accounts_to_process = subaccounts
        if specific_account:
            accounts_to_process = [acc for acc in subaccounts if acc['name'] == specific_account]
        
        successful = 0
        for i, account in enumerate(accounts_to_process, 1):
            try:
                logging.info(f"📋 Account {i}/{len(accounts_to_process)}: {account['name']}")
                self.import_account(account, mode)
                successful += 1
                
                if i < len(accounts_to_process):
                    time.sleep(2)  # Rate limiting
                    
            except Exception as e:
                logging.error(f"❌ {account['name']}: {e}")
        
        duration = datetime.now() - start_time
        logging.info(f"🏁 Import abgeschlossen: {successful}/{len(accounts_to_process)} Accounts in {duration}")

def main():
    """Hauptfunktion"""
    parser = argparse.ArgumentParser(description='Trade Import Script')
    parser.add_argument('--mode', choices=['full', 'update'], default='update')
    parser.add_argument('--account', type=str, help='Spezifischer Account')
    
    args = parser.parse_args()
    
    try:
        importer = TradeImporter()
        importer.import_all_accounts(mode=args.mode, specific_account=args.account)
        
    except KeyboardInterrupt:
        logging.info("❌ Abgebrochen")
    except Exception as e:
        logging.error(f"❌ Kritischer Fehler: {e}")

if __name__ == "__main__":
    main()
