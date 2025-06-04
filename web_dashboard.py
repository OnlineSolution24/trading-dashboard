from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = 'geheim123'

# Login-Daten
users = {
    "admin": generate_password_hash("passwort123")
}

# Startkapital zur Berechnung
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
    "Blofin": 1492.00
}

# Account-Definitionen
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
    chart_labels = []
    chart_percentages = []
    chart_values = []
    open_positions_data = []

    total_current = 0
    total_start = sum(initial_balances.values())

    for acc in subaccounts:
        name = acc["name"]
        start_balance = initial_balances.get(name, 0)
        current_balance = 0
        pnl_percent = 0
        pnl_value = 0
        error = None
        positions = []

        try:
            if name == "Blofin":
                client = BloFinClient(acc["key"], acc["secret"], acc["passphrase"])
                balance = client.account.get_balance(account_type="futures")["data"]
                for item in balance:
                    if item["currency"] == "USDT":
                        current_balance = float(item["available"])
                        break
            else:
                session_bybit = HTTP(acc["key"], acc["secret"])
                wallet_data = session_bybit.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                for item in wallet_data:
                    for coin in item["coin"]:
                        if coin["coin"] == "USDT":
                            current_balance = float(coin["equity"])

                pos_data = session_bybit.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
                positions = [
                    f"{p['symbol']}: Größe {p['size']}, PnL {float(p['unrealisedPnl']):+.2f} USDT"
                    for p in pos_data if float(p["size"]) != 0
                ]

            pnl_value = current_balance - start_balance
            pnl_percent = (pnl_value / start_balance) * 100 if start_balance != 0 else 0

        except Exception as e:
            error = str(e)

        total_current += current_balance
        chart_labels.append(name)
        chart_percentages.append(round(pnl_percent, 2))
        chart_values.append(round(pnl_value, 2))

        account_data.append({
            "name": name,
            "balance": current_balance,
            "start": start_balance,
            "pnl": pnl_value,
            "pnl_percent": pnl_percent,
            "status": "✅" if not error else f"❌ {error}",
            "positions": positions
        })

    total_pnl = total_current - total_start
    total_pnl_percent = (total_pnl / total_start) * 100

    # === CHART ===
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(chart_labels, chart_percentages, color=['green' if p >= 0 else 'red' for p in chart_percentages])
    for i, bar in enumerate(bars):
        value = f"{chart_percentages[i]:+.1f}%\n(${chart_values[i]:+.2f})"
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.01, value, ha='center', va='bottom', fontsize=9)
    ax.axhline(0, color='black')
    ax.set_title("PNL Übersicht pro Subaccount")
    ax.set_ylabel("Veränderung in %")
    plt.xticks(rotation=45)
    plt.tight_layout()

    chart_img = io.BytesIO()
    plt.savefig(chart_img, format='png')
    chart_img.seek(0)
    chart_data = base64.b64encode(chart_img.getvalue()).decode()

    return render_template("dashboard.html",
                           accounts=account_data,
                           total_current=total_current,
                           total_start=total_start,
                           total_pnl=total_pnl,
                           total_pnl_percent=total_pnl_percent,
                           chart_data=chart_data,
                           accounts=subaccount_data,
                           now=datetime.utcnow)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
