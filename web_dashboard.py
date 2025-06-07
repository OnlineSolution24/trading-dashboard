import os
import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, render_template
from datetime import datetime
import pytz
import logging
from pybit.unified_trading import HTTP
from blofin.client import BloFinClient  # Stelle sicher, dass du blofin-sdk installiert hast

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)

# Flask App
app = Flask(__name__)

# BYBIT Subaccounts
subaccounts = [
    {"name": "Incubatorzone", "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET")},
    {"name": "Memestrategies", "key": os.environ.get("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_MEMESTRATEGIES_API_SECRET")},
    {"name": "Ethapestrategies", "key": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_SECRET")},
    {"name": "Altsstrategies", "key": os.environ.get("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_ALTSSTRATEGIES_API_SECRET")},
    {"name": "Solstrategies", "key": os.environ.get("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_SOLSTRATEGIES_API_SECRET")},
    {"name": "Btcstrategies", "key": os.environ.get("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_BTCSTRATEGIES_API_SECRET")},
    {"name": "Corestrategies", "key": os.environ.get("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.environ.get("BYBIT_CORESTRATEGIES_API_SECRET")},
    {"name": "2k->10k Projekt", "key": os.environ.get("BYBIT_2K_API_KEY"), "secret": os.environ.get("BYBIT_2K_API_SECRET")},
    {"name": "1k->5k Projekt", "key": os.environ.get("BYBIT_1K_API_KEY"), "secret": os.environ.get("BYBIT_1K_API_SECRET")}
]

# Blofin Zugangsdaten
blofin_key = os.environ.get("BLOFIN_API_KEY")
blofin_secret = os.environ.get("BLOFIN_API_SECRET")
blofin_passphrase = os.environ.get("BLOFIN_API_PASSPHRASE")

# Zeitzone
tz = pytz.timezone('Europe/Berlin')

def fetch_bybit_data(name, key, secret):
    if not key or not secret:
        logging.error(f"{name}: API-Key oder Secret fehlt.")
        return None, None, "Fehlende Zugangsdaten"

    try:
        session = HTTP(api_key=key, api_secret=secret)
        balance = session.get_wallet_balance(accountType="UNIFIED")["result"]["list"][0]
        total_equity = float(balance["totalEquity"])
        total_margin = float(balance["totalMarginBalance"])
        return total_equity, total_margin, "OK"
    except Exception as e:
        logging.error(f"Fehler bei {name}: {e}")
        return None, None, str(e)

def fetch_blofin_data():
    if not all([blofin_key, blofin_secret, blofin_passphrase]):
        logging.error("Blofin Zugangsdaten unvollständig")
        return None

    try:
        client = BloFinClient(
            api_key=blofin_key,
            api_secret=blofin_secret,
            passphrase=blofin_passphrase,
        )
        resp = client.get_wallet_info()
        return float(resp["data"]["totalEquity"])
    except Exception as e:
        logging.error(f"Blofin Fehler: {e}")
        return None

@app.route("/")
@app.route("/dashboard")
def dashboard():
    accounts_data = []
    total_start = 0
    total_balance = 0

    for acc in subaccounts:
        name = acc["name"]
        key = acc["key"]
        secret = acc["secret"]
        start_capital = 1000  # Placeholder, ggf. aus Datei holen

        balance, _, status = fetch_bybit_data(name, key, secret)

        if balance is not None:
            pnl = balance - start_capital
            pnl_percent = (pnl / start_capital) * 100
            accounts_data.append({
                "name": name,
                "start": start_capital,
                "balance": balance,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "status": status
            })
            total_start += start_capital
            total_balance += balance
        else:
            accounts_data.append({
                "name": name,
                "start": start_capital,
                "balance": 0,
                "pnl": 0,
                "pnl_percent": 0,
                "status": status
            })

    # Blofin hinzufügen
    blofin_balance = fetch_blofin_data()
    if blofin_balance:
        start_blofin = 1000
        pnl = blofin_balance - start_blofin
        pnl_percent = (pnl / start_blofin) * 100
        accounts_data.append({
            "name": "7 Tage Performer",
            "start": start_blofin,
            "balance": blofin_balance,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "status": "OK"
        })
        total_start += start_blofin
        total_balance += blofin_balance

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100 if total_start else 0

    # Diagramm generieren (dummy)
    labels = [a["name"] for a in accounts_data]
    values = [a["pnl_percent"] for a in accounts_data]

    fig, ax = plt.subplots(figsize=(10, 4))
    bars = ax.bar(labels, values, color=["green" if v >= 0 else "red" for v in values])
    ax.set_ylabel("PnL (%)")
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_title("Strategien Performance")
    plt.tight_layout()
    chart_path_strategien = "static/chart_strategien.png"
    fig.savefig(chart_path_strategien)
    plt.close()

    return render_template("dashboard.html",
                           accounts=accounts_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path_strategien=chart_path_strategien,
                           chart_path_projekte="static/chart_projekte.png",  # ggf. später ergänzen
                           now=datetime.now(tz).strftime('%d.%m.%Y %H:%M:%S'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
