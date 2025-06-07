import os
import time
import logging
import pytz
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from flask import Flask, render_template
from pybit.unified_trading import HTTP

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)

# Flask App
app = Flask(__name__)

# Konstanten
STARTKAPITAL = 13729.37
TZ = pytz.timezone("Europe/Berlin")

# Bybit Subaccounts (Name, API, Secret)
bybit_accounts = [
    ("Incubatorzone", "API_KEY1", "SECRET1"),
    ("Memestrategies", "API_KEY2", "SECRET2"),
    ("Ethapestrategies", "API_KEY3", "SECRET3"),
    ("Altsstrategies", "API_KEY4", "SECRET4"),
    ("Solstrategies", "API_KEY5", "SECRET5"),
    ("Btcstrategies", "API_KEY6", "SECRET6"),
    ("Corestrategies", "API_KEY7", "SECRET7"),
    ("2k->10k Projekt", "API_KEY8", "SECRET8"),
    ("1k->5k Projekt", "API_KEY9", "SECRET9")
]

# Blofin Account (Einzelaccount)
blofin_account = {
    "name": "7 Tage Performer",
    "api_key": "YOUR_BLOFIN_API_KEY",
    "api_secret": "YOUR_BLOFIN_API_SECRET"
}


def get_bybit_balance_and_positions(name, key, secret):
    try:
        session = HTTP(api_key=key, api_secret=secret)
        balance = session.get_wallet_balance(accountType="UNIFIED")["result"]["list"][0]["totalWalletBalance"]
        positions = session.get_positions(category="linear")["result"]["list"]
        open_positions = [
            {
                "symbol": p["symbol"],
                "size": float(p["size"]),
                "avgPrice": float(p["avgPrice"]),
                "unrealisedPnl": float(p["unrealisedPnl"]),
                "side": p["side"]
            }
            for p in positions if float(p["size"]) > 0
        ]
        return balance, open_positions, "OK"
    except Exception as e:
        logging.error(f"Fehler bei {name}: {e}")
        return 0.0, [], "Fehler"


def get_blofin_balance():
    import requests
    import hmac
    import hashlib

    try:
        url = "https://api.blofin.com/api/v1/account/assets"
        timestamp = str(int(time.time() * 1000))
        sign_payload = timestamp + "GET" + "/api/v1/account/assets"
        signature = hmac.new(
            blofin_account["api_secret"].encode(),
            sign_payload.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "ACCESS-KEY": blofin_account["api_key"],
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp
        }

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Http status code is not 200. (ErrCode: {response.status_code})")

        assets = response.json()["data"]
        total_usd = sum(float(a["usdValue"]) for a in assets)
        return total_usd, "OK"
    except Exception as e:
        logging.error(f"Fehler bei {blofin_account['name']}: {e}")
        return 0.0, "Fehler"


def calculate_pnl(balance, start):
    pnl = balance - start
    pnl_percent = (pnl / start) * 100 if start > 0 else 0
    return pnl, pnl_percent


def generate_chart(data, filename, title):
    df = pd.DataFrame(data)
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(df["Name"], df["PNL"], color=["green" if v >= 0 else "red" for v in df["PNL"]])
    ax.set_title(title)
    ax.set_ylabel("PNL ($)")
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df["Name"], rotation=45, ha="right")
    for bar in bars:
        yval = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, yval, f"{yval:.0f}", ha='center', va='bottom', fontsize=8)
    plt.tight_layout()
    path = f"static/{filename}"
    fig.savefig(path)
    plt.close()
    return path


@app.route("/")
@app.route("/dashboard")
def dashboard():
    accounts = []
    positions_all = []
    projects = {
        "10k->1Mio Projekt": [],
        "2k->10k Projekt": [],
        "1k->5k Projekt": [],
        "7 Tage Performer": []
    }

    # Daten sammeln
    for name, key, secret in bybit_accounts:
        start = 1000 if "Projekt" not in name else (2000 if "2k" in name else 1000)
        balance, positions, status = get_bybit_balance_and_positions(name, key, secret)
        pnl, pnl_percent = calculate_pnl(balance, start)
        accounts.append({
            "name": name,
            "start": start,
            "balance": balance,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "status": status
        })
        for pos in positions:
            positions_all.append((name, pos))

        # Projektzuordnung
        if name in ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"]:
            projects["10k->1Mio Projekt"].append(pnl)
        elif "2k->10k" in name:
            projects["2k->10k Projekt"].append(pnl)
        elif "1k->5k" in name:
            projects["1k->5k Projekt"].append(pnl)

    # Blofin
    blofin_balance, blofin_status = get_blofin_balance()
    blofin_start = 1000
    blofin_pnl, blofin_pnl_percent = calculate_pnl(blofin_balance, blofin_start)
    accounts.append({
        "name": "7 Tage Performer",
        "start": blofin_start,
        "balance": blofin_balance,
        "pnl": blofin_pnl,
        "pnl_percent": blofin_pnl_percent,
        "status": blofin_status
    })
    projects["7 Tage Performer"].append(blofin_pnl)

    # Summen
    total_start = sum(a["start"] for a in accounts)
    total_balance = sum(a["balance"] for a in accounts)
    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # Charts generieren
    chart_path_strategien = generate_chart(
        [{"Name": a["name"], "PNL": a["pnl"]} for a in accounts],
        "chart_strategien.png",
        "Strategien PNL"
    )
    chart_path_projekte = generate_chart(
        [{"Name": k, "PNL": sum(v)} for k, v in projects.items()],
        "chart_projekte.png",
        "Projektübersicht"
    )

    return render_template("dashboard.html",
                           accounts=accounts,
                           positions_all=positions_all,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path_strategien=chart_path_strategien,
                           chart_path_projekte=chart_path_projekte,
                           now=datetime.now(TZ).strftime("%d.%m.%Y %H:%M"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=10000)
