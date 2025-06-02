from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from werkzeug.security import check_password_hash, generate_password_hash
import os

app = Flask(__name__)
app.secret_key = 'geheim123'  # Ändere das für Produktion auf eine Zufallszeichenkette

# Benutzer-Daten
users = {
    "husky125": generate_password_hash("Ideal250!")  # Benutzername + Passwort
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

    try:
        bybit_session = HTTP(
            api_key=os.environ.get("BYBIT_API_KEY"),
            api_secret=os.environ.get("BYBIT_API_SECRET")
        )

        # Positionen abrufen
        positions = bybit_session.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
        bybit_data = [
            f"{p['symbol']} | Größe: {p['size']} | PnL: {p['unrealisedPnl']}"
            for p in positions if float(p['size']) != 0
        ]

        # Guthaben abrufen
        wallet_data = bybit_session.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
        bybit_total = 0.0
        for acc in wallet_data:
            for coin in acc["coin"]:
                if coin["coin"] == "USDT":
                    bybit_total += float(coin["walletBalance"])
        bybit_total_str = f"{bybit_total:.2f} USDT"

    except Exception as e:
        bybit_data = [f"Fehler bei Bybit: {str(e)}"]
        bybit_total_str = "Fehler"

    return render_template(
        'dashboard.html',
        bybit_data=bybit_data,
        bybit_total=bybit_total_str
    )


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
