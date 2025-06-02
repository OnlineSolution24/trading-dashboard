from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash
import os

app = Flask(__name__)
app.secret_key = 'geheim123'

# Benutzerverwaltung
users = {
    "husky125": generate_password_hash("Ideal250!")
}

# Konfiguration
START_CAPITAL = float(os.environ.get("START_CAPITAL", 12237.37))
BYBIT_ACCOUNTS = 9

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

    # === 9 BYBIT SUBACCOUNTS ===
    for i in range(1, BYBIT_ACCOUNTS + 1):
        api_key = os.environ.get(f"BYBIT_API_KEY_{i}")
        api_secret = os.environ.get(f"BYBIT_API_SECRET_{i}")
        account_name = f"Bybit #{i}"

        try:
            session_obj = HTTP(api_key=api_key, api_secret=api_secret)
            positions_raw = session_obj.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
            positions = []
            for p in positions_raw:
                if float(p["size"]) != 0:
                    positions.append({
                        "symbol": p["symbol"],
                        "size": p["size"],
                        "pnl": float(p["unrealisedPnl"])
                    })

            balance_raw = session_obj.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
            usdt_balance = 0.0
            for acc in balance_raw:
                for coin in acc["coin"]:
                    if coin["coin"] == "USDT":
                        usdt_balance += float(coin["walletBalance"])
            total_balance += usdt_balance

            subaccounts.append({
                "name": account_name,
                "balance": f"{usdt_balance:.2f}",
                "positions": positions
            })

        except Exception as e:
            subaccounts.append({
                "name": account_name,
                "balance": "Fehler",
                "positions": [{"symbol": "Fehler", "size": "-", "pnl": 0.0}]
            })

    # === 1 BLOFIN KONTO ===
    try:
        blofin = BloFinClient(
            api_key=os.environ.get("BLOFIN_API_KEY"),
            api_secret=os.environ.get("BLOFIN_API_SECRET"),
            passphrase=os.environ.get("BLOFIN_API_PASSPHRASE")
        )
        blofin_response = blofin.account.get_balance(account_type="futures")
        blofin_balance = 0.0
        blofin_positions = []

        for item in blofin_response["data"]:
            if item["currency"] == "USDT":
                blofin_balance += float(item["balance"])

        total_balance += blofin_balance

        subaccounts.append({
            "name": "Blofin",
            "balance": f"{blofin_balance:.2f}",
            "positions": blofin_positions  # Keine PnL abrufbar derzeit
        })

    except Exception as e:
        subaccounts.append({
            "name": "Blofin",
            "balance": "Fehler",
            "positions": [{"symbol": "Fehler", "size": "-", "pnl": 0.0}]
        })

    # === Gesamt-PnL berechnen
    profit_loss = total_balance - START_CAPITAL

    return render_template(
        'dashboard.html',
        subaccounts=subaccounts,
        total_balance=f"{total_balance:.2f}",
        profit_loss=profit_loss
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
