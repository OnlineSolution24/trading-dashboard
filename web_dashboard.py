import os
import json
import gspread
import matplotlib
matplotlib.use('Agg')  # Für headless Deployment (Render.com)
import matplotlib.pyplot as plt
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'supergeheim'

# 🔐 Benutzerverwaltung
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# 📊 API-Konfiguration
subaccounts = [
    {
        "name": "Incubatorzone",
        "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"),
        "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET")
    },
    {
        "name": "Memestrategies",
        "key": os.environ.get("BYBIT_MEMESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_MEMESTRATEGIES_API_SECRET")
    },
    {
        "name": "Ethapestrategies",
        "key": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_SECRET")
    },
    {
        "name": "Altsstrategies",
        "key": os.environ.get("BYBIT_ALTSSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_ALTSSTRATEGIES_API_SECRET")
    },
    {
        "name": "Solstrategies",
        "key": os.environ.get("BYBIT_SOLSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_SOLSTRATEGIES_API_SECRET")
    },
    {
        "name": "Btcstrategies",
        "key": os.environ.get("BYBIT_BTCSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_BTCSTRATEGIES_API_SECRET")
    },
    {
        "name": "Corestrategies",
        "key": os.environ.get("BYBIT_CORESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_CORESTRATEGIES_API_SECRET")
    },
    {
        "name": "2k->10k Projekt",
        "key": os.environ.get("BYBIT_2K_API_KEY"),
        "secret": os.environ.get("BYBIT_2K_API_SECRET")
    },
    {
        "name": "1k->5k Projekt",
        "key": os.environ.get("BYBIT_1K_API_KEY"),
        "secret": os.environ.get("BYBIT_1K_API_SECRET")
    },
    {
        "name": "Blofin",
        "key": os.environ.get("BLOFIN_API_KEY"),
        "secret": os.environ.get("BLOFIN_API_SECRET"),
        "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")
    }
]

# 💵 Startkapital zur Berechnung von PnL
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
    "Blofin": 1492.00
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

    account_data = []
    total_balance = 0.0
    total_start = sum(startkapital.values())
    failed_apis = []
    positions_all = []

    for acc in subaccounts:
        name = acc["name"]
        try:
            if "Blofin" in name:
                client = BloFinClient(api_key=acc["key"], api_secret=acc["secret"], passphrase=acc["passphrase"])
                balances = client.get_account_summary()
                usdt = float(balances["data"]["totalEquity"])
                status = "✅"
                positions = []
            else:
                session_bybit = HTTP(api_key=acc["key"], api_secret=acc["secret"])
                wallet_data = session_bybit.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                usdt = 0.0
                for acc_data in wallet_data:
                    for coin in acc_data["coin"]:
                        if coin["coin"] == "USDT":
                            usdt += float(coin["walletBalance"])
                status = "✅"
                positions = session_bybit.get_positions(category="linear")["result"]["list"]
                positions_all.extend([(name, p) for p in positions if float(p.get("size", 0)) > 0])
        except Exception:
            usdt = 0.0
            status = "❌"
            positions = []
            failed_apis.append(name)

        pnl_value = usdt - startkapital.get(name, 0)
        pnl_percent = (pnl_value / startkapital.get(name, 1)) * 100

        account_data.append({
            "name": name,
            "status": status,
            "balance": usdt,
            "start": startkapital.get(name, 0),
            "pnl": pnl_value,
            "pnl_percent": pnl_percent,
            "positions": positions
        })

        total_balance += usdt

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100 if total_start > 0 else 0

    # 📊 Chart für Übersicht
    chart_labels = [a["name"] for a in account_data]
    chart_values = [a["pnl_percent"] for a in account_data]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(chart_labels, chart_values, color=['green' if val >= 0 else 'red' for val in chart_values])
    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_ylabel("PNL (%)")
    ax.set_title("Strategie Performance")
    for i, bar in enumerate(bars):
        value = chart_values[i]
        raw = account_data[i]["pnl"]
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (1 if value >= 0 else -3),
                f"{value:+.1f}%\n(${raw:+.2f})",
                ha='center', va='bottom' if value >= 0 else 'top', fontsize=8)
    fig.tight_layout()
    chart_path = "static/chart.png"
    fig.savefig(chart_path)
    plt.close(fig)

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path=chart_path,
                           positions_all=positions_all,
                           now=datetime.utcnow)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))
