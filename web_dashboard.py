import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pybit.unified_trading import HTTP
from blofin import BloFinClient
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = 'geheim123'

# Benutzer
users = {
    "husky125": generate_password_hash("Ideal250!")
}

# Startwerte für PnL-Berechnung
initial_balances = {
    "Incubatorzone": 400.00,
    "Memestrategies": 800.00,
    "Ethapestrategies": 1200.00,
    "Altsstrategies": 1200.00,
    "Solstrategies": 1713.81,
    "Btcstrategies": 1923.00,
    "Corestrategies": 2000.56,
    "2k->10k Projekt": 2000.00,
    "1k->5k Projekt": 1000.00,
    "Blofin": 1492.00,
}
STARTWERT_GESAMT = 13729.37

# Subaccounts Konfiguration
subaccounts = [
    {
        "name": "Incubatorzone",
        "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"),
        "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET")
    },
    {
        "name": "Memestrategies",
        "key": os.environ.get("BYBIT_MEMESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_MEMESTRATEGIES_API_SECRET")
    },
    {
        "name": "Ethapestrategies",
        "key": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_ETHAPESTRATEGIES_API_SECRET")
    },
    {
        "name": "Altsstrategies",
        "key": os.environ.get("BYBIT_ALTSSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_ALTSSTRATEGIES_API_SECRET")
    },
    {
        "name": "Solstrategies",
        "key": os.environ.get("BYBIT_SOLSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_SOLSTRATEGIES_API_SECRET")
    },
    {
        "name": "Btcstrategies",
        "key": os.environ.get("BYBIT_BTCSTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_BTCSTRATEGIES_API_SECRET")
    },
    {
        "name": "Corestrategies",
        "key": os.environ.get("BYBIT_CORESTRATEGIES_API_KEY"),
        "secret": os.environ.get("BYBIT_CORESTRATEGIES_API_SECRET")
    },
    {
        "name": "2k->10k Projekt",
        "key": os.environ.get("BYBIT_2K_API_KEY"),
        "secret": os.environ.get("BYBIT_2K_API_SECRET")
    },
    {
        "name": "1k->5k Projekt",
        "key": os.environ.get("BYBIT_1K_API_KEY"),
        "secret": os.environ.get("BYBIT_1K_API_SECRET")
    },
    {
        "name": "Blofin",
        "key": os.environ.get("BLOFIN_API_KEY"),
        "secret": os.environ.get("BLOFIN_API_SECRET"),
        "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")
    }
]

def read_last_days(days: int):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key("1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g")
        ws = sheet.worksheet("DailyBalances")
        rows = ws.get_all_values()
        headers = rows[0]
        data = rows[1:]
        results = []
        for row in data[-days:]:
            d = {headers[i]: float(row[i]) if row[i] else 0 for i in range(1, len(row))}
            d["date"] = row[0]
            results.append(d)
        return results
    except Exception as e:
        print("Fehler beim Google Sheet Import:", str(e))
        return []

def export_to_sheet(date_str, balance_dict):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        credentials_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}"))
        creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key("1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g")
        ws = sheet.worksheet("DailyBalances")
        headers = ws.row_values(1)
        today_values = [date_str]
        for acc in headers[1:]:
            today_values.append(balance_dict.get(acc, ""))
        ws.append_row(today_values)
    except Exception as e:
        print("Fehler beim Google Sheets Export:", str(e))

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if user in users and check_password_hash(users[user], pw):
            session['user'] = user
            return redirect(url_for('dashboard'))
        return render_template("login.html", error="Falsche Zugangsdaten.")
    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    subaccount_results = []
    total_balance = 0.0
    balance_dict = {}

    for sub in subaccounts:
        name = sub["name"]
        try:
            if name == "Blofin":
                client = BloFinClient(
                    api_key=sub["key"],
                    api_secret=sub["secret"],
                    passphrase=sub["passphrase"]
                )
                data = client.account.get_balance(account_type="futures")
                coins = data["data"]
                usd_value = sum(float(c["balanceInUSD"]) for c in coins)
                coin_summary = [
                    f"{c['currency']}: {float(c['balanceInUSD']):.2f} $" for c in coins if float(c["balanceInUSD"]) > 0
                ]
            else:
                session_api = HTTP(api_key=sub["key"], api_secret=sub["secret"])
                balance = session_api.get_wallet_balance(accountType="UNIFIED")
                coins = balance["result"]["list"][0]["coin"]
                usd_value = sum(float(c["usdValue"]) for c in coins)
                coin_summary = [
                    f"{c['coin']}: {float(c['usdValue']):.2f} $" for c in coins if float(c["usdValue"]) > 0
                ]

            total_balance += usd_value
            pnl = usd_value - initial_balances.get(name, 0)
            pnl_pct = (pnl / initial_balances.get(name, 1)) * 100

            subaccount_results.append({
                "name": name,
                "balance": usd_value,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "coin_summary": coin_summary
            })
            balance_dict[name] = round(usd_value, 2)

        except Exception as e:
            subaccount_results.append({
                "name": name,
                "balance": 0,
                "pnl": 0,
                "pnl_pct": 0,
                "coin_summary": [],
                "error": str(e)
            })
            balance_dict[name] = 0

    # Chart generieren
    labels = [x["name"] for x in subaccount_results]
    chart_values = [x["pnl_pct"] for x in subaccount_results]
    bar_colors = ['green' if val >= 0 else 'red' for val in chart_values]

    plt.clf()
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(labels, chart_values, color=bar_colors)
    for i, bar in enumerate(bars):
        text = f"{chart_values[i]:+.1f}%\n({subaccount_results[i]['pnl']:+.2f}$)"
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 0.5, text,
                ha='center', va='center', color='white', fontsize=9, fontweight='bold')

    ax.axhline(0, color='black', linewidth=0.8)
    ax.set_ylabel('Performance %')
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    chart_path = "static/pnl_chart.png"
    plt.savefig(chart_path)

    # Tageswert exportieren
    today = datetime.now().strftime("%Y-%m-%d")
    export_to_sheet(today, balance_dict)

    # Historie
    last_1 = read_last_days(1)
    last_7 = read_last_days(7)
    last_30 = read_last_days(30)

    def get_perf(data):
        if len(data) >= 1:
            val = sum(data[-1].values()) - STARTWERT_GESAMT
            pct = (val / STARTWERT_GESAMT) * 100
            return round(val, 2), round(pct, 2)
        return 0.0, 0.0

    perf_1d = get_perf(last_1)
    perf_7d = get_perf(last_7)
    perf_30d = get_perf(last_30)

    return render_template(
        "dashboard.html",
        subaccount_results=subaccount_results,
        total_balance=total_balance,
        perf_1d=perf_1d,
        perf_7d=perf_7d,
        perf_30d=perf_30d
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
