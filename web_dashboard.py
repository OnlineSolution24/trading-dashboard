import os
import json
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
import gspread
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# Flask Setup
app = Flask(__name__)
app.secret_key = 'sicherer_schlüssel'

# Benutzer
users = {
    "admin": generate_password_hash("dein_passwort")
}

# Google Sheets Setup
sheet_id = "1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g"
sheet_tab = "DailyBalances"
json_path = "credentials.json"  # Datei im Root-Ordner ablegen

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

def read_sheet_data(days=1):
    gc = gspread.service_account(json_path)
    sh = gc.open_by_key(sheet_id)
    worksheet = sh.worksheet(sheet_tab)
    rows = worksheet.get_all_records()
    if not rows:
        return None
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)
    filtered = [r for r in rows if datetime.strptime(r["Date"], "%Y-%m-%d") >= cutoff]
    return filtered[-1]["Total"] if filtered else None

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form['username'], request.form['password']
        if u in users and check_password_hash(users[u], p):
            session['user'] = u
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Login fehlgeschlagen.")
    return render_template('login.html')

@app.route('/dashboard')
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
        error = None
        positions = []

        try:
            if name == "Blofin":
                client = BloFinClient(sub["key"], sub["secret"], sub["passphrase"])
                resp = client.account.get_balance(account_type="futures")
                for b in resp["data"]:
                    if b["currency"] == "USDT":
                        balance = float(b["available"])
                        break
            else:
                session_bybit = HTTP(api_key=sub["key"], api_secret=sub["secret"])
                balance_data = session_bybit.get_wallet_balance(accountType="UNIFIED")
                for item in balance_data["result"]["list"]:
                    for c in item["coin"]:
                        if c["coin"] == "USDT":
                            balance += float(c["availableToWithdraw"])

                pos = session_bybit.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
                positions = [{
                    "symbol": p["symbol"],
                    "size": float(p["size"]),
                    "pnl": float(p["unrealisedPnl"])
                } for p in pos if float(p["size"]) != 0]

        except Exception as e:
            error = str(e)

        pnl = balance - starting_balances.get(name, 0)
        pnl_percent = (pnl / starting_balances.get(name, 1)) * 100
        total_current += balance

        results.append({
            "name": name,
            "balance": balance,
            "start": starting_balances.get(name, 0),
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "positions": positions,
            "status": "OK" if not error else "Fehler",
            "error_msg": error
        })

    # Google Sheets Log
    try:
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        gc = gspread.service_account(json_path)
        sh = gc.open_by_key(sheet_id)
        worksheet = sh.worksheet(sheet_tab)
        values = [today_str, f"{total_current:.2f}"]
        worksheet.append_row(values)
    except Exception as e:
        print("Fehler beim Google Sheets Export:", e)

    # Historie
    day1 = read_sheet_data(1)
    day7 = read_sheet_data(7)
    day30 = read_sheet_data(30)

    total_pnl = total_current - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # Chart erstellen
    labels = [r["name"] for r in results]
    values = [r["pnl_percent"] for r in results]
    chart_path = "static/pnl_chart.png"
    os.makedirs("static", exist_ok=True)
    fig, ax = plt.subplots()
    bars = ax.bar(labels, values, color=["green" if v > 0 else "red" for v in values])
    ax.set_ylabel("PNL %")
    plt.xticks(rotation=45)
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() * 0.98, f"{val:.2f}%", ha='center', va='bottom', fontsize=8)
    fig.tight_layout()
    plt.savefig(chart_path)
    plt.close()

    return render_template("dashboard.html",
        accounts=results,
        total=total_current,
        total_pnl=total_pnl,
        total_pnl_percent=total_pnl_percent,
        day1=day1,
        day7=day7,
        day30=day30,
        chart_path=chart_path
    )

@app.route('/logout')
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)
