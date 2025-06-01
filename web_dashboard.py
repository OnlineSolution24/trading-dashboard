from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = 'geheim123'  # Ändere das in etwas Zufälliges für Sicherheit

# Benutzer-Daten
users = {
    "husky125": generate_password_hash("Ideal250!")  # Passwort frei wählbar
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

    # === BYBIT LIVE-DATEN ===
    try:
        bybit_session = HTTP(
            api_key=os.environ.get("BYBIT_API_KEY"),
            api_secret=os.environ.get("BYBIT_API_SECRET")
        )
        positions = bybit_session.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
        bybit_data = [
            f"{p['symbol']} | Größe: {p['size']} | PnL: {p['unrealisedPnl']}"
            for p in positions if float(p['size']) != 0
        ]
    except Exception as e:
        bybit_data = [f"Fehler bei Bybit: {str(e)}"]

    # === BLOFIN LIVE-DATEN ===
    try:
        blofin_client = BloFinClient(
            api_key=os.environ.get("BLOFIN_API_KEY"),
            api_secret=os.environ.get("BLOFIN_API_SECRET"),
            passphrase=os.environ.get("BLOFIN_API_PASSPHRASE")
        )
        response = blofin_client.account.get_balance(account_type="futures")
print(response)  # Nur für Debug – in HTML kannst du das ersetzen
balances = response["data"]

        blofin_data = [f"{b['currency']}: {b['available']} verfügbar" for b in balances]
    except Exception as e:
        blofin_data = [f"Fehler bei Blofin: {str(e)}"]

    return render_template('dashboard.html', bybit_data=bybit_data, blofin_data=blofin_data)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


import os
from pybit.unified_trading import HTTP
from blofin import BloFinClient

# API-Zugangsdaten aus Umgebungsvariablen
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")

BLOFIN_API_KEY = os.environ.get("BLOFIN_API_KEY")
BLOFIN_API_SECRET = os.environ.get("BLOFIN_API_SECRET")
BLOFIN_API_PASSPHRASE = os.environ.get("BLOFIN_API_PASSPHRASE")
