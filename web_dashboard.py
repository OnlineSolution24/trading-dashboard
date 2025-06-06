import os
import time
import hmac
import hashlib
import requests
import logging
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = 'supergeheim'
logging.basicConfig(level=logging.INFO)

users = {
    "admin": generate_password_hash("deinpasswort123")
}

subaccounts = [
    {"name": "Blofin", "key": os.environ.get("BLOFIN_API_KEY"), "secret": os.environ.get("BLOFIN_API_SECRET"), "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")}
]

startkapital = {
    "Blofin": 1492.00
}

def get_blofin_balance(api_key, api_secret, passphrase):
    url = "https://api.blofin.com/api/v1/account/balance"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    payload = ""

    pre_hash = f"{timestamp}{method}/api/v1/account/balance{payload}"
    signature = hmac.new(api_secret.encode(), pre_hash.encode(), hashlib.sha256).hexdigest()

    headers = {
        "ACCESS-KEY": api_key,
        "ACCESS-SIGN": signature,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": passphrase
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return float(data["data"]["totalEquity"])
    else:
        raise Exception(f"BloFin API-Fehler: {response.text}")

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
    positions_all = []
    failed_apis = []

    for acc in subaccounts:
        name = acc["name"]
        try:
            if name == "Blofin":
                usdt = get_blofin_balance(acc["key"], acc["secret"], acc["passphrase"])
                positions = []
                status = "✅"
            else:
                raise Exception("Unbekannter Subaccount")
        except Exception as e:
            logging.error(f"Fehler bei {name}: {str(e)}")
            usdt = 0.0
            positions = []
            status = "❌"
            failed_apis.append(name)

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

    labels = [a["name"] for a in account_data]
    values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
    ax.axhline(0, color='black')
    for i, bar in enumerate(bars):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (1 if values[i] >= 0 else -3),
                f"{values[i]:+.1f}%\n(${account_data[i]['pnl']:+.2f})",
                ha='center', va='bottom' if values[i] >= 0 else 'top', fontsize=8)
    fig.tight_layout()
    chart_path = "static/chart.png"
    fig.savefig(chart_path)
    plt.close(fig)

    mez = pytz.timezone("Europe/Berlin")
    now_berlin = datetime.now(mez)

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path=chart_path,
                           positions_all=positions_all,
                           now=now_berlin)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
