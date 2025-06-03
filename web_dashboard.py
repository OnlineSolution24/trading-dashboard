
import os
from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from blofin import BloFinClient
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib.pyplot as plt
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'geheim123'

users = {
    "husky125": "Ideal250!"
}

STARTKAPITAL = 13729.37
GOOGLE_SHEET_ID = "1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g"
SHEET_TAB = "DailyBalances"

def save_to_google_sheet(date_str, value):
    try:
        creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_TAB)
        sheet.append_row([date_str, value])
    except Exception as e:
        print("Fehler beim Google Sheets Export:", e)

def read_last_days(days):
    try:
        creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_TAB)
        data = sheet.get_all_values()
        rows = data[-days:] if len(data) >= days else data[1:]
        return [float(row[1]) for row in rows]
    except Exception as e:
        print("Fehler beim Google Sheets Lesen:", e)
        return []

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if user in users and users[user] == pw:
            session['user'] = user
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Login fehlgeschlagen.")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    total = 0.0
    subaccounts = [
        {"name": "Incubatorzone", "key": os.environ.get("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.environ.get("BYBIT_INCUBATORZONE_API_SECRET")},
        {"name": "Blofin", "key": os.environ.get("BLOFIN_API_KEY"), "secret": os.environ.get("BLOFIN_API_SECRET"), "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")}
    ]

    account_data = []

    for acc in subaccounts:
        try:
            if acc["name"] == "Blofin":
                client = BloFinClient(api_key=acc["key"], api_secret=acc["secret"], passphrase=acc["passphrase"])
                balances = client.account.get_balance(account_type="futures")["data"]
                usdt = sum(float(x["available"]) for x in balances if x["currency"] == "USDT")
                status = "✅"
            else:
                session_bybit = HTTP(api_key=acc["key"], api_secret=acc["secret"])
                balances = session_bybit.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                usdt = 0.0
                for item in balances:
                    for coin in item["coin"]:
                        if coin["coin"] == "USDT":
                            usdt += float(coin["walletBalance"])
                status = "✅"
            total += usdt
        except Exception as e:
            usdt = 0.0
            status = "❌"
        account_data.append({
            "name": acc["name"],
            "balance": f"${usdt:,.2f}",
            "status": status
        })

    date_now = datetime.now().strftime("%Y-%m-%d")
    save_to_google_sheet(date_now, total)

    pnl_abs = total - STARTKAPITAL
    pnl_pct = (pnl_abs / STARTKAPITAL) * 100

    last_1 = read_last_days(1)
    last_7 = read_last_days(7)
    last_30 = read_last_days(30)

    return render_template(
        "dashboard.html",
        accounts=account_data,
        total=f"${total:,.2f}",
        pnl_abs=f"${pnl_abs:,.2f}",
        pnl_pct=f"{pnl_pct:+.2f}%",
        perf_1d=f"{((total - last_1[0])/last_1[0])*100:.2f}%" if last_1 else "n/a",
        perf_7d=f"{((total - last_7[0])/last_7[0])*100:.2f}%" if last_7 else "n/a",
        perf_30d=f"{((total - last_30[0])/last_30[0])*100:.2f}%" if last_30 else "n/a"
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
