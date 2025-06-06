import os
import logging
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient

app = Flask(__name__)
app.secret_key = 'supergeheim'
logging.basicConfig(level=logging.INFO)

users = {
    "admin": generate_password_hash("deinpasswort123")
}

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
    {"name": "Blofin", "key": os.getenv("BLOFIN_API_KEY"), "secret": os.getenv("BLOFIN_API_SECRET"), "passphrase": os.getenv("BLOFIN_API_PASSPHRASE")}
]

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
    positions_all = []
    total_balance = 0.0
    total_start = sum(startkapital.values())

    for acc in subaccounts:
        name = acc["name"]
        try:
            if name == "Blofin":
                client = BloFinClient(api_key=acc["key"], api_secret=acc["secret"], passphrase=acc["passphrase"])
                res = client.wallet_get_currency_balance("USDT")
                usdt = float(res['data']['available'])
                positions = []
            else:
                client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
                wallet = client.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                usdt = sum(float(c["walletBalance"]) for x in wallet for c in x["coin"] if c["coin"] == "USDT")
                pos = client.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
                positions = [p for p in pos if float(p.get("size", 0)) > 0]
                for p in positions:
                    positions_all.append((name, p))
            status = "✅"
        except Exception as e:
            logging.error(f"Fehler bei {name}: {e}")
            usdt = 0.0
            positions = []
            status = "❌"

        start = startkapital.get(name, 0)
        pnl = usdt - start
        pnl_percent = (pnl / start) * 100 if start else 0

        account_data.append({
            "name": name,
            "status": status,
            "balance": usdt,
            "start": start,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "positions": positions
        })

        total_balance += usdt

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100 if total_start else 0

    # 📊 Chart
    labels = [a["name"] for a in account_data]
    values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
    ax.axhline(0, color='black')
    for i, bar in enumerate(bars):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 0.95,
                f"{values[i]:+.1f}%\n(${account_data[i]['pnl']:+.2f})",
                ha='center', va='bottom' if values[i] >= 0 else 'top', fontsize=8)
    fig.tight_layout()
    chart_path = "static/chart.png"
    fig.savefig(chart_path)
    plt.close(fig)

    # 🕒 Zeitstempel in MEZ
    berlin_time = datetime.now(pytz.timezone('Europe/Berlin')).strftime('%d.%m.%Y %H:%M')

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path=chart_path,
                           positions_all=positions_all,
                           timestamp=berlin_time)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))
