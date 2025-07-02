# Dashboard Integration für Progressive Import
# Diese Änderungen müssen in deine web_dashboard.py eingefügt werden

import subprocess
import threading
import time
from datetime import datetime
import sqlite3

# Importiere das Progressive Import System
try:
    from progressive_import_system import (
        ProgressiveTradeImporter, 
        ProgressDatabase,
        get_progressive_import_status,
        get_all_import_progress,
        start_progressive_import
    )
    PROGRESSIVE_IMPORT_AVAILABLE = True
except ImportError:
    PROGRESSIVE_IMPORT_AVAILABLE = False
    logging.warning("⚠️ Progressive Import System nicht verfügbar")

# Globale Progressive Import Status
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

@app.route('/start_progressive_import', methods=['POST'])
def start_progressive_import_route():
    """Starte Progressive Import über Dashboard"""
    if 'user' not in session:
        return jsonify({'status': 'error', 'message': 'Nicht authentifiziert'}), 401
    
    if not PROGRESSIVE_IMPORT_AVAILABLE:
        return jsonify({
            'status': 'error', 
            'message': 'Progressive Import System nicht verfügbar'
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
        
        # Zusätzliche Informationen aus der DB
        if status['running']:
            try:
                db = ProgressDatabase()
                all_progress = db.get_all_progress()
                
                # Berechne detaillierte Statistiken
                total_accounts = len(subaccounts)
                in_progress = len([p for p in all_progress if p['status'] == 'in_progress'])
                completed = len([p for p in all_progress if p['completed']])
                errors = len([p for p in all_progress if p['status'] == 'error'])
                total_trades = sum(p['total_trades'] for p in all_progress)
                
                # Aktueller Account
                current_accounts = [p['account'] for p in all_progress if p['status'] == 'in_progress']
                current_account = current_accounts[0] if current_accounts else ''
                
                # Geschätzte Fertigstellung
                if completed > 0 and total_accounts > completed:
                    remaining = total_accounts - completed
                    avg_time_per_account = 3  # Minuten geschätzt
                    estimated_minutes = remaining * avg_time_per_account
                    estimated_completion = (datetime.now() + timedelta(minutes=estimated_minutes)).strftime('%H:%M')
                else:
                    estimated_completion = None
                
                status.update({
                    'total_accounts': total_accounts,
                    'completed_accounts': completed,
                    'in_progress_accounts': in_progress,
                    'error_accounts': errors,
                    'total_trades': total_trades,
                    'current_account': current_account,
                    'estimated_completion': estimated_completion,
                    'progress': min(95, (completed / total_accounts) * 100) if total_accounts > 0 else 0
                })
                
            except Exception as e:
                logging.error(f"❌ Status Detail Error: {e}")
        
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
        
        # Setze Stop-Flag (wird vom Import-Thread erkannt)
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

# Dashboard Template Erweiterungen (HTML)
PROGRESSIVE_IMPORT_HTML = '''
<!-- Progressive Import Controls -->
<div class="row mb-3">
    <div class="col-12">
        <div class="card" style="background: rgba(52, 152, 219, 0.1); border: 1px solid rgba(52, 152, 219, 0.3);">
            <div class="card-header">
                <h5 class="mb-0">
                    <i class="fas fa-download me-2"></i>Progressive Import System
                    <small class="text-muted ms-2">Kontinuierlicher Import aller verfügbaren Trades</small>
                </h5>
            </div>
            <div class="card-body">
                <!-- Control Buttons -->
                <div class="row">
                    <div class="col-md-8">
                        <div class="d-flex gap-2 mb-3">
                            <button type="button" 
                                    class="btn btn-success" 
                                    onclick="startProgressiveImport()" 
                                    id="progressive-start-btn">
                                <i class="fas fa-play me-1"></i>Vollständigen Import starten
                            </button>
                            
                            <button type="button" 
                                    class="btn btn-warning" 
                                    onclick="startProgressiveImport(true)" 
                                    id="progressive-resume-btn">
                                <i class="fas fa-play-circle me-1"></i>Import fortsetzen
                            </button>
                            
                            <button type="button" 
                                    class="btn btn-danger" 
                                    onclick="stopProgressiveImport()" 
                                    id="progressive-stop-btn" 
                                    style="display: none;">
                                <i class="fas fa-stop me-1"></i>Import stoppen
                            </button>
                            
                            <div class="dropdown">
                                <button class="btn btn-outline-light dropdown-toggle" 
                                        type="button" 
                                        data-bs-toggle="dropdown">
                                    <i class="fas fa-cog"></i>
                                </button>
                                <ul class="dropdown-menu">
                                    <li>
                                        <a class="dropdown-item" href="#" onclick="showProgressDetails()">
                                            <i class="fas fa-chart-bar me-2"></i>Fortschritt Details
                                        </a>
                                    </li>
                                    <li>
                                        <a class="dropdown-item" href="#" onclick="resetProgressiveImport()">
                                            <i class="fas fa-redo me-2"></i>Progress zurücksetzen
                                        </a>
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-4 text-end">
                        <div id="progressive-status" class="import-status">● Bereit für Progressive Import</div>
                        <small id="progressive-eta" class="text-muted"></small>
                    </div>
                </div>
                
                <!-- Progress Bar -->
                <div id="progressive-progress-section" style="display: none;">
                    <div class="progress mb-2" style="height: 8px;">
                        <div class="progress-bar bg-success" 
                             id="progressive-progress-bar" 
                             style="width: 0%"></div>
                    </div>
                    <div class="d-flex justify-content-between">
                        <small id="progressive-progress-text">Bereit...</small>
                        <small id="progressive-progress-percent">0%</small>
                    </div>
                </div>
                
                <!-- Account Progress Grid -->
                <div id="progressive-account-grid" class="row" style="display: none;">
                    <!-- Wird dynamisch gefüllt -->
                </div>
            </div>
        </div>
    </div>
</div>
'''

PROGRESSIVE_IMPORT_JAVASCRIPT = '''
<script>
let progressiveImportRunning = false;
let progressiveStatusInterval = null;

function startProgressiveImport(resume = false) {
    if (progressiveImportRunning) {
        alert('Progressive Import läuft bereits!');
        return;
    }
    
    const confirmMessage = resume ? 
        'Progressive Import fortsetzen? Dies kann mehrere Stunden dauern.' :
        'Vollständigen Progressive Import starten? Dies kann mehrere Stunden dauern und lädt ALLE verfügbaren Trades.';
    
    if (!confirm(confirmMessage)) {
        return;
    }
    
    // UI Updates
    updateProgressiveUI(true);
    
    // Starte Import
    const formData = new FormData();
    formData.append('resume', resume ? 'true' : 'false');
    
    fetch('/start_progressive_import', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showProgressiveProgress(true);
            updateProgressiveStatus('Progressive Import gestartet...', 'info');
            
            // Starte Status-Polling
            progressiveStatusInterval = setInterval(checkProgressiveStatus, 3000);
        } else {
            throw new Error(data.message);
        }
    })
    .catch(error => {
        console.error('Progressive Import Start Error:', error);
        updateProgressiveStatus('Start-Fehler: ' + error.message, 'error');
        updateProgressiveUI(false);
    });
}

function stopProgressiveImport() {
    if (!progressiveImportRunning) {
        alert('Kein Progressive Import läuft aktuell!');
        return;
    }
    
    if (!confirm('Progressive Import wirklich stoppen?')) {
        return;
    }
    
    fetch('/stop_progressive_import', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            updateProgressiveStatus('Import wird gestoppt...', 'warning');
        } else {
            throw new Error(data.message);
        }
    })
    .catch(error => {
        console.error('Progressive Stop Error:', error);
        alert('Fehler beim Stoppen: ' + error.message);
    });
}

function resetProgressiveImport() {
    if (progressiveImportRunning) {
        alert('Import läuft noch. Bitte erst stoppen.');
        return;
    }
    
    if (!confirm('Progressive Import Progress wirklich zurücksetzen? Alle Fortschrittsdaten gehen verloren.')) {
        return;
    }
    
    fetch('/reset_progressive_import', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            updateProgressiveStatus('Progress zurückgesetzt', 'success');
            hideProgressiveProgress();
            hideAccountGrid();
        } else {
            throw new Error(data.message);
        }
    })
    .catch(error => {
        console.error('Progressive Reset Error:', error);
        alert('Fehler beim Zurücksetzen: ' + error.message);
    });
}

function checkProgressiveStatus() {
    fetch('/progressive_import_status')
    .then(response => response.json())
    .then(data => {
        if (data.running) {
            progressiveImportRunning = true;
            
            // Update Progress
            updateProgressiveProgress(
                data.progress || 0, 
                data.message || 'Läuft...',
                data.current_account || ''
            );
            
            // Update ETA
            if (data.estimated_completion) {
                document.getElementById('progressive-eta').textContent = 
                    `Geschätzte Fertigstellung: ${data.estimated_completion}`;
            }
            
            // Update Account Grid
            updateAccountProgressGrid();
            
        } else {
            // Import beendet
            progressiveImportRunning = false;
            updateProgressiveUI(false);
            
            if (data.progress >= 100) {
                updateProgressiveStatus('Progressive Import abgeschlossen!', 'success');
                updateProgressiveProgress(100, 'Abgeschlossen', '');
                
                // Zeige Erfolgs-Zusammenfassung
                setTimeout(() => {
                    if (confirm('Progressive Import abgeschlossen! Dashboard neu laden für aktualisierte Daten?')) {
                        window.location.reload();
                    }
                }, 2000);
            } else if (data.message && data.message.includes('Fehler')) {
                updateProgressiveStatus(data.message, 'error');
            } else {
                updateProgressiveStatus('Progressive Import beendet', 'neutral');
            }
            
            // Stoppe Status-Polling
            if (progressiveStatusInterval) {
                clearInterval(progressiveStatusInterval);
                progressiveStatusInterval = null;
            }
        }
    })
    .catch(error => {
        console.error('Progressive Status Check Error:', error);
        // Bei Fehler weitermachen, aber weniger häufig checken
    });
}

function updateProgressiveUI(running) {
    progressiveImportRunning = running;
    
    // Buttons
    document.getElementById('progressive-start-btn').style.display = running ? 'none' : 'inline-block';
    document.getElementById('progressive-resume-btn').style.display = running ? 'none' : 'inline-block';
    document.getElementById('progressive-stop-btn').style.display = running ? 'inline-block' : 'none';
    
    // Progress Section
    if (running) {
        showProgressiveProgress(true);
    }
}

function showProgressiveProgress(show) {
    document.getElementById('progressive-progress-section').style.display = show ? 'block' : 'none';
    if (show) {
        document.getElementById('progressive-account-grid').style.display = 'block';
    }
}

function hideProgressiveProgress() {
    document.getElementById('progressive-progress-section').style.display = 'none';
    hideAccountGrid();
}

function hideAccountGrid() {
    document.getElementById('progressive-account-grid').style.display = 'none';
}

function updateProgressiveProgress(percent, message, currentAccount) {
    document.getElementById('progressive-progress-bar').style.width = percent + '%';
    document.getElementById('progressive-progress-percent').textContent = Math.round(percent) + '%';
    document.getElementById('progressive-progress-text').textContent = 
        currentAccount ? `${message} (${currentAccount})` : message;
}

function updateProgressiveStatus(message, type) {
    const statusEl = document.getElementById('progressive-status');
    statusEl.className = `import-status ${type}`;
    
    const icons = {
        'info': '🔄',
        'success': '✅',
        'warning': '⚠️',
        'error': '❌',
        'neutral': '●'
    };
    
    statusEl.textContent = `${icons[type] || '●'} ${message}`;
}

function updateAccountProgressGrid() {
    fetch('/progressive_import_progress')
    .then(response => response.json())
    .then(data => {
        const grid = document.getElementById('progressive-account-grid');
        
        if (data.progress && data.progress.length > 0) {
            let html = '<div class="col-12"><h6 class="mb-3">Account Fortschritt:</h6></div>';
            
            data.progress.forEach(account => {
                const statusClass = account.completed ? 'success' : 
                                  account.status === 'in_progress' ? 'info' : 
                                  account.status === 'error' ? 'danger' : 'secondary';
                
                html += `
                <div class="col-md-4 col-lg-3 mb-2">
                    <div class="card card-sm border-${statusClass}">
                        <div class="card-body p-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <small class="fw-bold">${account.account}</small>
                                <span class="badge bg-${statusClass}">${account.status_icon}</span>
                            </div>
                            <div class="d-flex justify-content-between">
                                <small class="text-muted">${account.exchange}</small>
                                <small class="fw-bold">${account.total_trades || 0} Trades</small>
                            </div>
                            ${account.error_count > 0 ? 
                                `<small class="text-danger">Fehler: ${account.error_count}</small>` : 
                                ''
                            }
                        </div>
                    </div>
                </div>`;
            });
            
            grid.innerHTML = html;
        }
    })
    .catch(error => {
        console.error('Account Progress Update Error:', error);
    });
}

function showProgressDetails() {
    // Zeige detaillierte Progress-Informationen in Modal
    fetch('/progressive_import_progress')
    .then(response => response.json())
    .then(data => {
        let content = '<div class="table-responsive"><table class="table table-sm">';
        content += '<thead><tr><th>Account</th><th>Exchange</th><th>Status</th><th>Trades</th><th>Letztes Update</th></tr></thead><tbody>';
        
        if (data.progress) {
            data.progress.forEach(account => {
                content += `
                <tr>
                    <td>${account.account}</td>
                    <td>${account.exchange}</td>
                    <td>${account.status_icon} ${account.status}</td>
                    <td>${account.total_trades || 0}</td>
                    <td>${account.last_update ? new Date(account.last_update).toLocaleString() : 'Nie'}</td>
                </tr>`;
            });
        }
        
        content += '</tbody></table></div>';
        
        // Zeige in Modal (du müsstest ein Modal in dein Dashboard HTML hinzufügen)
        showInfoModal('Progressive Import Details', content);
    })
    .catch(error => {
        console.error('Progress Details Error:', error);
        alert('Fehler beim Laden der Details: ' + error.message);
    });
}

function showInfoModal(title, content) {
    // Erstelle temporäres Modal falls nicht vorhanden
    let modal = document.getElementById('infoModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.innerHTML = `
        <div class="modal fade" id="infoModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content" style="background: var(--bg-card); color: var(--text-light);">
                    <div class="modal-header">
                        <h5 class="modal-title" id="infoModalTitle"></h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" style="filter: invert(1);"></button>
                    </div>
                    <div class="modal-body" id="infoModalContent"></div>
                </div>
            </div>
        </div>`;
        document.body.appendChild(modal);
    }
    
    document.getElementById('infoModalTitle').textContent = title;
    document.getElementById('infoModalContent').innerHTML = content;
    
    const bootstrapModal = new bootstrap.Modal(document.getElementById('infoModal'));
    bootstrapModal.show();
}

// Auto-check für laufende Progressive Imports beim Seitenladen
document.addEventListener('DOMContentLoaded', function() {
    // Prüfe ob Progressive Import läuft
    checkProgressiveStatus();
    
    // Starte regelmäßige Checks falls Import läuft
    setTimeout(() => {
        if (progressiveImportRunning) {
            progressiveStatusInterval = setInterval(checkProgressiveStatus, 3000);
        }
    }, 1000);
});

// Cleanup beim Seitenverlassen
window.addEventListener('beforeunload', function() {
    if (progressiveStatusInterval) {
        clearInterval(progressiveStatusInterval);
    }
});
</script>

<!-- Zusätzliche CSS Styles für Progressive Import -->
<style>
.card-sm .card-body {
    padding: 0.5rem !important;
}

.progress {
    background-color: rgba(0,0,0,0.2);
}

.import-status.info { color: #17a2b8; }
.import-status.success { color: var(--profit-color); }
.import-status.warning { color: #ffc107; }
.import-status.error { color: var(--loss-color); }
.import-status.neutral { color: var(--neutral-color); }

.border-info { border-color: #17a2b8 !important; }
.border-success { border-color: var(--profit-color) !important; }
.border-danger { border-color: var(--loss-color) !important; }
.border-secondary { border-color: var(--neutral-color) !important; }

.bg-info { background-color: #17a2b8 !important; }
.bg-success { background-color: var(--profit-color) !important; }
.bg-danger { background-color: var(--loss-color) !important; }
.bg-secondary { background-color: var(--neutral-color) !important; }
</style>
'''
