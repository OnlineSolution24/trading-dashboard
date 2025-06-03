import os
import io
import base64
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, session, url_for
from pybit.unified_trading import HTTP
from werkzeug.security import generate_password_hash, check_password_hash
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = 'supersecret'

# Benutzer
users = {
    "husky125": generate_password_hash("Ideal250!")
}

# Google Sheet Setup
def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1FEtLcvSgi9NbPKqhu2RfeuuM3n15eLqZ9JtMvSM7O7g")
    return sheet.worksheet("DailyBalances")

def save_to_google_sheet(date_str, value):
    try:
        sheet = get_sheet()
        sheet.append_row([date_str, value])
    except Exception as e:
        print("Fehler beim Google Sheets Export:", e)

def read_last_days(days):
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        return [float(row["Wert"]) for row in records[-days:] if "Wert" in row]
    except:
        return []

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = request.form["username"]
        pw = request.form["password"]
        if user in users and check_password_hash(users[user], pw):
            session["user"] = user
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Login fehlgeschlagen.")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    START_CAPITAL = 13729.37
    api_error = False

    subaccounts = [
        {
            "name": "Corestrategies",
            "api_key": os.environ.get("BYBIT_CORE_API_KEY"),
            "api_secret": os.environ.get("BYBIT_CORE_API_SECRET")
        },
        {
            "name": "Btcstrategies",
            "api_key": os.environ.get("BYBIT_BTC_API_KEY"),
            "api_secret": os.environ.get("BYBIT_BTC_API_SECRET")
        },
        {
            "name": "Solstrategies",
            "api_key": os.environ.get("BYBIT_SOL_API_KEY"),
            "api_secret": os.environ.get("BYBIT_SOL_API_SECRET")
        },
        {
            "name": "Altstrategies",
            "api_key": os.environ.get("BYBIT_ALT_API_KEY"),
            "api_secret": os.environ.get("BYBIT_ALT_API_SECRET")
        },
        {
            "name": "Ethapestrategies",
            "api_key": os.environ.get("BYBIT_ETH_API_KEY"),
            "api_secret": os.environ.get("BYBIT_ETH_API_SECRET")
        },
        {
            "name": "Memestrategies",
            "api_key": os.environ.get("BYBIT_MEME_API_KEY"),
            "api_secret": os.environ.get("BYBIT_MEME_API_SECRET")
        },
        {
            "name": "Incubatorzone",
            "api_key": os.environ.get("BYBIT_INCUBATOR_API_KEY"),
            "api_secret": os.environ.get("BYBIT_INCUBATOR_API_SECRET")
        },
        {
            "name": "2k->10k Projekt",
            "api_key": os.environ.get("BYBIT_2K10K_API_KEY"),
            "api_secret": os.environ.get("BYBIT_2K10K_API_SECRET")
        },
        {
            "name": "1k->5k Projekt",
            "api_key": os.environ.get("BYBIT_1K5K_API_KEY"),
            "api_secret": os.environ.get("BYBIT_1K5K_API_SECRET")
        },
        {
            "name": "Blofin (Top 1-3 Performer)",
            "api_key": os.environ.get("BLOFIN_API_KEY"),
            "api_secret": os.environ.get("BLOFIN_API_SECRET"),
            "passphrase": os.environ.get("BLOFIN_API_PASSPHRASE")
        }
    ]

    bybit_total = 0.0
    account_data = []

    for acc in subaccounts:
        acc_result = {
            "name": acc["name"],
            "balance": None,
            "coins": [],
            "error": None
        }
        try:
            if "blofin" in acc["name"].lower():
                from blofin import BloFinClient
                blofin_client = BloFinClient(api_key=acc["api_key"], api_secret=acc["api_secret"], passphrase=acc["passphrase"])
                result = blofin_client.account.get_balance(account_type="futures")
                total = 0.0
                for item in result["data"]:
                    if item["currency"] == "USDT":
                        total += float(item["available"])
                        acc_result["coins"].append({"coin": "USDT", "amount": float(item["available"])})
                acc_result["balance"] = round(total, 2)
            else:
                session = HTTP(api_key=acc["api_key"], api_secret=acc["api_secret"])
                response = session.get_wallet_balance(accountType="UNIFIED")
                total = 0.0
                for item in response["result"]["list"]:
                    for coin in item["coin"]:
                        if coin["coin"] in ["USDT", "BTC", "ETH", "SOL"]:
                            amount = float(coin["walletBalance"])
                            acc_result["coins"].append({"coin": coin["coin"], "amount": amount})
                            if coin["coin"] == "USDT":
                                total += amount
                acc_result["balance"] = round(total, 2)
                bybit_total += total
        except Exception as e:
            acc_result["error"] = str(e)
            api_error = True

        account_data.append(acc_result)

    # Google Sheet speichern
    date_str = datetime.now().strftime("%Y-%m-%d")
    save_to_google_sheet(date_str, round(bybit_total, 2))

    last_1 = read_last_days(2)
    last_7 = read_last_days(7)
    last_30 = read_last_days(30)

    perf_1 = f"{((bybit_total - last_1[0]) / last_1[0]) * 100:.2f}%" if len(last_1) >= 2 else "n/a"
    perf_7 = f"{((bybit_total - last_7[0]) / last_7[0]) * 100:.2f}%" if len(last_7) >= 2 else "n/a"
    perf_30 = f"{((bybit_total - last_30[0]) / last_30[0]) * 100:.2f}%" if len(last_30) >= 2 else "n/a"

    pnl_percent = ((bybit_total - START_CAPITAL) / START_CAPITAL) * 100
    pnl_dollar = bybit_total - START_CAPITAL

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(["Gesamt"], [pnl_percent], color="green" if pnl_percent >= 0 else "red")
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width()/2,
                bar.get_height() * (0.98 if pnl_percent >= 0 else 1.02),
                f"{pnl_percent:+.2f}%\n(${pnl_dollar:+,.2f})",
                ha='center',
                va='top' if pnl_percent >= 0 else 'bottom',
                fontsize=10)
    ax.set_ylim(min(-100, pnl_percent * 1.5), max(100, pnl_percent * 1.5))
    ax.set_title("Performance seit Start")
    plt.tight_layout()
    img = io.BytesIO()
    plt.savefig(img, format="png")
    img.seek(0)
    chart_url = base64.b64encode(img.getvalue()).decode()

    return render_template("dashboard.html",
                           bybit_total=f"${bybit_total:,.2f}",
                           perf_1=perf_1,
                           perf_7=perf_7,
                           perf_30=perf_30,
                           chart_data=chart_url,
                           account_data=account_data,
                           api_error=api_error)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
