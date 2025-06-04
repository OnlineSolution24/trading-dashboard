import os
import json
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from flask_caching import Cache  # Für Caching

# Flask Setup
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'sicherer_schlüssel')

# Caching Setup
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

# Benutzer
users = {
    "husky125": generate_password_hash("Ideal250!")
}

# Startwerte je Account
starting_balances = {
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

# Subaccounts
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

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and check_password_hash(users[username], password):
            session['user'] = username
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Login fehlgeschlagen.")
    return render_template('login.html')

@app.route('/dashboard')
@cache.cached(timeout=60)  # Cache für 60 Sekunden
def dashboard():
    if "user" not in session:
        return redirect(url_for('login'))

    results = []
    total_current = 0
    total_start = sum(starting_balances.values())

    for sub in subaccounts:
        name = sub['name']
        balance = 0
        pnl = 0
        api_ok = False
        positions = []
        error_msg = None

        try:
            if name == "Blofin":
                client = BloFinClient(sub["key"], sub["secret"], sub["passphrase"])
                resp = client.account.get_balance(account_type="futures")
                if "data" in resp:
                    for b in resp["data"]:
                        if b["currency"] == "USDT":
                            balance = float(b["available"])
                            api_ok = True
                            break
            else:
                session_bybit = HTTP(api_key=sub["key"], api_secret=sub["secret"])
                balance_data = session_bybit.get_wallet_balance(accountType="UNIFIED")
                if "result" in balance_data:
                    for item in balance_data["result"]["list"]:
                        for c in item["coin"]:
                            if c["coin"] == "USDT":
                                balance += float(c["availableToWithdraw"])
                                api_ok = True

                    pos = session_bybit.get_positions(category="linear", settleCoin="USDT")
                    if "result" in pos:
                        positions = [{
                            "symbol": p["symbol"],
                            "size": float(p["size"]),
                            "pnl": float(p["unrealisedPnl"])
                        } for p in pos["result"]["list"] if float(p["size"]) != 0]

        except Exception as e:
            error_msg = str(e)
            api_ok = False

        pnl = balance - starting_balances.get(name, 0)
        pnl_percent = (pnl / starting_balances.get(name, 1)) * 100 if starting_balances.get(name, 0) != 0 else 0
        total_current += balance

        results.append({
            "name": name,
            "balance": f"{balance:.2f}",
            "start": f"{starting_balances.get(name, 0):.2f}",
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "pnl_str": f"{pnl:+.2f}",
            "pnl_percent_str": f"{pnl_percent:+.2f}",
            "positions": positions,
            "api_ok": api_ok,
            "error_msg": error_msg
        })

    # Keine Google Sheets-Anbindung mehr (deaktiviert)
    day1 = day7 = day30 = None

    total_pnl = total_current - total_start
    total_pnl_percent = (total_pnl / total_start) * 100 if total_start != 0 else 0

    # Chart erstellen
    chart_path = "static/chart.png"
    os.makedirs("static", exist_ok=True)
    if results:
        labels = [r["name"] for r in results]
        values = [r["pnl_percent"] for r in results]
        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(labels, values, color=["green" if v > 0 else "red" for v in values])
        ax.set_ylabel("PNL %")
        plt.xticks(rotation=45)
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 0.98, 
                   f"{val:+.2f}%", ha='center', va='bottom', fontsize=8)
        fig.tight_layout()
        plt.savefig(chart_path, bbox_inches='tight', dpi=100)
        plt.close()

    return render_template("dashboard.html",
        subaccounts=results,
        total_balance=f"{total_current:.2f}",
        total_pnl=total_pnl,
        total_pnl_str=f"{total_pnl:+.2f}",
        total_pnl_percent=total_pnl_percent,
        total_pnl_percent_str=f"{total_pnl_percent:+.2f}%",
        pnl_1d=day1 if day1 else 0,
        pnl_1d_str=f"{day1:+.2f}" if day1 else "N/A",
        pnl_1d_percent=0,
        pnl_7d=day7 if day7 else 0,
        pnl_7d_str=f"{day7:+.2f}" if day7 else "N/A",
        pnl_7d_percent=0,
        pnl_30d=day30 if day30 else 0,
        pnl_30d_str=f"{day30:+.2f}" if day30 else "N/A",
        pnl_30d_percent=0,
        chart_path=chart_path
    )

@app.route('/logout')
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
