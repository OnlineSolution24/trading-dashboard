@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    # === BYBIT ===
    try:
        bybit_session = HTTP(
            api_key=os.environ.get("BYBIT_API_KEY"),
            api_secret=os.environ.get("BYBIT_API_SECRET")
        )

        # Positionen laden
        positions = bybit_session.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
        bybit_data = [
            f"{p['symbol']} | Größe: {p['size']} | PnL: {p['unrealisedPnl']}"
            for p in positions if float(p['size']) != 0
        ]

        # Guthaben laden
        balance_raw = bybit_session.get_wallet_balance(accountType="UNIFIED")["result"]["list"]
        bybit_total = 0.0
        for item in balance_raw:
            for coin in item["coin"]:
                if coin["coin"] == "USDT":
                    bybit_total += float(coin["walletBalance"])
        bybit_total_str = f"{bybit_total:.2f} USDT"

    except Exception as e:
        bybit_data = [f"Fehler bei Bybit: {str(e)}"]
        bybit_total_str = "Fehler"

    # === BLOFIN ===
    try:
        blofin_client = BloFinClient(
            api_key=os.environ.get("BLOFIN_API_KEY"),
            api_secret=os.environ.get("BLOFIN_API_SECRET"),
            passphrase=os.environ.get("BLOFIN_API_PASSPHRASE")
        )
        response = blofin_client.account.get_balance(account_type="futures")
        balances = response["data"]
        blofin_data = [f"{b['currency']}: {b['available']} verfügbar" for b in balances]

        blofin_total = 0.0
        for b in balances:
            if b["currency"] == "USDT":
                blofin_total += float(b["balance"])
        blofin_total_str = f"{blofin_total:.2f} USDT"

    except Exception as e:
        blofin_data = [f"Fehler bei Blofin: {str(e)}"]
        blofin_total_str = "Fehler"

    return render_template(
        'dashboard.html',
        bybit_data=bybit_data,
        blofin_data=blofin_data,
        bybit_total=bybit_total_str,
        blofin_total=blofin_total_str
    )
