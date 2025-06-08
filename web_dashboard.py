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
                        
                        # Wenn total vorhanden ist, verwende das, sonst available + frozen
                        if total > 0:
                            usdt = total
                        else:
                            usdt = available + frozen
                        
                        logging.info(f"Blofin USDT gefunden: available={available}, frozen={frozen}, total={total}, final={usdt}")
                        break
        except Exception as e:
            logging.error(f"Fehler bei Blofin Asset Balance {acc['name']}: {e}")
        
        # Versuch 2: Account Info falls Asset Balance nicht funktioniert
        if usdt == 0.0:
            try:
                account_response = client._make_request('GET', '/api/v1/account/account')
                logging.info(f"Blofin Account Response: {account_response}")
                
                if account_response.get('code') == '0' and account_response.get('data'):
                    data = account_response['data']
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    
                    # Suche nach USDT in verschiedenen Strukturen
                    if 'details' in data:
                        for detail in data['details']:
                            if detail.get('ccy') == 'USDT' or detail.get('currency') == 'USDT':
                                usdt = float(detail.get('cashBal', detail.get('bal', detail.get('balance', 0))))
                                break
                    elif 'totalEq' in data:
                        usdt = float(data.get('totalEq', 0))
                    elif 'uTime' in data:  # Bybit-ähnliche Struktur
                        usdt = float(data.get('totalWalletBalance', data.get('totalMarginBalance', 0)))
            except Exception as e:
                logging.error(f"Fehler bei Blofin Account Info {acc['name']}: {e}")
        
        # Versuch 3: Wallet Balance
        if usdt == 0.0:
            try:
                wallet_response = client._make_request('GET', '/api/v1/asset/currencies')
                logging.info(f"Blofin Wallet Response: {wallet_response}")
                # Weitere Implementierung falls nötig
            except Exception as e:
                logging.error(f"Fehler bei Blofin Wallet {acc['name']}: {e}")
        
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
            "positions": positions
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
        "10k->1Mio Projekt": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
        "2k->10k Projekt": ["2k->10k Projekt"],
        "1k->5k Projekt": ["1k->5k Projekt"],
        "7 Tage Performer": ["7 Tage Performer"]
    }

    proj_labels = []
    proj_values = []
    for pname, members in projekte.items():
        start_sum = sum(startkapital.get(m, 0) for m in members)
        curr_sum = sum(a["balance"] for a in account_data if a["name"] in members)
        pnl_percent = ((curr_sum - start_sum) / start_sum) * 100
        proj_labels.append(pname)
        proj_values.append(pnl_percent)

    fig2, ax2 = plt.subplots(figsize=(10, 5))
    bars2 = ax2.bar(proj_labels, proj_values, color=["green" if v >= 0 else "red" for v in proj_values])
    ax2.axhline(0, color='black')
    ax2.set_xticklabels(proj_labels, rotation=30, ha="right")
    for i, bar in enumerate(bars2):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                 f"{proj_values[i]:+.1f}%", ha='center', va='bottom' if proj_values[i] >= 0 else 'top', fontsize=8)
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
                           now=now)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
