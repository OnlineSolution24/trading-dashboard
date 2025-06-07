import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
import pandas as pd
import logging

app = Flask(__name__)
app.secret_key = 'supergeheim'
logging.basicConfig(level=logging.INFO)

# Timezone MEZ
tz = pytz.timezone('Europe/Berlin')

# Benutzer
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# Subaccounts & API
subaccounts = [
    {"name": "Incubatorzone", "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET")},
    {"name": "Memestrategies", "key": os.environ.get("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_MEMESTRATEGIES_API_SECRET")},
    {"name": "Ethapestrategies", "key": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_SECRET")},
    {"name": "Altsstrategies", "key": os.environ.get("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ALTSSTRATEGIES_API_SECRET")},
    {"name": "Solstrategies", "key": os.environ.get("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_SOLSTRATEGIES_API_SECRET")},
    {"name": "Btcstrategies", "key": os.environ.get("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_BTCSTRATEGIES_API_SECRET")},
    {"name": "Corestrategies", "key": os.environ.get("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_CORESTRATEGIES_API_SECRET")},
    {"name": "2k->10k Projekt", "key": os.environ.get("BYBIT_2K_API_KEY"), "secret": os.environ.get("BYBIT_2K_API_SECRET")},
    {"name": "1k->5k Projekt", "key": os.environ.get("BYBIT_1K_API_KEY"), "secret": os.environ.get("BYBIT_1K_API_SECRET")},
    {"name": "Blofin", "key": os.environ.get("BLOFIN_API_KEY"), "secret": os.environ.get("BLOFIN_API_SECRET"), "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")}
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
            client = HTTP(api_key=acc["key"], api_secret=acc["secret"], recv_window=10000)
            wallet = client.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
            usdt = sum(float(c["walletBalance"]) for x in wallet for c in x["coin"] if c["coin"] == "USDT")

            pos = client.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
            all_positions = client.get_positions(category="linear")["result"]["list"]
            positions = [p for p in all_positions if float(p.get("size", 0)) > 0]
            for p in positions:
                positions_all.append((name, p))
            status = "✅"
        except Exception as e:
            logging.error(f"Fehler bei {name}: {e}")
            usdt = 0.0
            status = "❌"

        pnl = usdt - startkapital.get(name, 0)
        pnl_percent = (pnl / startkapital.get(name, 1)) * 100

        account_data.append({
            "name": name,
            "status": status,
            "balance": usdt,
            "start": startkapital.get(name, 0),
            "pnl": pnl,
            "pnl_percent": pnl_percent
        })

        total_balance += usdt

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # 🔢 Strategie-Chart
    labels = [a["name"] for a in account_data]
    values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
    ax.axhline(0, color='black')
    ax.set_xticklabels(labels, rotation=45, ha="right")
    for i, bar in enumerate(bars):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                f"{values[i]:+.1f}%", ha='center', va='bottom' if values[i] >= 0 else 'top', fontsize=8)
    chart_path_strategien = "static/chart_strategien.png"
    fig.tight_layout()
    plt.savefig(chart_path_strategien)
    plt.close()

    # 🔢 Projekt-Chart
    projekte = {
        "10k->1Mio": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
        "2k->10k": ["2k->10k Projekt"],
        "1k->5k": ["1k->5k Projekt"],
        "7-Tage Performer": ["Blofin"]
    }

    projekt_pnls = {}
    for name, members in projekte.items():
        start = sum(startkapital[m] for m in members)
        balance = sum(a["balance"] for a in account_data if a["name"] in members)
        pnl = balance - start
        projekt_pnls[name] = (pnl / start) * 100

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(list(projekt_pnls.keys()), list(projekt_pnls.values()),
                  color=["green" if v >= 0 else "red" for v in projekt_pnls.values()])
    ax.axhline(0, color='black')
    chart_path_projekte = "static/chart_projekte.png"
    fig.tight_layout()
    plt.savefig(chart_path_projekte)
    plt.close()

    # 📈 Zeitlicher Verlauf (simuliert)
    verlauf_daten = []
    heute = datetime.now(tz)
    for i in range(10):
        datum = heute - timedelta(days=9 - i)
        faktor = 1 + (i - 5) * 0.01
        verlauf_daten.append({
            "datum": datum,
            "balance": total_balance * faktor,
            "pnl": total_pnl * faktor
        })

    df = pd.DataFrame(verlauf_daten)
    verlauf_chart_path_balance = "static/verlauf_balance.png"
    verlauf_chart_path_pnl = "static/verlauf_pnl.png"

    plt.figure(figsize=(10, 4))
    plt.plot(df["datum"], df["balance"], marker='o')
    plt.title("Gesamtbalance Verlauf")
    plt.xlabel("Datum")
    plt.ylabel("Balance ($)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(verlauf_chart_path_balance)
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(df["datum"], df["pnl"], color='orange', marker='o')
    plt.title("Gesamt-PnL Verlauf")
    plt.xlabel("Datum")
    plt.ylabel("PnL ($)")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(verlauf_chart_path_pnl)
    plt.close()

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path_strategien=chart_path_strategien,
                           chart_path_projekte=chart_path_projekte,
                           verlauf_chart_path_balance=verlauf_chart_path_balance,
                           verlauf_chart_path_pnl=verlauf_chart_path_pnl,
                           positions_all=positions_all,
                           now=datetime.now(tz).strftime('%d.%m.%Y %H:%M'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

import os

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Render setzt PORT automatisch
    app.run(host='0.0.0.0', port=port, debug=True)

