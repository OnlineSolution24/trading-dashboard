302-4144595-6171562import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
import pytz
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
import logging

app = Flask(__name__)
app.secret_key = 'supergeheim'

# 🛡️ Logging für Fehleranalyse
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# 🔐 Benutzerverwaltung
users = {
    "admin": generate_password_hash("deinpasswort123")
}

# 🌐 Subaccounts (API Keys via Umgebungsvariablen)
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
    {"name": "Blofin", "key": os.getenv("BLOFIN_API_KEY"), "secret": os.getenv("BLOFIN_API_SECRET")}
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

# 📁 Projektgruppen
projekte = {
    "10k → 1M Projekt": ["Incubatorzone", "Memestrategies", "Ethapestrategies", "Altsstrategies", "Solstrategies", "Btcstrategies", "Corestrategies"],
    "2k → 10k Projekt": ["2k->10k Projekt"],
    "1k → 5k Projekt": ["1k->5k Projekt"],
    "7-Tage Performer": ["Blofin"]
}

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["username"]
        pw = request.form["password"]
        if user in users and check_password_hash(users[user], pw):
            session["user"] = user
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Login fehlgeschlagen.")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    account_data, total_balance, total_start, positions_all = [], 0.0, sum(startkapital.values()), []

    for acc in subaccounts:
        name, key, secret = acc["name"], acc["key"], acc["secret"]
        balance, positions = 0.0, []
        try:
            client = HTTP(api_key=key, api_secret=secret)
            wallet = client.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
            balance = sum(float(c["walletBalance"]) for x in wallet for c in x["coin"] if c["coin"] == "USDT")

            pos = client.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
            positions = [p for p in pos if float(p.get("size", 0)) > 0]
            for p in positions:
                p["side"] = p.get("side", "unknown")
                positions_all.append((name, p))
        except Exception as e:
            logger.error(f"Fehler bei {name}: {e}")

        start = startkapital.get(name, 0)
        pnl = balance - start
        pnl_percent = (pnl / start) * 100 if start else 0

        account_data.append({
            "name": name,
            "balance": balance,
            "start": start,
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "positions": positions
        })
        total_balance += balance

    total_pnl = total_balance - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # 📈 Subaccount Chart
    sub_labels = [a["name"] for a in account_data]
    sub_values = [a["pnl_percent"] for a in account_data]
    fig, ax = plt.subplots(figsize=(14, 6))
    bars = ax.bar(sub_labels, sub_values, color=["green" if v >= 0 else "red" for v in sub_values])
    ax.axhline(0, color='black')
    ax.set_title("Strategie Performance")
    for i, bar in enumerate(bars):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (1 if sub_values[i] >= 0 else -3),
                f"{sub_values[i]:+.1f}%\n(${account_data[i]['pnl']:+.2f})", ha='center',
                va='bottom' if sub_values[i] >= 0 else 'top', fontsize=8)
    fig.tight_layout()
    chart_path = "static/chart.png"
    fig.savefig(chart_path)
    plt.close(fig)

    # 📈 Projekt Chart
    proj_labels, proj_pnls = [], []
    for proj, subs in projekte.items():
        proj_start = sum(startkapital[s] for s in subs)
        proj_balance = sum(a["balance"] for a in account_data if a["name"] in subs)
        proj_pnl = proj_balance - proj_start
        proj_pnls.append((proj, proj_pnl / proj_start * 100 if proj_start else 0, proj_pnl))
        proj_labels.append(proj)

    fig2, ax2 = plt.subplots(figsize=(10, 4))
    proj_values = [x[1] for x in proj_pnls]
    bars = ax2.bar(proj_labels, proj_values, color=["green" if v >= 0 else "red" for v in proj_values])
    ax2.axhline(0, color="black")
    ax2.set_title("Projekt Performance")
    for i, bar in enumerate(bars):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + (1 if proj_values[i] >= 0 else -3),
                 f"{proj_values[i]:+.1f}%\n(${proj_pnls[i][2]:+.2f})", ha='center',
                 va='bottom' if proj_values[i] >= 0 else 'top', fontsize=8)
    fig2.tight_layout()
    proj_chart_path = "static/projekt_chart.png"
    fig2.savefig(proj_chart_path)
    plt.close(fig2)

    # 🕒 Zeitstempel
    berlin = pytz.timezone("Europe/Berlin")
    timestamp = datetime.now(berlin).strftime("%d.%m.%Y %H:%M")

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_start=total_start,
                           total_balance=total_balance,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_path=chart_path,
                           proj_chart_path=proj_chart_path,
                           positions_all=positions_all,
                           timestamp=timestamp)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))
