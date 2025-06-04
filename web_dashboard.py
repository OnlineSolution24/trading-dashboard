import os
import time
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from datetime import datetime
import matplotlib
matplotlib.use('Agg')  # Für Server-Betrieb
import matplotlib.pyplot as plt

# ========== KONFIGURATION ==========
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_key_'+os.urandom(12).hex())

# Debug-Einstellungen
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'
API_TIMEOUT = 15  # Sekunden

# ========== DATENMODEL ==========
users = {
    "husky125": generate_password_hash("Ideal250!")
}

starting_balances = {
    "Incubatorzone": 400.00,
    "Memestrategies": 800.00,
    "Ethapestrategies": 1200.00,
    "Altsstrategies": 1200.00,
    "Solstrategies": 1713.81,
    "Btcstrategies": 1923.00,
    "Corestrategies": 2000.56,
    "2k->10k Projekt": 2000.00,
    "1k->5k Projekt": 1000.00,
    "Blofin": 1492.00
}

subaccounts = [
    {"name": "Incubatorzone", "exchange": "bybit", "key_env": "BYBIT_INCUBATORZONE_API_KEY", "secret_env": "BYBIT_INCUBATORZONE_API_SECRET"},
    {"name": "Memestrategies", "exchange": "bybit", "key_env": "BYBIT_MEMESTRATEGIES_API_KEY", "secret_env": "BYBIT_MEMESTRATEGIES_API_SECRET"},
    {"name": "Ethapestrategies", "exchange": "bybit", "key_env": "BYBIT_ETHAPESTRATEGIES_API_KEY", "secret_env": "BYBIT_ETHAPESTRATEGIES_API_SECRET"},
    {"name": "Altsstrategies", "exchange": "bybit", "key_env": "BYBIT_ALTSSTRATEGIES_API_KEY", "secret_env": "BYBIT_ALTSSTRATEGIES_API_SECRET"},
    {"name": "Solstrategies", "exchange": "bybit", "key_env": "BYBIT_SOLSTRATEGIES_API_KEY", "secret_env": "BYBIT_SOLSTRATEGIES_API_SECRET"},
    {"name": "Btcstrategies", "exchange": "bybit", "key_env": "BYBIT_BTCSTRATEGIES_API_KEY", "secret_env": "BYBIT_BTCSTRATEGIES_API_SECRET"},
    {"name": "Corestrategies", "exchange": "bybit", "key_env": "BYBIT_CORESTRATEGIES_API_KEY", "secret_env": "BYBIT_CORESTRATEGIES_API_SECRET"},
    {"name": "2k->10k Projekt", "exchange": "bybit", "key_env": "BYBIT_2K_API_KEY", "secret_env": "BYBIT_2K_API_SECRET"},
    {"name": "1k->5k Projekt", "exchange": "bybit", "key_env": "BYBIT_1K_API_KEY", "secret_env": "BYBIT_1K_API_SECRET"},
    {"name": "Blofin", "exchange": "blofin", "key_env": "BLOFIN_API_KEY", "secret_env": "BLOFIN_API_SECRET", "passphrase_env": "BLOFIN_API_PASSPHRASE"}
]

# ========== HELPER FUNCTIONS ==========
def log(message):
    if DEBUG:
        print(f"[DEBUG] {datetime.now().isoformat()} - {message}")

def get_account_credentials(account):
    """Holt API-Keys aus Environment Variables"""
    creds = {
        "key": os.environ.get(account["key_env"]),
        "secret": os.environ.get(account["secret_env"])
    }
    if account["exchange"] == "blofin":
        creds["passphrase"] = os.environ.get(account["passphrase_env"])
    return creds

