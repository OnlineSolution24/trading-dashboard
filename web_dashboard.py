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

users = {
    "husky125": generate_password_hash("Ideal250!")
}

START_CAPITAL = 13729.37

SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
SHEET_TAB_NAME = "DailyBalances"

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

INITIALS = {
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

def save_to_google_sheet(date_str, value):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        worksheet = sheet.worksheet(SHEET_TAB_NAME)
        worksheet.append_row([date_str, value])
    except Exception as e:
        print("Fehler beim Google Sheets Export:", str(e))

def read_last_days(days=7):
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        worksheet = sheet.worksheet(SHEET_TAB_NAME)
        data = worksheet.get_all_records()
        return [float(row["Gesamtwert ($)"]) for row in data][-days:]
    except:
        return []

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

            start_cap = INITIALS.get(account_name, 0)
            pnl_absolute = account_value - start_cap
            pnl_percent = (pnl_absolute / start_cap * 100) if start_cap else 0

            subaccounts.append({
                "name": account_name,
                "balance": f"${account_value:,.2f}",
                "positions": positions,
                "pnl_absolute": pnl_absolute,
                "pnl_percent": pnl_percent
            })

        except Exception as e:
            subaccounts.append({
                "name": account_name,
                "balance": f"Fehler ({str(e)})",
                "positions": []
            })

    # Blofin-Konto
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

        start_cap = INITIALS.get("Blofin (Top_7_Tage_Performer)", 0)
        pnl_absolute = blofin_balance - start_cap
        pnl_percent = (pnl_absolute / start_cap * 100) if start_cap else 0

        subaccounts.append({
            "name": "Blofin (Top_7_Tage_Performer)",
            "balance": f"${blofin_balance:,.2f}",
            "positions": [],
            "pnl_absolute": pnl_absolute,
            "pnl_percent": pnl_percent
        })

    except Exception as e:
        subaccounts.append({
            "name": "Blofin",
            "balance": f"Fehler ({str(e)})",
            "positions": []
        })

    # CHART GENERIEREN
    chart_labels, chart_values, chart_dollar = [], [], []
    for name, current in current_balances.items():
        if name in INITIALS:
            start = INITIALS[name]
            pnl = (current - start) / start * 100
            chart_labels.append(name)
            chart_values.append(pnl)
            chart_dollar.append(current - start)

    fig, ax = plt.subplots(figsize=(13, 6))
    bars = ax.bar(chart_labels, chart_values, color=["green" if x >= 0 else "red" for x in chart_values])
    ax.axhline(0, color="gray")
    ax.set_title("PnL in % (mit $)")
    ax.set_ylabel("Veränderung in %")
    ax.set_ylim(min(-10, min(chart_values) * 1.3), max(10, max(chart_values) * 1.2))
    plt.xticks(rotation=45, ha="right")
    for i, bar in enumerate(bars):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height - (5 if height > 0 else -5),
            f"{chart_values[i]:+.1f}%\n(${chart_dollar[i]:+.0f})",
            ha="center",
            va="bottom" if height > 0 else "top",
            fontsize=8,
            color="white" if abs(height) > 15 else "black",
            clip_on=True
        )

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    chart_base64 = base64.b64encode(buf.read()).decode('utf-8')
    chart_url = f"data:image/png;base64,{chart_base64}"

    today = datetime.now().strftime("%Y-%m-%d")
    save_to_google_sheet(today, round(total_balance, 2))
    last_7 = read_last_days(7)
    last_30 = read_last_days(30)

    perf_7 = f"{(total_balance - last_7[0]) / last_7[0] * 100:.2f}%" if len(last_7) >= 2 else "?"
    perf_30 = f"{(total_balance - last_30[0]) / last_30[0] * 100:.2f}%" if len(last_30) >= 2 else "?"

    return render_template("dashboard.html",
        subaccounts=subaccounts,
        total_balance=f"${total_balance:,.2f}",
        profit_loss=f"${total_balance - START_CAPITAL:,.2f}",
        pnl_chart=chart_url,
        perf_7=perf_7,
        perf_30=perf_30
    )

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
