from flask import Flask, render_template, request, redirect, session, url_for
import os, datetime, gspread
from oauth2client.service_account import ServiceAccountCredentials
from pybit.unified_trading import HTTP
from blofin import BloFinClient

app = Flask(__name__)
app.secret_key = 'geheim123'

users = {
    "admin": "adminpass"
}

START_CAPITAL = 13729.37
GOOGLE_SHEET_ID = "1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g"
SHEET_TAB_NAME = "DailyBalances"

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] in users and request.form['password'] == users[request.form['username']]:
            session['user'] = request.form['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Falscher Login")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    subaccounts = [
        {"name": "Incubatorzone", "key": os.getenv("BYBIT_INCUBATORZONE_API_KEY"), "secret": os.getenv("BYBIT_INCUBATORZONE_API_SECRET")},
        {"name": "Memestrategies", "key": os.getenv("BYBIT_MEMESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_MEMESTRATEGIES_API_SECRET")},
        {"name": "Ethapestrategies", "key": os.getenv("BYBIT_ETHAPESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ETHAPESTRATEGIES_API_SECRET")},
        {"name": "Altsstrategies", "key": os.getenv("BYBIT_ALTSSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_ALTSSTRATEGIES_API_SECRET")},
        {"name": "Solstrategies", "key": os.getenv("BYBIT_SOLSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_SOLSTRATEGIES_API_SECRET")},
        {"name": "Btcstrategies", "key": os.getenv("BYBIT_BTCSTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_BTCSTRATEGIES_API_SECRET")},
        {"name": "Corestrategies", "key": os.getenv("BYBIT_CORESTRATEGIES_API_KEY"), "secret": os.getenv("BYBIT_CORESTRATEGIES_API_SECRET")},
        {"name": "2k->10k Projekt", "key": os.getenv("BYBIT_2K_API_KEY"), "secret": os.getenv("BYBIT_2K_API_SECRET")},
        {"name": "1k->5k Projekt", "key": os.getenv("BYBIT_1K_API_KEY"), "secret": os.getenv("BYBIT_1K_API_SECRET")},
        {"name": "Blofin", "key": os.getenv("BLOFIN_API_KEY"), "secret": os.getenv("BLOFIN_API_SECRET"), "passphrase": os.getenv("BLOFIN_API_PASSPHRASE")}
    ]

    sub_data = []
    total_value = 0
    for acc in subaccounts:
        try:
            if acc["name"] == "Blofin":
                blofin_client = BloFinClient(api_key=acc["key"], api_secret=acc["secret"], passphrase=acc["passphrase"])
                balances = blofin_client.account.get_balance(account_type="futures")["data"]
                equity = sum(float(b["equity"]) for b in balances if b["currency"] == "USDT")
                positions = []  # Blofin Positionen optional erweiterbar
            else:
                session_api = HTTP(api_key=acc["key"], api_secret=acc["secret"])
                balance_raw = session_api.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
                equity = sum(float(c["equity"]) for item in balance_raw for c in item["coin"] if c["coin"] == "USDT")
                pos_raw = session_api.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
                positions = [
                    {
                        "symbol": p["symbol"],
                        "size": p["size"],
                        "pnl": float(p["unrealisedPnl"])
                    }
                    for p in pos_raw if float(p["size"]) != 0
                ]
            status = "🟢"
        except Exception:
            equity = 0
            positions = []
            status = "🔴"

        total_value += equity
        sub_data.append({
            "name": acc["name"],
            "status": status,
            "equity": equity,
            "pnl": equity - get_start_equity(acc["name"]),
            "pnl_pct": ((equity - get_start_equity(acc["name"])) / get_start_equity(acc["name"])) * 100 if get_start_equity(acc["name"]) else 0,
            "positions": positions
        })

    total_pnl = total_value - START_CAPITAL
    total_pct = (total_pnl / START_CAPITAL) * 100

    # Google Sheets Export
    try:
        creds_path = os.getenv("GOOGLE_SHEETS_JSON") or "google_creds.json"
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_TAB_NAME)
        sheet.append_row([datetime.datetime.now().strftime("%Y-%m-%d"), total_value])
    except Exception as e:
        print("Fehler beim Google Sheets Export:", e)

    return render_template("dashboard.html",
                           sub_data=sub_data,
                           total_value=total_value,
                           total_pnl=total_pnl,
                           total_pct=total_pct,
                           start_capital=START_CAPITAL)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

def get_start_equity(name):
    mapping = {
        "Incubatorzone": 400,
        "Memestrategies": 800,
        "Ethapestrategies": 1200,
        "Altsstrategies": 1200,
        "Solstrategies": 1713.81,
        "Btcstrategies": 1923.00,
        "Corestrategies": 2000.56,
        "2k->10k Projekt": 2000,
        "1k->5k Projekt": 1000,
        "Blofin": 1492.00
    }
    return mapping.get(name, 0)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
