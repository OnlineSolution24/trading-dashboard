#!/bin/bash
# setup_progressive_import.sh
# Setup Script für das Progressive Import System

echo "🚀 Progressive Import System Setup"
echo "=================================="

# 1. Erstelle das Progressive Import System
echo "📝 Erstelle progressive_import_system.py..."
# Das Artifact progressive_import_system wird als Datei gespeichert

# 2. Erweitere die web_dashboard.py mit Progressive Import Integration
echo "🔧 Erweitere Dashboard Integration..."

cat >> dashboard_progressive_patch.py << 'EOF'
# Dashboard Progressive Import Integration Patch
# Füge diese Zeilen zu deiner web_dashboard.py hinzu

# SCHRITT 1: Imports hinzufügen (oben in der Datei nach den anderen Imports)
try:
    from progressive_import_system import (
        ProgressiveTradeImporter, 
        ProgressDatabase,
        get_progressive_import_status,
        get_all_import_progress,
        start_progressive_import
    )
    PROGRESSIVE_IMPORT_AVAILABLE = True
    logging.info("✅ Progressive Import System geladen")
except ImportError as e:
    PROGRESSIVE_IMPORT_AVAILABLE = False
    logging.warning(f"⚠️ Progressive Import System nicht verfügbar: {e}")

# SCHRITT 2: Globale Status-Variable hinzufügen (nach den anderen globalen Vars)
progressive_status = {
    'running': False,
    'progress': 0,
    'message': 'Bereit',
    'session_id': '',
    'current_account': '',
    'total_accounts': 0,
    'completed_accounts': 0,
    'total_trades': 0,
    'estimated_completion': None
}

# SCHRITT 3: Neue Routes hinzufügen (vor der dashboard() Route)

@app.route('/start_progressive_import', methods=['POST'])
def start_progressive_import_route():
    """Starte Progressive Import über Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({
            'status': 'error', 
            'message': 'Progressive Import System nicht verfügbar. Führe: pip install -r requirements.txt aus.'
        }), 500
    
    try:
        specific_account = request.form.get('account', '').strip()
        resume = request.form.get('resume', 'true').lower() == 'true'
        
        logging.info(f"🎯 Dashboard Progressive Import: account={specific_account or 'alle'}, resume={resume}")
        
        if progressive_status['running']:
            return jsonify({
                'status': 'error',
                'message': 'Progressive Import läuft bereits. Bitte warten Sie bis zum Abschluss.'
            }), 400
        
        # Lösche Dashboard Cache für frische Daten nach Import
        clear_dashboard_cache()
        
        # Starte Progressive Import
        result = start_progressive_import(specific_account, resume)
        
        if 'error' in result:
            return jsonify({
                'status': 'error',
                'message': f'Fehler beim Starten: {result["error"]}'
            }), 500
        
        return jsonify({
            'status': 'success',
            'message': f'Progressive Import gestartet für {specific_account or "alle Accounts"}',
            'session_id': result['session_id']
        })
        
    except Exception as e:
        logging.error(f"❌ Progressive Import Route Error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Starten des Progressive Imports: {str(e)}'
        }), 500

@app.route('/progressive_import_status')
def get_progressive_import_status_route():
    """Hole Progressive Import Status für AJAX Updates"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({
            'running': False,
            'message': 'Progressive Import nicht verfügbar'
        })
    
    try:
        status = get_progressive_import_status()
        return jsonify(status)
        
    except Exception as e:
        logging.error(f"❌ Progressive Status Route Error: {e}")
        return jsonify({
            'running': False,
            'message': f'Status-Fehler: {str(e)}'
        })

