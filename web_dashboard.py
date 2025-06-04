import os
import time
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_'+os.urandom(12).hex())

# Debug-Modus
DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

# Benutzerdaten
users = {"husky125": generate_password_hash("Ideal250!")}

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
    # ... (alle anderen Konten analog)
]

def get_bybit_balance(api_key, api_secret):
    try:
        session = HTTP(api_key=api_key, api_secret=api_secret)
        balance = session.get_wallet_balance(accountType="UNIFIED")
        return float(balance['result']['list'][0]['coin'][0]['availableToWithdraw'])
    except Exception as e:
        print(f"Bybit Fehler: {str(e)}")
        return 0.0

def get_blofin_balance(api_key, api_secret, passphrase):
    try:
        client = BloFinClient(api_key, api_secret, passphrase)
        balance = client.account.get_balance(account_type="futures")
        return float(balance['data'][0]['available'])
    except Exception as e:
        print(f"Blofin Fehler: {str(e)}")
        return 0.0

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users and check_password_hash(users[username], password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Falsche Anmeldedaten")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    accounts = []
    total = 0.0
    
    for acc in subaccounts:
        creds = {
            'key': os.environ.get(acc['key_env']),
            'secret': os.environ.get(acc['secret_env']),
            'passphrase': os.environ.get(acc.get('passphrase_env', ''))
        }
        
        if acc['exchange'] == 'bybit':
            balance = get_bybit_balance(creds['key'], creds['secret'])
        else:
            balance = get_blofin_balance(creds['key'], creds['secret'], creds['passphrase'])
        
        start = starting_balances.get(acc['name'], 0.0)
        pnl = balance - start
        pnl_percent = (pnl / start) * 100 if start != 0 else 0
        
        accounts.append({
            'name': acc['name'],
            'balance': f"{balance:.2f}",
            'pnl': f"{pnl:.2f}",
            'pnl_percent': f"{pnl_percent:.2f}",
            'status': 'OK' if balance > 0 else 'Error'
        })
        total += balance

    # Zeitraum-Daten (Dummy-Werte)
    time_data = {
        'pnl_1d': 0, 'pnl_1d_str': "N/A", 'pnl_1d_percent': 0,
        'pnl_7d': 0, 'pnl_7d_str': "N/A", 'pnl_7d_percent': 0,
        'pnl_30d': 0, 'pnl_30d_str': "N/A", 'pnl_30d_percent': 0
    }

    return render_template(
        'dashboard.html',
        accounts=accounts,
        total_balance=f"{total:.2f}",
        total_pnl=f"{(total - sum(starting_balances.values())):.2f}",
        **time_data
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=DEBUG)
