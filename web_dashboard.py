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

        # Positionen laden (optional farbige Anzeige)
        positions = bybit_session.get_positions(category="linear", settleCoin="USDT")["result"]["list"]
        bybit_data = [
            f"{p['symbol']} | Größe: {p['size']} | PnL: {p['unrealisedPnl']}"
            for p in positions if float(p['size']) != 0
        ]

        # GUTHABEN laden
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