@app.route('/progressive_import_progress')
def get_progressive_import_progress_route():
    """Hole detaillierte Progress-Informationen für Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'unauthorized'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({'progress': []})
    
    try:
        progress = get_all_import_progress()
        
        # Formatiere für Dashboard
        formatted_progress = []
        for p in progress:
            status_icon = "✅" if p['completed'] else "🔄" if p['status'] == 'in_progress' else "❌" if p['status'] == 'error' else "⏸️"
            
            formatted_progress.append({
                'account': p['account'],
                'exchange': p['exchange'],
                'status': p['status'],
                'status_icon': status_icon,
                'total_trades': p['total_trades'],
                'completed': p['completed'],
                'error_count': p['error_count'],
                'last_update': p['last_update'],
                'progress_percent': 100 if p['completed'] else 50 if p['status'] == 'in_progress' else 0
            })
        
        return jsonify({'progress': formatted_progress})
        
    except Exception as e:
        logging.error(f"❌ Progress Route Error: {e}")
        return jsonify({'error': str(e)})

@app.route('/stop_progressive_import', methods=['POST'])
def stop_progressive_import_route():
    """Stoppe Progressive Import"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    try:
        global progressive_status
        
        if not progressive_status['running']:
            return jsonify({
                'status': 'error',
                'message': 'Kein Progressive Import läuft aktuell'
            }), 400
        
        # Setze Stop-Flag
        progressive_status['running'] = False
        progressive_status['message'] = 'Import wird gestoppt...'
        
        return jsonify({
            'status': 'success',
            'message': 'Progressive Import wird gestoppt'
        })
        
    except Exception as e:
        logging.error(f"❌ Stop Progressive Import Error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Stoppen: {str(e)}'
        }), 500

