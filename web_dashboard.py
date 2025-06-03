from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
from werkzeug.security import check_password_hash, generate_password_hash
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)
app.secret_key = 'geheim123'

# ====================
# GOOGLE SHEETS FUNKTIONEN
# ====================
def save_to_google_sheet(date_str, value):
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name('google_service_account.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.environ.get("GOOGLE_SHEET_ID"))
        worksheet = sheet.worksheet("DailyBalances")

        # Sheet ID fest setzen (wenn nicht über Umgebungsvariable)
        os.environ['GOOGLE_SHEET_ID'] = '1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g'

        existing = worksheet.col_values(1)
        if date_str not in existing:
            worksheet.append_row([date_str, value])
            print(f"✅ Gespeichert: {date_str} – ${value}")
        else:
            print(f"ℹ️ Bereits vorhanden: {date_str}")
    except Exception as e:
        print("❌ Fehler beim Google Sheets Export:", str(e))

def read_last_days(days=7):
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name('google_service_account.json', scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(os.environ.get("GOOGLE_SHEET_ID"))
        worksheet = sheet.worksheet("DailyBalances")

        # Sheet ID fest setzen (wenn nicht über Umgebungsvariable)
        os.environ['GOOGLE_SHEET_ID'] = '1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g'

        records = worksheet.get_all_records()
        return [float(row["Gesamtwert ($)"]) for row in records][-days:]
    except Exception as e:
        print("❌ Fehler beim Lesen der Google Tabelle:", str(e))
        return []

# Der Rest der App sollte hier folgen, z.B. das Dashboard-Routing, API-Aufrufe, Chart-Generierung usw.
# Dies kann auf Wunsch jetzt hinzugefügt werden
# Benutzer-Daten
users = {
    "husky125": generate_password_hash("Ideal250!")
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

    START_CAPITAL = 13729.37

    try:
        bybit_session = HTTP(
            api_key=os.environ.get("BYBIT_API_KEY"),
            api_secret=os.environ.get("BYBIT_API_SECRET")
        )
        wallet_data = bybit_session.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
        bybit_total = 0.0
        for acc in wallet_data:
            for coin in acc["coin"]:
                if coin["coin"] == "USDT":
                    bybit_total += float(coin["walletBalance"])
        bybit_total_str = f"${bybit_total:,.2f}"
    except Exception as e:
        bybit_total_str = f"Fehler: {str(e)}"
        bybit_total = 0.0

    # Speichern in Google Sheets
    date_str = datetime.now().strftime("%Y-%m-%d")
    save_to_google_sheet(date_str, round(bybit_total, 2))

last_7 = read_last_days(7)
    last_30 = read_last_days(30)
    last_1 = read_last_days(2)

    perf_1 = f"{((bybit_total - last_1[0]) / last_1[0]) * 100:.2f}%" if len(last_1) >= 2 else "n/a"
    perf_7 = f"{((bybit_total - last_7[0]) / last_7[0]) * 100:.2f}%" if len(last_7) >= 2 else "n/a"
    perf_30 = f"{((bybit_total - last_30[0]) / last_30[0]) * 100:.2f}%" if len(last_30) >= 2 else "n/a"
    last_30 = read_last_days(30)

    perf_7 = f"{((bybit_total - last_7[0]) / last_7[0]) * 100:.2f}%" if len(last_7) >= 2 else "n/a"
    perf_30 = f"{((bybit_total - last_30[0]) / last_30[0]) * 100:.2f}%" if len(last_30) >= 2 else "n/a"

    # Diagramm: Performance seit Start
    fig, ax = plt.subplots(figsize=(8, 4))
    pnl_percent = ((bybit_total - START_CAPITAL) / START_CAPITAL) * 100
    pnl_dollar = bybit_total - START_CAPITAL
    ax.bar(["PnL"], [pnl_percent], color="green" if pnl_percent >= 0 else "red")
    ax.text(0, pnl_percent, f"{pnl_percent:+.2f}%\n(${pnl_dollar:+,.2f})", ha='center', va='bottom')
    ax.set_ylim(min(0, pnl_percent * 1.3), max(10, pnl_percent * 1.3))
    ax.set_title("Performance seit Start")
    img = io.BytesIO()
    plt.tight_layout()
    plt.savefig(img, format='png')
    img.seek(0)
    chart_url = base64.b64encode(img.getvalue()).decode()

    return render_template(
        'dashboard.html',
        bybit_total=bybit_total_str,
        perf_7=perf_7,
        perf_30=perf_30,
        chart_data=chart_url,
        perf_1=perf_1
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))
