cat > debug_progressive_import.py << 'EOF'
#!/usr/bin/env python3
"""
Debug Progressive Import System
"""
import os
from datetime import datetime, timedelta

def debug_time_ranges():
    print("🔍 DEBUG TIME RANGES")
    print("=" * 40)
    
    now = datetime.now()
    print(f"Aktuelles Datum: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Standard 90 Tage
    days = 90
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    start_date = datetime.fromtimestamp(start_time/1000)
    
    print(f"Start-Zeit (90 Tage): {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Start-Timestamp: {start_time}")
    
    # Was wäre für Juni-Daten?
    june_start = datetime(2024, 6, 1)  # Juni 2024 (nicht 2025!)
    june_timestamp = int(june_start.timestamp() * 1000)
    
    print(f"Juni 2024 Start: {june_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Juni Timestamp: {june_timestamp}")
    
    # Aktueller Timestamp vs Juni
    print(f"Timestamp Differenz: {start_time - june_timestamp} ms")
    
    return start_time, june_timestamp

def test_api_call():
    """Teste einen API-Call mit korrekten Parametern"""
    try:
        from pybit.unified_trading import HTTP
        
        # Beispiel mit Claude Projekt API
        api_key = os.environ.get("BYBIT_CLAUDE_PROJEKT_API_KEY")
        api_secret = os.environ.get("BYBIT_CLAUDE_PROJEKT_API_SECRET")
        
        if not api_key or not api_secret:
            print("❌ Claude Projekt API Keys nicht gefunden")
            return
        
        client = HTTP(api_key=api_key, api_secret=api_secret)
        
        # Test mit verschiedenen Zeitbereichen
        now = datetime.now()
        
        # 1. Test: Letzte 30 Tage
        start_30d = int((now - timedelta(days=30)).timestamp() * 1000)
        
        print(f"\n🧪 TEST: Letzte 30 Tage ab {datetime.fromtimestamp(start_30d/1000).strftime('%Y-%m-%d')}")
        
        response = client.get_executions(
            category='linear',
            startTime=start_30d,
            limit=10
        )
        
        if response and response.get('retCode') == 0:
            trades = response.get('result', {}).get('list', [])
            print(f"✅ Trades gefunden: {len(trades)}")
            
            if trades:
                first_trade = trades[0]
                last_trade = trades[-1]
                
                first_date = datetime.fromtimestamp(int(first_trade.get('execTime', 0))/1000)
                last_date = datetime.fromtimestamp(int(last_trade.get('execTime', 0))/1000)
                
                print(f"   Neuester Trade: {first_date.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Ältester Trade: {last_date.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Symbols: {set(t.get('symbol', '') for t in trades[:5])}")
        else:
            print(f"❌ API Response: {response}")
            
    except Exception as e:
        print(f"❌ API Test Fehler: {e}")

if __name__ == "__main__":
    debug_time_ranges()
    test_api_call()
EOF
