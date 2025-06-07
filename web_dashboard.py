import os
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import pytz
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP

# 🌍 Setup
app = Flask(__name__)
app.secret_key = 'supergeheim'
logging.basicConfig(level=logging.INFO)

# 👥 Benutzer
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# 🔑 API-Zugangsdaten aus Umgebungsvariablen
subaccounts = [
    {"name": "Incubatorzone", "key": os.getenv("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.getenv("BYBIT_INCUBATORZONE_API_SECRET")},
    {"name": "Memestrategies", "key": os.getenv("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_MEMESTRATEGIES_API_SECRET")},
    {"name": "Ethapestrategies", "key": os.getenv("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ETHAPESTRATEGIES_API_SECRET")},
    {"name": "Altsstrategies", "key": os.getenv("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ALTSSTRATEGIES_API_SECRET")},
    {"name": "Solstrategies", "key": os.getenv("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_SOLSTRATEGIES_API_SECRET")},
    {"name": "Btcstrategies", "key": os.getenv("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_BTCSTRATEGIES_API_SECRET")},
    {"name": "Corestrategies", "key": os.getenv("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_CORESTRATEGIES_API_SECRET")},
    {"name": "2k->10k Projekt", "key": os.getenv("BYBIT_2K_API_KEY"), "secret": os.getenv("BYBIT_2K_API_SECRET")},
    {"name": "1k->5k Projekt", "key": os.getenv("BYBIT_1K_API_KEY"), "secret": os.getenv("BYBIT_1K_API_SECRET")}
]

# 💰 Startkapital
startkapital = {
    "Incubatorzone": 400.00,
    "Memestrategies": 800.00,
    "Ethapestrategies": 1200.00,
    "Altsstrategies": 1200.00,
    "Solstrategies": 1713.81,
    "Btcstrategies": 1923.00,
    "Corestrategies": 2000.56,
    "2k->10k Projekt": 2000.00,
    "1k->5k Projekt": 1000.00
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
    total_start = sum(startkapital.values())
    total_balance = 0

    for acc in subaccounts:
        name = acc["name"]
        try:
            client = HTTP(api_key=acc["key"], api_secret=acc["secret"])
            wallet = client.get_wallet_balance(accountType="UNIFIED")
            usdt = 0.0
            for item in wallet["result"]["list"]:
                for coin in item["coin"]:
                    if coin["coin"] == "USDT":
                        usdt += float(coin["walletBalance"])

            # Positionsdaten
            pos_result = client.get_positions(category="linear", symbol="BTCUSDT")  # Dummy-Symbol notwendig!
            positions = [p for p in pos_result["result"]["list"] if float(p.get("size", 0)) > 0]
            for p in positions:
                positions_all.append((name, p))
            status = "✅"

        except Exception as e:
            logging.error(f"Fehler bei {name}: {e}")
            usdt = 0.0
            positions = []
            status = "❌"

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

    # 🔢 Gesamt
    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # 📊 Strategien Chart
    labels = [a["name"] for a in account_data]
    values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.axhline(0, color='black')
    for i, bar in enumerate(bars):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{values[i]:+.1f}%", ha='center', va='bottom' if values[i] >= 0 else 'top')
    fig.tight_layout()
    chart_path = "static/chart.png"
    fig.savefig(chart_path)
    plt.close(fig)

    # 🕒 Zeitstempel (MEZ)
    mez = pytz.timezone("Europe/Berlin")
    now = datetime.now(mez).strftime("%d.%m.%Y %H:%M:%S")

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path_strategien=chart_path,
                           chart_path_projekte=chart_path,  # Optional: separater Projektchart möglich
                           positions_all=positions_all,
                           now=now)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=10000)
