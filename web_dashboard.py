from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from pybit.unified_trading import HTTP
import os
from datetime import datetime
import matplotlib.pyplot as plt
import json

app = Flask(__name__)
app.secret_key = 'dein_sicherer_schlüssel'  # Ändere dies!

users = {
    "admin": generate_password_hash("passwort123")
}

STARTKAPITAL = 13729.37  # Startwert in USD

subaccounts = [
    {"name": "Incubatorzone", "key": os.getenv("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.getenv("BYBIT_INCUBATORZONE_API_SECRET")},
    {"name": "Memestrategies", "key": os.getenv("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_MEMESTRATEGIES_API_SECRET")},
    {"name": "Ethapestrategies", "key": os.getenv("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ETHAPESTRATEGIES_API_SECRET")},
    {"name": "Altsstrategies", "key": os.getenv("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ALTSSTRATEGIES_API_SECRET")},
    {"name": "Solstrategies", "key": os.getenv("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_SOLSTRATEGIES_API_SECRET")},
    {"name": "Btcstrategies", "key": os.getenv("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_BTCSTRATEGIES_API_SECRET")},
    {"name": "Corestrategies", "key": os.getenv("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_CORESTRATEGIES_API_SECRET")},
    {"name": "2k->10k Projekt", "key": os.getenv("BYBIT_2K_API_KEY"), "secret": os.getenv("BYBIT_2K_API_SECRET")},
    {"name": "1k->5k Projekt", "key": os.getenv("BYBIT_1K_API_KEY"), "secret": os.getenv("BYBIT_1K_API_SECRET")},
]

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

    results = []
    total_value = 0

    for acc in subaccounts:
        try:
            session_api = HTTP(api_key=acc["key"], api_secret=acc["secret"])
            balance_raw = session_api.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
            usdt = 0.0
            for item in balance_raw:
                for coin in item["coin"]:
                    if coin["coin"] == "USDT":
                        usdt = float(coin["walletBalance"])
            pnl_abs = usdt - get_initial_value(acc["name"])
            pnl_pct = (pnl_abs / get_initial_value(acc["name"])) * 100
            results.append({
                "name": acc["name"],
                "usdt": usdt,
                "pnl_abs": pnl_abs,
                "pnl_pct": pnl_pct,
                "status": "🟢"
            })
            total_value += usdt
        except Exception as e:
            results.append({
                "name": acc["name"],
                "usdt": 0.0,
                "pnl_abs": 0.0,
                "pnl_pct": 0.0,
                "status": "🔴"
            })

    total_pnl = total_value - STARTKAPITAL
    total_pnl_pct = (total_pnl / STARTKAPITAL) * 100

    return render_template("dashboard.html",
                           results=results,
                           total_value=total_value,
                           total_pnl=total_pnl,
                           total_pnl_pct=total_pnl_pct,
                           start_value=STARTKAPITAL)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

def get_initial_value(account_name):
    initial_values = {
        "Incubatorzone": 400,
        "Memestrategies": 800,
        "Ethapestrategies": 1200,
        "Altsstrategies": 1200,
        "Solstrategies": 1713.81,
        "Btcstrategies": 1923,
        "Corestrategies": 2000.56,
        "2k->10k Projekt": 2000,
        "1k->5k Projekt": 1000
    }
    return initial_values.get(account_name, 0)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
