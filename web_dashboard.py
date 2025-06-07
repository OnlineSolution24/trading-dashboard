# web_dashboard.py
import os
import time
import hmac
import hashlib
import requests
import logging
from flask import Flask, render_template
from datetime import datetime
import pytz
import matplotlib.pyplot as plt

# Flask Setup
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

CHART_PATH_STRATEGIEN = "static/chart_strategien.png"
CHART_PATH_PROJEKTE = "static/chart_projekte.png"

accounts = [
    {
        "name": "7 Tage Performer",
        "api_key": os.getenv("BLOFIN_API_KEY"),
        "api_secret": os.getenv("BLOFIN_API_SECRET"),
        "type": "blofin",
        "start": 1000
    },
    {
        "name": "1k->5k Projekt",
        "api_key": os.getenv("BYBIT_KEY_1"),
        "api_secret": os.getenv("BYBIT_SECRET_1"),
        "type": "bybit",
        "start": 1000
    }
    # Weitere Accounts kannst du hinzufügen
]

def generate_blofin_signature(secret_key, timestamp, method, path, body=""):
    prehash = timestamp + method.upper() + path + body
    signature = hmac.new(secret_key.encode(), prehash.encode(), hashlib.sha256).hexdigest()
    return signature

def create_chart(data, labels, title, filename):
    fig, ax = plt.subplots()
    bars = ax.bar(labels, data, color=['green' if x >= 0 else 'red' for x in data])
    ax.set_title(title)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.2f}', xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points", ha='center', va='bottom')
    plt.tight_layout()
    plt.savefig(filename)
    plt.close()

@app.route("/dashboard")
def dashboard():
    results = []
    positions_all = []
    projektdaten = {
        "10k->1Mio Projekt": [],
        "2k->10k Projekt": [],
        "1k->5k Projekt": [],
        "7 Tage Performer": []
    }

    for acc in accounts:
        try:
            name = acc["name"]
            acc_type = acc["type"]
            start = acc["start"]
            balance = 0.0

            if acc_type == "blofin":
                ts = str(int(time.time() * 1000))
                path = "/api/v1/private/account/assets"
                sign = generate_blofin_signature(acc["api_secret"], ts, "GET", path)
                headers = {
                    "ACCESS-KEY": acc["api_key"],
                    "ACCESS-SIGN": sign,
                    "ACCESS-TIMESTAMP": ts,
                    "Content-Type": "application/json"
                }
                url = f"https://api.blofin.com{path}"
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    usdt_bal = sum(float(a["availableBalance"]) for a in data["data"] if a["asset"] == "USDT")
                    balance = usdt_bal
                else:
                    raise Exception(f"Blofin API Error: {resp.status_code}")

            elif acc_type == "bybit":
                # Beispielwert für Demo-Zwecke
                balance = 1200.0
                positions_all.append((name, {
                    "symbol": "BTCUSDT",
                    "size": 0.01,
                    "avgPrice": 50000,
                    "unrealisedPnl": 20.0,
                    "side": "Buy"
                }))

            pnl = balance - start
            pnl_percent = (pnl / start * 100) if start > 0 else 0

            if "1k" in name:
                projektdaten["1k->5k Projekt"].append(pnl)
            elif "2k" in name:
                projektdaten["2k->10k Projekt"].append(pnl)
            elif "Performer" in name:
                projektdaten["7 Tage Performer"].append(pnl)
            else:
                projektdaten["10k->1Mio Projekt"].append(pnl)

            results.append({
                "name": name,
                "balance": balance,
                "start": start,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "status": "Aktiv"
            })

        except Exception as e:
            logging.error(f"Fehler bei {acc['name']}: {e}")

    total_start = sum(a["start"] for a in results)
    total_balance = sum(a["balance"] for a in results)
    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start * 100) if total_start > 0 else 0

    create_chart([a["pnl"] for a in results],
                 [a["name"] for a in results],
                 "Strategien Performance", CHART_PATH_STRATEGIEN)

    create_chart([sum(vals) for vals in projektdaten.values()],
                 list(projektdaten.keys()),
                 "Projekt Performance", CHART_PATH_PROJEKTE)

    now = datetime.now(pytz.timezone("Europe/Berlin")).strftime("%d.%m.%Y %H:%M:%S")

    return render_template("dashboard.html",
                           accounts=results,
                           chart_path_strategien=CHART_PATH_STRATEGIEN,
                           chart_path_projekte=CHART_PATH_PROJEKTE,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           positions_all=positions_all,
                           now=now)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000, debug=True)
