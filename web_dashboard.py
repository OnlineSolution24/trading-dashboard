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

    # Beispielausgabe – hier würdest du deine echten Daten reinladen
    bybit_data = ["BTCUSDT | Größe: 0.1 | PnL: 5.2"]
    blofin_data = ["USDT: 250.00"]

    return render_template('dashboard.html', bybit_data=bybit_data, blofin_data=blofin_data)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
