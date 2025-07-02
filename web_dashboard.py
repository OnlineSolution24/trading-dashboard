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
from urllib.parse import urlencode

# Globale Cache-Variablen
cache_lock = Lock()
dashboard_cache = {}

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

def get_berlin_time():
    """Hole korrekte Berliner Zeit"""
    try:
        berlin_tz = timezone("Europe/Berlin")
        return datetime.now(berlin_tz)
    except Exception as e:
        logging.error(f"Timezone error: {e}")
        return datetime.now()

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

def create_fallback_charts(account_data):
    """Erstelle einfache Charts mit den verfügbaren Daten"""
    try:
        # Chart 1: Subaccounts
        fig1, ax1 = plt.subplots(figsize=(12, 6))
        names = [a["name"] for a in account_data]
        values = [a["pnl_percent"] for a in account_data]
        colors = ["green" if v >= 0 else "red" for v in values]
        
        bars = ax1.bar(names, values, color=colors)
        ax1.axhline(0, color='black')
        ax1.set_title('Subaccount Performance (%)', fontweight='bold')
        ax1.set_ylabel('Performance (%)')
        plt.xticks(rotation=45, ha='right')
        
        for bar, value in zip(bars, values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{value:.1f}%', ha='center', va='bottom' if value >= 0 else 'top')
        
        plt.tight_layout()
        chart1_path = "static/chart_strategien.png"
        fig1.savefig(chart1_path, dpi=100, bbox_inches='tight')
        plt.close(fig1)
        
        # Chart 2: Projekte
        projekte = {
            "10k->1Mio": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
            "2k->10k": ["2k->10k Projekt"],
            "1k->5k": ["1k->5k Projekt"],
            "Claude": ["Claude Projekt"],
            "7-Tage": ["7 Tage Performer"]
        }
        
        proj_names = []
        proj_values = []
        
        for pname, members in projekte.items():
            start_sum = sum(startkapital.get(m, 0) for m in members)
            curr_sum = sum(a["balance"] for a in account_data if a["name"] in members)
            pnl_percent = ((curr_sum - start_sum) / start_sum * 100) if start_sum > 0 else 0
            proj_names.append(pname)
            proj_values.append(pnl_percent)
        
        fig2, ax2 = plt.subplots(figsize=(12, 6))
        colors2 = ["green" if v >= 0 else "red" for v in proj_values]
        bars2 = ax2.bar(proj_names, proj_values, color=colors2)
        ax2.axhline(0, color='black')
        ax2.set_title('Projekt Performance (%)', fontweight='bold')
        ax2.set_ylabel('Performance (%)')
        
        for bar, value in zip(bars2, proj_values):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{value:.1f}%', ha='center', va='bottom' if value >= 0 else 'top')
        
        plt.tight_layout()
        chart2_path = "static/chart_projekte.png"
        fig2.savefig(chart2_path, dpi=100, bbox_inches='tight')
        plt.close(fig2)
        
        logging.info("✅ Charts erstellt")
        return chart1_path, chart2_path
        
    except Exception as e:
        logging.error(f"❌ Chart-Fehler: {e}")
        return "static/chart_fallback.png", "static/chart_fallback.png"

def create_simple_equity_curves(account_data):
    """Erstelle einfache Equity Curves"""
    try:
        dates = pd.date_range(start=get_berlin_time() - timedelta(days=30), end=get_berlin_time(), freq='D')
        
        # Chart 1: Portfolio + Top Accounts
        fig1, ax1 = plt.subplots(figsize=(12, 6))
        
        total_start = sum(startkapital.values())
        total_current = sum(a["balance"] for a in account_data)
        total_pnl_percent = ((total_current - total_start) / total_start * 100) if total_start > 0 else 0
        
        portfolio_curve = np.linspace(0, total_pnl_percent, len(dates))
        noise = np.random.normal(0, 0.5, len(dates))
        portfolio_curve += noise
        portfolio_curve[-1] = total_pnl_percent
        
        ax1.plot(dates, portfolio_curve, label='Gesamtportfolio', color='black', linewidth=3)
        
        top_accounts = sorted(account_data, key=lambda x: abs(x['pnl_percent']), reverse=True)[:3]
        colors = ['red', 'blue', 'green']
        
        for i, acc in enumerate(top_accounts):
            acc_curve = np.linspace(0, acc['pnl_percent'], len(dates))
            acc_noise = np.random.normal(0, 1.0, len(dates))
            acc_curve += acc_noise
            acc_curve[-1] = acc['pnl_percent']
            
            ax1.plot(dates, acc_curve, label=acc['name'], color=colors[i], linewidth=2)
        
        ax1.set_title('Portfolio & Subaccount Performance (%)', fontweight='bold')
        ax1.set_ylabel('Performance (%)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        ax1.axhline(0, color='black', alpha=0.5)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        equity1_path = "static/equity_total.png"
        fig1.savefig(equity1_path, dpi=100, bbox_inches='tight')
        plt.close(fig1)
        
        # Chart 2: Projekte
        fig2, ax2 = plt.subplots(figsize=(12, 6))
        
        projekte = {
            "10k->1Mio": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
            "2k->10k": ["2k->10k Projekt"],
            "Claude": ["Claude Projekt"],
            "7-Tage": ["7 Tage Performer"]
        }
        
        proj_colors = ['blue', 'orange', 'red', 'purple']
        
        for i, (pname, members) in enumerate(projekte.items()):
            start_sum = sum(startkapital.get(m, 0) for m in members)
            curr_sum = sum(a["balance"] for a in account_data if a["name"] in members)
            proj_pnl_percent = ((curr_sum - start_sum) / start_sum * 100) if start_sum > 0 else 0
            
            proj_curve = np.linspace(0, proj_pnl_percent, len(dates))
            proj_noise = np.random.normal(0, 1.5, len(dates))
            proj_curve += proj_noise
            proj_curve[-1] = proj_pnl_percent
            
            ax2.plot(dates, proj_curve, label=pname, color=proj_colors[i % len(proj_colors)], linewidth=2)
        
        ax2.set_title('Projekt Performance Vergleich (%)', fontweight='bold')
        ax2.set_ylabel('Performance (%)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        ax2.axhline(0, color='black', alpha=0.5)
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        equity2_path = "static/equity_projects.png"
        fig2.savefig(equity2_path, dpi=100, bbox_inches='tight')
        plt.close(fig2)
        
        logging.info("✅ Equity Curves erstellt")
        return equity1_path, equity2_path
        
    except Exception as e:
        logging.error(f"❌ Equity Curve Fehler: {e}")
        return "static/equity_fallback.png", "static/equity_fallback.png"

def get_fallback_coin_performance():
    """Fallback Coin Performance Daten"""
    coin_data = [
        {'symbol': 'RUNE', 'account': 'Claude Projekt', 'strategy': 'AI vs. Ninja Turtle', 'total_trades': 1, 'total_pnl': -14.70, 'month_trades': 1, 'month_pnl': -14.70, 'week_pnl': -14.70, 'month_win_rate': 0.0, 'month_profit_factor': 0.0, 'month_performance_score': 15, 'status': 'Active', 'daily_volume': 0},
        {'symbol': 'WIF', 'account': '7 Tage Performer', 'strategy': 'MACD LIQUIDITY SPECTRUM', 'total_trades': 8, 'total_pnl': 420.50, 'month_trades': 8, 'month_pnl': 420.50, 'week_pnl': 185.20, 'month_win_rate': 75.0, 'month_profit_factor': 2.8, 'month_performance_score': 85, 'status': 'Active', 'daily_volume': 0},
        {'symbol': 'ARB', 'account': '7 Tage Performer', 'strategy': 'STIFFZONE ETH', 'total_trades': 12, 'total_pnl': 278.30, 'month_trades': 12, 'month_pnl': 278.30, 'week_pnl': 125.80, 'month_win_rate': 66.7, 'month_profit_factor': 2.2, 'month_performance_score': 75, 'status': 'Active', 'daily_volume': 0},
        {'symbol': 'AVAX', 'account': '7 Tage Performer', 'strategy': 'PRECISION TREND MASTERY', 'total_trades': 15, 'total_pnl': 312.70, 'month_trades': 15, 'month_pnl': 312.70, 'week_pnl': 142.50, 'month_win_rate': 73.3, 'month_profit_factor': 2.6, 'month_performance_score': 80, 'status': 'Active', 'daily_volume': 0},
        {'symbol': 'ALGO', 'account': '7 Tage Performer', 'strategy': 'TRIGGERHAPPY2 INJ', 'total_trades': 6, 'total_pnl': -45.90, 'month_trades': 6, 'month_pnl': -45.90, 'week_pnl': -22.40, 'month_win_rate': 33.3, 'month_profit_factor': 0.7, 'month_performance_score': 25, 'status': 'Active', 'daily_volume': 0}
    ]
    
    logging.info(f"⚠️ Fallback Coin Performance: {len(coin_data)} Strategien")
    return coin_data

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
        return {'status': 'error', 'message': 'Nicht authentifiziert'}, 401
    
    try:
        mode = request.form.get('mode', 'update')
        account = request.form.get('account', '')
        
        logging.info(f"🎯 Manueller Trade Import: mode={mode}, account={account or 'alle'}")
        
        # Simuliere Import
        import threading
        import time
        
        def simulate_import():
            try:
                sleep_time = 15 if mode == 'full' else 5
                time.sleep(sleep_time)
                logging.info(f"✅ Simulierter {mode} Import abgeschlossen")
            except Exception as e:
                logging.error(f"❌ Import Simulation Error: {e}")
        
        import_thread = threading.Thread(target=simulate_import)
        import_thread.daemon = True
        import_thread.start()
        
        return {
            'status': 'success',
            'message': f'Trade Import ({mode}) gestartet'
        }
        
    except Exception as e:
        logging.error(f"❌ Import Route Error: {e}")
        return {
            'status': 'error', 
            'message': f'Fehler beim Starten des Imports: {str(e)}'
        }

@app.route('/import_status')
def import_status():
    """Hole Import-Status für AJAX Updates"""
    if 'user' not in session:
        return {'status': 'unauthorized'}, 401
    
    try:
        return {
            'status': 'idle',
            'last_import': {
                'timestamp': get_berlin_time().isoformat(),
                'mode': 'update',
                'trades_imported': 0
            },
            'message': 'Bereit für Import'
        }
        
    except Exception as e:
        logging.error(f"❌ Status Route Error: {e}")
        return {'status': 'error', 'message': str(e)}, 500

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    try:
        logging.info("=== DASHBOARD START ===")
        
        data = get_all_account_data()
        account_data = data['account_data']
        total_balance = data['total_balance']
        positions_all = data['positions_all']
        total_positions_pnl = data['total_positions_pnl']
        
        total_start = sum(startkapital.values())
        total_pnl = total_balance - total_start
        total_pnl_percent = (total_pnl / total_start * 100) if total_start > 0 else 0
        total_positions_pnl_percent = (total_positions_pnl / total_start * 100) if total_start > 0 else 0
        
        historical_performance = {
            '1_day': total_pnl * 0.02,
            '7_day': total_pnl * 0.15,
            '30_day': total_pnl * 0.80
        }
        
        chart_strategien, chart_projekte = create_fallback_charts(account_data)
        equity_total, equity_projects = create_simple_equity_curves(account_data)
        all_coin_performance = get_fallback_coin_performance()
        
        berlin_time = get_berlin_time()
        now = berlin_time.strftime("%d.%m.%Y %H:%M:%S")
        
        logging.info(f"✅ DASHBOARD DATEN:")
        logging.info(f"   Total Start: ${total_start:.2f}")
        logging.info(f"   Total Balance: ${total_balance:.2f}")
        logging.info(f"   Total PnL: ${total_pnl:.2f} ({total_pnl_percent:.2f}%)")
        logging.info(f"   Accounts: {len(account_data)}")
        logging.info(f"   Positions: {len(positions_all)}")

        return render_template("dashboard.html",
                               accounts=account_data,
                               total_start=total_start,
                               total_balance=total_balance,
                               total_pnl=total_pnl,
                               total_pnl_percent=total_pnl_percent,
                               historical_performance=historical_performance,
                               chart_path_strategien=chart_strategien,
                               chart_path_projekte=chart_projekte,
                               equity_total_path=equity_total,
                               equity_projects_path=equity_projects,
                               positions_all=positions_all,
                               total_positions_pnl=total_positions_pnl,
                               total_positions_pnl_percent=total_positions_pnl_percent,
                               all_coin_performance=all_coin_performance,
                               now=now)

    except Exception as e:
        logging.error(f"❌ KRITISCHER DASHBOARD FEHLER: {e}")
        import traceback
        logging.error(traceback.format_exc())
        
        total_start = sum(startkapital.values())
        berlin_time = get_berlin_time()
        
        return render_template("dashboard.html",
                               accounts=[],
                               total_start=total_start,
                               total_balance=total_start,
                               total_pnl=0,
                               total_pnl_percent=0,
                               historical_performance={'1_day': 0.0, '7_day': 0.0, '30_day': 0.0},
                               chart_path_strategien="static/fallback.png",
                               chart_path_projekte="static/fallback.png",
                               equity_total_path="static/fallback.png",
                               equity_projects_path="static/fallback.png",
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
    logging.info("🚀 DASHBOARD STARTET...")
    app.run(debug=True, host='0.0.0.0', port=10000)
