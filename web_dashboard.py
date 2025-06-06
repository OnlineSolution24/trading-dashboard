import os
import pytz
import time
import hmac
import hashlib
import requests
import logging
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from datetime import datetime
import pytz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 🌐 Flask App initialisieren
app = Flask(__name__)
app.secret_key = 'supergeheim'
logging.basicConfig(level=logging.INFO)

# 🧑‍💻 Benutzer
users = {
"admin": generate_password_hash("deinpasswort123")
}

# 🪙 Subaccounts (API-Zugang)
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
@@ -56,10 +60,10 @@ def login():
if user in users and check_password_hash(users[user], pw):
session['user'] = user
return redirect(url_for('dashboard'))
        return render_template('login.html', error="Login fehlgeschlagen.")
        else:
            return render_template('login.html', error="Login fehlgeschlagen.")
return render_template('login.html')


@app.route('/dashboard')
def dashboard():
if 'user' not in session:
@@ -69,30 +73,23 @@ def dashboard():
total_balance = 0.0
total_start = sum(startkapital.values())
positions_all = []
    failed_apis = []

for acc in subaccounts:
name = acc["name"]
try:
if name == "Blofin":
                client = BloFinClient(api_key=acc["key"], api_secret=acc["secret"], passphrase=acc["passphrase"])
                balances = client.get_account_balance()
                usdt = float(balances["data"]["totalEquity"])
                positions = []  # Optional: Positionen abrufen, wenn verfügbar

                usdt = get_blofin_balance(acc["key"], acc["secret"], acc["passphrase"])
                positions = []
                status = "✅"
else:
                client = HTTP(api_key=acc["key"], api_secret=acc["secret"], recv_window=15000)
                wallet = client.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                usdt = sum(float(c["walletBalance"]) for x in wallet for c in x["coin"] if c["coin"] == "USDT")
                pos = client.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
                positions = [p for p in pos if float(p.get("size", 0)) > 0]
                for p in positions:
                    positions_all.append((name, p))
            status = "✅"
                raise Exception("Unbekannter Subaccount")
except Exception as e:
            logging.error(f"Fehler bei {name}: {str(e)}")
usdt = 0.0
positions = []
status = "❌"
            logging.error(f"Fehler bei {name}: {str(e)}")
            failed_apis.append(name)

pnl = usdt - startkapital.get(name, 0)
pnl_percent = (pnl / startkapital.get(name, 1)) * 100
@@ -112,10 +109,9 @@ def dashboard():
total_pnl = total_balance - total_start
total_pnl_percent = (total_pnl / total_start) * 100

    # 📈 Chart
labels = [a["name"] for a in account_data]
values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(12, 6))
    fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
ax.axhline(0, color='black')
for i, bar in enumerate(bars):
@@ -127,9 +123,8 @@ def dashboard():
fig.savefig(chart_path)
plt.close(fig)

    # 🕓 Aktuelle Zeit in MEZ (Berlin)
    berlin = pytz.timezone('Europe/Berlin')
    jetzt = datetime.now(berlin).strftime('%d.%m.%Y %H:%M')
    mez = pytz.timezone("Europe/Berlin")
    now_berlin = datetime.now(mez)

return render_template("dashboard.html",
accounts=account_data,
@@ -139,15 +134,12 @@ def dashboard():
total_pnl_percent=total_pnl_percent,
chart_path=chart_path,
positions_all=positions_all,
                           timestamp=jetzt)

                           now=now_berlin)

@app.route('/logout')
def logout():
session.pop('user', None)
return redirect(url_for('login'))


# 🚀 App starten
if __name__ == "__main__":
app.run(host="0.0.0.0", port=10000, debug=True)