@app.route('/reset_progressive_import', methods=['POST'])
def reset_progressive_import_route():
    """Reset Progressive Import Progress"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    try:
        if progressive_status['running']:
            return jsonify({
                'status': 'error',
                'message': 'Import läuft noch. Bitte erst stoppen.'
            }), 400
        
        # Reset Progress-Database
        if PROGRESSIVE_IMPORT_AVAILABLE:
            db = ProgressDatabase()
            conn = sqlite3.connect(db.db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM import_progress')
            cursor.execute('DELETE FROM import_sessions')
            conn.commit()
            conn.close()
            
            logging.info("✅ Progressive Import Progress zurückgesetzt")
            
            return jsonify({
                'status': 'success',
                'message': 'Progressive Import Progress wurde zurückgesetzt'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Progressive Import System nicht verfügbar'
            }), 500
            
    except Exception as e:
        logging.error(f"❌ Reset Progressive Import Error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Fehler beim Zurücksetzen: {str(e)}'
        }), 500

EOF

# 3. Erstelle Template Update für dashboard.html
echo "📋 Erstelle Dashboard Template Update..."

cat > dashboard_progressive_template.html << 'EOF'
<!-- Progressive Import Section für dashboard.html -->
<!-- Füge dies NACH der "Import Controls" Section und VOR den KPI Cards ein -->

<!-- Progressive Import Controls -->
<div class="row mb-3">
    <div class="col-12">
        <div class="card" style="background: linear-gradient(145deg, rgba(52, 152, 219, 0.1), rgba(41, 128, 185, 0.15)); border: 1px solid rgba(52, 152, 219, 0.3); border-radius: 15px;">
            <div class="card-header" style="background: transparent; border-bottom: 1px solid rgba(52, 152, 219, 0.2);">
                <h5 class="mb-0 d-flex align-items-center">
                    <i class="fas fa-rocket me-2 text-primary"></i>
                    <span>Progressive Import System</span>
                    <small class="text-muted ms-3">Kontinuierlicher Import aller verfügbaren Trading-Daten</small>
                </h5>
            </div>
            <div class="card-body">
                <!-- Control Buttons -->
                <div class="row align-items-center">
                    <div class="col-md-8">
                        <div class="d-flex gap-2 mb-3 flex-wrap">
                            <button type="button" 
                                    class="btn btn-success btn-sm" 
                                    onclick="startProgressiveImport()" 
                                    id="progressive-start-btn">
                                <i class="fas fa-rocket me-1"></i>Vollständigen Import starten
                            </button>
                            
                            <button type="button" 
                                    class="btn btn-info btn-sm" 
                                    onclick="startProgressiveImport(true)" 
                                    id="progressive-resume-btn">
                                <i class="fas fa-play-circle me-1"></i>Import fortsetzen
                            </button>
                            
                            <button type="button" 
                                    class="btn btn-danger btn-sm" 
                                    onclick="stopProgressiveImport()" 
                                    id="progressive-stop-btn" 
                                    style="display: none;">
                                <i class="fas fa-stop me-1"></i>Import stoppen
                            </button>
                            
                            <div class="dropdown">
                                <button class="btn btn-outline-light btn-sm dropdown-toggle" 
                                        type="button" 
                                        data-bs-toggle="dropdown">
                                    <i class="fas fa-cog"></i> Optionen
                                </button>
                                <ul class="dropdown-menu" style="background: var(--bg-card); border: 1px solid var(--border-color);">
                                    <li>
                                        <a class="dropdown-item text-light" href="#" onclick="showProgressDetails()">
                                            <i class="fas fa-chart-bar me-2"></i>Fortschritt Details
                                        </a>
                                    </li>
                                    <li>
                                        <a class="dropdown-item text-light" href="#" onclick="resetProgressiveImport()">
                                            <i class="fas fa-redo me-2"></i>Progress zurücksetzen
                                        </a>
                                    </li>
                                    <li><hr class="dropdown-divider" style="border-color: var(--border-color);"></li>
                                    <li>
                                        <a class="dropdown-item text-light" href="#" onclick="showProgressiveHelp()">
                                            <i class="fas fa-question-circle me-2"></i>Hilfe
                                        </a>
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-4 text-end">
                        <div id="progressive-status" class="import-status neutral mb-1">● Bereit für Progressive Import</div>
                        <small id="progressive-eta" class="text-muted d-block"></small>
                    </div>
                </div>
                
                <!-- Progress Bar -->
                <div id="progressive-progress-section" style="display: none;">
                    <div class="progress mb-2" style="height: 10px; background: rgba(0,0,0,0.3); border-radius: 5px;">
                        <div class="progress-bar bg-gradient" 
                             id="progressive-progress-bar" 
                             style="width: 0%; background: linear-gradient(90deg, #28a745, #20c997); border-radius: 5px;"></div>
                    </div>
                    <div class="d-flex justify-content-between">
                        <small id="progressive-progress-text" class="text-light">Bereit...</small>
                        <small id="progressive-progress-percent" class="text-light fw-bold">0%</small>
                    </div>
                </div>
                
                <!-- Account Progress Grid -->
                <div id="progressive-account-grid" class="row mt-3" style="display: none;">
                    <!-- Wird dynamisch gefüllt -->
                </div>
                
                <!-- Info Box -->
                <div class="alert alert-info mt-3" style="background: rgba(23, 162, 184, 0.1); border: 1px solid rgba(23, 162, 184, 0.3); color: var(--text-light);">
                    <div class="d-flex align-items-start">
                        <i class="fas fa-info-circle me-2 mt-1"></i>
                        <div>
                            <strong>Progressive Import:</strong> Lädt kontinuierlich alle verfügbaren Trading-Daten von allen APIs. 
                            Der Import kann mehrere Stunden dauern, läuft aber automatisch im Hintergrund weiter und kann unterbrochen/fortgesetzt werden.
                            <div class="mt-2">
                                <small class="text-muted">
                                    🔄 <strong>Fortsetzen:</strong> Lädt nur neue Daten seit dem letzten Import<br>
                                    🚀 <strong>Vollständig:</strong> Lädt alle verfügbaren Daten (empfohlen beim ersten Mal)
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
EOF

# 4. JavaScript Integration
echo "🎨 Erstelle JavaScript Integration..."
# Das JavaScript ist bereits im dashboard_progressive_integration Artifact enthalten

# 5. Erstelle Installations-Helper
cat > install_progressive_system.py << 'EOF'
#!/usr/bin/env python3
"""
Installation Helper für Progressive Import System
"""
import os
import sys
import shutil
import subprocess

def check_requirements():
    """Prüfe ob alle Requirements erfüllt sind"""
    required_packages = [
        'flask', 'pybit', 'gspread', 'google-auth', 
        'pandas', 'matplotlib', 'numpy', 'requests'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"❌ Fehlende Packages: {', '.join(missing)}")
        print("🔧 Installiere mit: pip install " + " ".join(missing))
        return False
    
    print("✅ Alle Required Packages verfügbar")
    return True

def setup_progressive_system():
    """Setup Progressive Import System"""
    
    print("🚀 Progressive Import System Installation")
    print("=" * 50)
    
    # 1. Check Requirements
    if not check_requirements():
        return False
    
    # 2. Check Files
    required_files = [
        'progressive_import_system.py',
        'enhanced_trade_importer.py',
        'web_dashboard.py'
    ]
    
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Fehlende Dateien: {', '.join(missing_files)}")
        print("💡 Bitte alle Artifacts als Dateien speichern")
        return False
    
    print("✅ Alle erforderlichen Dateien gefunden")
    
    # 3. Test Progressive Import System
    try:
        from progressive_import_system import ProgressiveTradeImporter, ProgressDatabase
        print("✅ Progressive Import System erfolgreich importiert")
        
        # Test Database
        db = ProgressDatabase()
        print("✅ Progress Database initialisiert")
        
    except Exception as e:
        print(f"❌ Progressive Import System Test fehlgeschlagen: {e}")
        return False
    
    # 4. Backup Original Dashboard
    if os.path.exists('web_dashboard.py'):
        backup_name = f"web_dashboard_backup_{int(time.time())}.py"
        shutil.copy2('web_dashboard.py', backup_name)
        print(f"✅ Dashboard Backup erstellt: {backup_name}")
    
    print("\n🎉 Progressive Import System Setup erfolgreich!")
    print("\n📋 Nächste Schritte:")
    print("1. Füge die Dashboard Integration aus 'dashboard_progressive_patch.py' zu deiner web_dashboard.py hinzu")
    print("2. Füge das Progressive Import HTML aus 'dashboard_progressive_template.html' zu deinem dashboard.html hinzu")
    print("3. Starte Dashboard: python web_dashboard.py")
    print("4. Teste Progressive Import über das Dashboard")
    
    return True

if __name__ == "__main__":
    import time
    success = setup_progressive_system()
    sys.exit(0 if success else 1)
EOF

# 6. Test Script
cat > test_progressive_import.py << 'EOF'
#!/usr/bin/env python3
"""
Test Script für Progressive Import System
"""
import os
import sys

def test_progressive_import():
    """Teste Progressive Import System"""
    print("🧪 Progressive Import System Test")
    print("=" * 40)
    
    try:
        # Test Import
        from progressive_import_system import (
            ProgressiveTradeImporter, 
            ProgressDatabase,
            get_progressive_import_status
        )
        print("✅ Progressive Import Module importiert")
        
        # Test Database
        db = ProgressDatabase()
        print("✅ Progress Database Test erfolgreich")
        
        # Test Status
        status = get_progressive_import_status()
        print(f"✅ Status Abruf erfolgreich: {status['message']}")
        
        # Test Importer Creation
        importer = ProgressiveTradeImporter("test_session")
        print("✅ Progressive Importer erstellt")
        
        print("\n🎉 Alle Tests erfolgreich!")
        print("💡 Das Progressive Import System ist bereit")
        
        return True
        
    except Exception as e:
        print(f"❌ Test fehlgeschlagen: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_progressive_import()
    sys.exit(0 if success else 1)
EOF

# 7. README Update
cat >> README_progressive.md << 'EOF'
# Progressive Import System

Das Progressive Import System ermöglicht kontinuierliches Laden aller verfügbaren Trading-Daten.

## Features

- 🚀 **Kontinuierlicher Import**: Lädt automatisch alle verfügbaren Trades
- 📊 **Progress Tracking**: Detaillierte Fortschrittsanzeige pro Account
- 🔄 **Resume Funktion**: Import kann unterbrochen und fortgesetzt werden
- 💾 **Persistierung**: Progress wird in SQLite gespeichert
- 🎛️ **Dashboard Integration**: Vollständige Steuerung über Web-Interface
- ⚡ **Optimiert**: Große Batches und intelligente Rate-Limiting

## Installation

1. **Speichere alle Artifacts als Dateien:**
   ```bash
   # progressive_import_system.py
   # dashboard_progressive_integration.py Inhalte zu web_dashboard.py hinzufügen
   # dashboard_progressive_template.html Inhalte zu dashboard.html hinzufügen
   ```

2. **Setup ausführen:**
   ```bash
   python install_progressive_system.py
   ```

3. **Test ausführen:**
   ```bash
   python test_progressive_import.py
   ```

## Nutzung

### Über Dashboard
- **Vollständiger Import**: Lädt alle verfügbaren Trades (beim ersten Mal)
- **Import fortsetzen**: Lädt nur neue Trades seit letztem Import
- **Live-Progress**: Echtzeit Fortschrittsanzeige
- **Account Details**: Status pro Trading-Account

### Kommandozeile
```bash
# Vollständiger Import
python progressive_import_system.py

# Spezifischer Account
python progressive_import_system.py --account="Claude Projekt"

# Status anzeigen
python progressive_import_system.py --status

# Progress zurücksetzen
python progressive_import_system.py --reset
```

## API Limits & Performance

- **Bybit**: 1000 Trades pro Request, max 100 Seiten
- **Blofin**: 100 Trades pro Request, max 50 Seiten
- **Rate Limiting**: Automatische Pausen zwischen Requests
- **Batch Processing**: Große Batches für Google Sheets
- **Resume Logic**: Fortsetzung ab letzter Position

## Datenumfang

Bei korrekter Konfiguration lädt das System:
- **90 Tage Trading History** (konfigurierbar)
- **Alle verfügbaren Trades** von allen konfigurierten APIs
- **Complete Pagination** bis keine weiteren Daten verfügbar
- **Performance Metriken** für Dashboard-Anzeige

## Troubleshooting

### Progressive Import startet nicht
- Environment Variables prüfen
- Google Sheets Verbindung testen
- API-Schlüssel validieren

### Import bricht ab
- Rate Limits beachten
- Netzwerkverbindung prüfen
- Error Logs in progressive_import.db prüfen

### Unvollständige Daten
- `--reset` ausführen und neu starten
- API-Limits der Exchange prüfen
- Mit `--status` Progress überwachen

## Database Schema

```sql
-- Progress Tracking
CREATE TABLE import_progress (
    account_name TEXT,
    exchange TEXT,
    last_cursor TEXT,
    total_trades_imported INTEGER,
    status TEXT,
    completed BOOLEAN
);

-- Session Management
CREATE TABLE import_sessions (
    session_id TEXT,
    start_time DATETIME,
    status TEXT,
    total_trades INTEGER
);
```

## Performance Tipps

1. **Erste Installation**: Vollständiger Import über Nacht laufen lassen
2. **Regelmäßig**: Import fortsetzen für neue Trades
3. **Monitoring**: Dashboard Progress-Details nutzen
4. **Fehlerbehandlung**: Bei Fehlern Reset und Neustart

Das Progressive Import System löst das Problem der begrenzten API-Requests durch intelligente Fortsetzung und Persistierung des Fortschritts! 🚀
EOF

# Berechtigungen setzen
chmod +x install_progressive_system.py
chmod +x test_progressive_import.py

echo ""
echo "🎉 Progressive Import System Setup abgeschlossen!"
echo ""
echo "📋 Nächste Schritte:"
echo "1. python install_progressive_system.py"
echo "2. Integriere dashboard_progressive_patch.py in deine web_dashboard.py"
echo "3. Integriere dashboard_progressive_template.html in dein dashboard.html"
echo "4. python test_progressive_import.py"
echo "5. python web_dashboard.py"
echo ""
echo "🚀 Progressive Import Features:"
echo "   • Kontinuierlicher Import aller verfügbaren Trades"
echo "   • Dashboard-Steuerung mit Live-Progress"
echo "   • Resume-Funktion bei Unterbrechungen"
echo "   • Optimiertes Batch-Processing"
echo "   • Vollständige API-Pagination"
echo ""
echo "💡 Das System lädt jetzt ALLE verfügbaren Trades!"
