from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash
import os
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = 'geheim123'

users = {
    "husky125": generate_password_hash("Ideal250!")
}

START_CAPITAL = float(os.environ.get("START_CAPITAL", 12237.37))

BYBIT_ACCOUNT_NAMES = {
    1: "Corestrategies",
    2: "Btcstrategies",
    3: "Solstrategies",
    4: "Altsstrategies",
    5: "Ethapestrategies",
    6: "Memestrategies",
    7: "Incubatorzone",
    8: "2k->10k Projekt",
    9: "1k->5k Projekt"
}

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

    subaccounts = []
    total_balance = 0.0
    current_balances = {}

    for i in range(1, 10):
        api_key = os.environ.get(f"BYBIT_API_KEY_{i}")
        api_secret = os.environ.get(f"BYBIT_API_SECRET_{i}")
        account_name = BYBIT_ACCOUNT_NAMES.get(i, f"Bybit #{i}")

        try:
            session_obj = HTTP(api_key=api_key, api_secret=api_secret)
            raw_positions = session_obj.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
            positions = [
                {
                    "symbol": p["symbol"],
                    "size": p["size"],
                    "pnl": float(p["unrealisedPnl"])
                }
                for p in raw_positions if float(p["size"]) != 0
            ]

            raw_balance = session_obj.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
            account_value = sum(float(acc["totalEquity"]) for acc in raw_balance)
            current_balances[account_name] = account_value
            total_balance += account_value

            subaccounts.append({
                "name": account_name,
                "balance": f"{account_value:.2f}",
                "positions": positions
            })

        except Exception as e:
            subaccounts.append({
                "name": account_name,
                "balance": f"Fehler ({str(e)})",
                "positions": [{"symbol": "Fehler", "size": "-", "pnl": 0.0}]
            })

    try:
        blofin = BloFinClient(
            api_key=os.environ.get("BLOFIN_API_KEY"),
            api_secret=os.environ.get("BLOFIN_API_SECRET"),
            passphrase=os.environ.get("BLOFIN_API_PASSPHRASE")
        )
        response = blofin.account.get_balance(account_type="futures")
        blofin_balance = sum(float(i["balance"]) for i in response["data"] if i["currency"] == "USDT")
        current_balances["Blofin (Top_7_Tage_Performer)"] = blofin_balance
        total_balance += blofin_balance

        subaccounts.append({
            "name": "Blofin (Top_7_Tage_Performer)",
            "balance": f"{blofin_balance:.2f}",
            "positions": []
        })

    except Exception as e:
        subaccounts.append({
            "name": "Blofin",
            "balance": f"Fehler ({str(e)})",
            "positions": [{"symbol": "Fehler", "size": "-", "pnl": 0.0}]
        })

    profit_loss = total_balance - START_CAPITAL

    # Chart vorbereiten
    initial_balances = {
        "Corestrategies": 2000.56,
        "Btcstrategies": 1923.00,
        "Solstrategies": 1713.81,
        "Altsstrategies": 1200.00,
        "Ethapestrategies": 1200.00,
        "Memestrategies": 800.00,
        "Incubatorzone": 400.00,
        "2k->10k Projekt": 2000.00,
        "1k->5k Projekt": 1000.00,
        "Blofin (Top_7_Tage_Performer)": 1492.00
    }

    pnl_percent = []
    account_labels = []
    for name, current in current_balances.items():
        if name in initial_balances:
            initial = initial_balances[name]
            change = ((current - initial) / initial) * 100
            pnl_percent.append(change)
            account_labels.append(name)

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(account_labels, pnl_percent, color=['green' if v >= 0 else 'red' for v in pnl_percent])
    ax.set_ylabel("PnL in %")
    ax.set_title("📈 Pro-Konto Gewinn/Verlust (in USD)")
    ax.axhline(0, color='black', linewidth=0.8)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    chart_url = f"data:image/png;base64,{chart_base64}"

    return render_template(
        'dashboard.html',
        subaccounts=subaccounts,
        total_balance=f"{total_balance:.2f}",
        profit_loss=profit_loss,
        pnl_chart=chart_url
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