# ========== API FUNKTIONEN ==========
def fetch_bybit_data(api_key, api_secret):
    """Holt alle Daten von Bybit API"""
    client = HTTP(
        api_key=api_key,
        api_secret=api_secret,
        recv_window=10000,
        request_timeout=API_TIMEOUT
    )
    
    try:
        # Guthaben abfragen
        balance = client.get_wallet_balance(accountType="UNIFIED")
        usdt_balance = 0.0
        if balance and "result" in balance:
            for account in balance["result"]["list"]:
                for coin in account["coin"]:
                    if coin["coin"] == "USDT":
                        usdt_balance += float(coin["availableToWithdraw"])
        
        # Positionen abfragen
        positions = client.get_positions(category="linear", settleCoin="USDT")
        open_positions = []
        if positions and "result" in positions:
            open_positions = [
                {
                    "symbol": p["symbol"],
                    "size": float(p["size"]),
                    "pnl": float(p["unrealisedPnl"])
                }
                for p in positions["result"]["list"]
                if float(p["size"]) != 0
            ]
        
        return usdt_balance, open_positions
    
    except Exception as e:
        log(f"Bybit API Fehler: {str(e)}")
        raise

def fetch_blofin_data(api_key, api_secret, passphrase):
    """Holt alle Daten von Blofin API"""
    client = BloFinClient(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase
    )
    
    try:
        # Guthaben abfragen
        balance = client.account.get_balance(account_type="futures")
        usdt_balance = 0.0
        if balance and "data" in balance:
            for coin in balance["data"]:
                if coin["currency"] == "USDT":
                    usdt_balance = float(coin["available"])
                    break
        
        # Positionen abfragen
        positions = client.account.get_positions(account_type="futures")
        open_positions = []
        if positions and "data" in positions:
            open_positions = [
                {
                    "symbol": p["symbol"],
                    "size": abs(float(p["positionQty"])),
                    "pnl": float(p["unrealizedPnl"])
                }
                for p in positions["data"]
                if float(p["positionQty"]) != 0
            ]
        
        return usdt_balance, open_positions
    
    except Exception as e:
        log(f"Blofin API Fehler: {str(e)}")
        raise

# ========== FLASK ROUTEN ==========
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and check_password_hash(users[username], password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Ungültige Anmeldedaten")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    account_data = []
    total_current = 0.0
    
    for account in subaccounts:
        creds = get_account_credentials(account)
        if not all(creds.values()):
            log(f"Fehlende Credentials für {account['name']}")
            account_data.append({
                "name": account["name"],
                "balance": 0.0,
                "error": "API-Keys nicht konfiguriert"
            })
            continue
        
        try:
            if account["exchange"] == "bybit":
                balance, positions = fetch_bybit_data(creds["key"], creds["secret"])
            else:
                balance, positions = fetch_blofin_data(
                    creds["key"], 
                    creds["secret"], 
                    creds.get("passphrase")
                )
            
            start_balance = starting_balances.get(account["name"], 0.0)
            pnl = balance - start_balance
            pnl_percent = (pnl / start_balance) * 100 if start_balance != 0 else 0
            
            account_data.append({
                "name": account["name"],
                "balance": balance,
                "start_balance": start_balance,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "positions": positions,
                "api_ok": True
            })
            total_current += balance
            
        except Exception as e:
            log(f"Verarbeitungsfehler {account['name']}: {str(e)}")
            account_data.append({
                "name": account["name"],
                "balance": 0.0,
                "error": str(e),
                "api_ok": False
            })
    
    # Gesamtberechnungen
    total_start = sum(starting_balances.values())
    total_pnl = total_current - total_start
    total_pnl_percent = (total_pnl / total_start) * 100 if total_start != 0 else 0
    
    # Chart erstellen
    chart_path = "static/performance_chart.png"
    os.makedirs("static", exist_ok=True)
    
    if account_data:
        fig, ax = plt.subplots(figsize=(12, 6))
        names = [acc["name"] for acc in account_data]
        pnls = [acc["pnl_percent"] for acc in account_data]
        colors = ['green' if p >= 0 else 'red' for p in pnls]
        
        bars = ax.bar(names, pnls, color=colors)
        ax.set_title("Konto-Performance (%)")
        ax.set_ylabel("PnL %")
        plt.xticks(rotation=45, ha='right')
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.2f}%',
                    ha='center', va='bottom')
        
        plt.tight_layout()
        plt.savefig(chart_path, dpi=100)
        plt.close()
    
    return render_template(
        "dashboard.html",
        subaccounts=account_data,
        total_balance=total_current,
        total_pnl=total_pnl,
        total_pnl_percent=total_pnl_percent,
        chart_path=chart_path
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# ========== START APPLICATION ==========
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=DEBUG)
