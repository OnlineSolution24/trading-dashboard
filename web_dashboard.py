<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --profit-color: #28a745;
            --loss-color: #dc3545;
            --neutral-color: #6c757d;
            --bg-dark: #2c3e50;
            --bg-card: #34495e;
            --bg-light: #ecf0f1;
            --text-light: #ffffff;
            --text-dark: #2c3e50;
            --text-muted: #95a5a6;
            --border-color: #7f8c8d;
            --blue-primary: #3498db;
            --blue-secondary: #2980b9;
            --gray-light: #bdc3c7;
            --gray-dark: #95a5a6;
        }

        body {
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 50%, #2980b9 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            color: var(--text-light);
        }

        .dashboard-container {
            background: rgba(44, 62, 80, 0.95);
            backdrop-filter: blur(15px);
            border-radius: 20px;
            padding: 30px;
            margin: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
            border: 1px solid var(--border-color);
        }

        .kpi-card {
            background: linear-gradient(145deg, var(--bg-card), #4a5f7a);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 8px 25px rgba(0,0,0,0.2);
            border: 1px solid var(--border-color);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            margin-bottom: 20px;
        }

        .kpi-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(52, 152, 219, 0.3);
        }

        .kpi-title {
            font-size: 0.9rem;
            color: var(--gray-light);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
            font-weight: 600;
        }

        .kpi-value {
            font-size: 2rem;
            font-weight: 700;
            margin: 0;
        }

        .kpi-icon {
            font-size: 2.5rem;
            margin-bottom: 15px;
            opacity: 0.8;
        }

        .profit { color: var(--profit-color) !important; }
        .loss { color: var(--loss-color) !important; }
        .neutral { color: var(--gray-light) !important; }

        .chart-container {
            background: var(--bg-card);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            border: 1px solid var(--border-color);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }

        .chart-title {
            color: var(--text-light);
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 20px;
            text-align: center;
        }

        .chart-img {
            width: 100%;
            height: auto;
            border-radius: 10px;
        }

        .data-table {
            background: var(--bg-card);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid var(--border-color);
            margin-bottom: 30px;
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }

        .table-title {
            color: var(--text-light);
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .custom-table {
            background: transparent;
            color: var(--text-light);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin-bottom: 0;
        }

        .custom-table thead {
            background: linear-gradient(145deg, var(--blue-secondary), var(--blue-primary));
        }

        .custom-table th {
            border: none;
            padding: 15px 12px;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
            color: var(--text-light);
        }

        .custom-table td {
            border: none;
            padding: 12px;
            border-bottom: 1px solid var(--border-color);
            vertical-align: middle;
        }

        .custom-table tbody tr {
            transition: background-color 0.2s ease;
        }

        .custom-table tbody tr:hover {
            background-color: rgba(52, 152, 219, 0.1);
        }

        .custom-table tbody tr:last-child td {
            border-bottom: none;
        }

        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .status-online {
            background-color: rgba(40, 167, 69, 0.2);
            color: var(--profit-color);
            border: 1px solid var(--profit-color);
        }

        .status-offline {
            background-color: rgba(220, 53, 69, 0.2);
            color: var(--loss-color);
            border: 1px solid var(--loss-color);
        }

        .pnl-value {
            font-weight: 700;
            font-size: 1.1rem;
        }

        .account-name {
            font-weight: 600;
            color: var(--text-light);
        }

        .symbol-badge {
            background: linear-gradient(145deg, var(--blue-primary), var(--blue-secondary));
            color: white;
            padding: 4px 10px;
            border-radius: 15px;
            font-size: 0.85rem;
            font-weight: 600;
        }

        .side-long {
            background-color: rgba(40, 167, 69, 0.2);
            color: var(--profit-color);
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: 600;
            border: 1px solid var(--profit-color);
        }

        .side-short {
            background-color: rgba(220, 53, 69, 0.2);
            color: var(--loss-color);
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: 600;
            border: 1px solid var(--loss-color);
        }

        .footer-timestamp {
            position: fixed;
            bottom: 20px;
            right: 30px;
            background: rgba(44, 62, 80, 0.9);
            padding: 10px 15px;
            border-radius: 25px;
            font-size: 0.85rem;
            color: var(--gray-light);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
        }

        .header-section {
            text-align: center;
            margin-bottom: 40px;
        }

        .header-title {
            font-size: 2.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--blue-primary), var(--gray-light));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }

        .header-subtitle {
            color: var(--gray-light);
            font-size: 1.1rem;
        }

        .icon-blue { color: var(--blue-primary); }
        .icon-gray { color: var(--gray-light); }

        /* Entfernen der Scroll-Container */
        .table-container {
            overflow: visible;
        }

        /* Responsive Design */
        @media (max-width: 768px) {
            .dashboard-container {
                margin: 10px;
                padding: 20px;
            }
            
            .kpi-value {
                font-size: 1.5rem;
            }
            
            .header-title {
                font-size: 2rem;
            }

            .custom-table {
                font-size: 0.85rem;
            }

            .custom-table th,
            .custom-table td {
                padding: 8px 6px;
            }
        }

        /* Bessere Darstellung für kleine Bildschirme */
        @media (max-width: 576px) {
            .col-lg-6 {
                margin-bottom: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="dashboard-container">
        <!-- Header -->
        <div class="header-section">
            <h1 class="header-title">
                <i class="fas fa-chart-line me-3"></i>Trading Dashboard
            </h1>
            <p class="header-subtitle">Übersicht Ihrer Trading-Performance</p>
        </div>

        <!-- KPI Cards -->
        <div class="row">
            <div class="col-lg-3 col-md-6">
                <div class="kpi-card">
                    <div class="kpi-icon">
                        <i class="fas fa-wallet icon-blue"></i>
                    </div>
                    <div class="kpi-title">Startkapital</div>
                    <div class="kpi-value neutral">${{ "%.2f"|format(total_start) }}</div>
                </div>
            </div>
            <div class="col-lg-3 col-md-6">
                <div class="kpi-card">
                    <div class="kpi-icon">
                        <i class="fas fa-coins icon-gray"></i>
                    </div>
                    <div class="kpi-title">Aktueller Wert</div>
                    <div class="kpi-value neutral">${{ "%.2f"|format(total_balance) }}</div>
                </div>
            </div>
            <div class="col-lg-3 col-md-6">
                <div class="kpi-card">
                    <div class="kpi-icon">
                        <i class="fas fa-chart-line {% if total_pnl >= 0 %}text-success{% else %}text-danger{% endif %}"></i>
                    </div>
                    <div class="kpi-title">Gesamt PnL</div>
                    <div class="kpi-value {% if total_pnl >= 0 %}profit{% else %}loss{% endif %}">
                        ${{ "%.2f"|format(total_pnl) }}
                    </div>
                </div>
            </div>
            <div class="col-lg-3 col-md-6">
                <div class="kpi-card">
                    <div class="kpi-icon">
                        <i class="fas fa-percentage {% if total_pnl_percent >= 0 %}text-success{% else %}text-danger{% endif %}"></i>
                    </div>
                    <div class="kpi-title">Gesamt PnL (%)</div>
                    <div class="kpi-value {% if total_pnl_percent >= 0 %}profit{% else %}loss{% endif %}">
                        {{ "%.2f"|format(total_pnl_percent) }}%
                    </div>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="row">
            <div class="col-lg-6">
                <div class="chart-container">
                    <h5 class="chart-title">
                        <i class="fas fa-chart-bar me-2 icon-blue"></i>Subaccount Performance
                    </h5>
                    <img src="{{ chart_path_strategien }}" class="chart-img" alt="Strategien Chart">
                </div>
            </div>
            <div class="col-lg-6">
                <div class="chart-container">
                    <h5 class="chart-title">
                        <i class="fas fa-project-diagram me-2 icon-blue"></i>Projekt Performance
                    </h5>
                    <img src="{{ chart_path_projekte }}" class="chart-img" alt="Projekte Chart">
                </div>
            </div>
        </div>

        <!-- Tables -->
        <div class="row">
            <!-- Subaccounts Table -->
            <div class="col-lg-6">
                <div class="data-table">
                    <h5 class="table-title">
                        <i class="fas fa-users icon-blue"></i>
                        Subaccounts
                    </h5>
                    <div class="table-container">
                        <table class="table custom-table">
                            <thead>
                                <tr>
                                    <th>Account</th>
                                    <th>Status</th>
                                    <th>Start</th>
                                    <th>Balance</th>
                                    <th>PnL</th>
                                    <th>PnL %</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for a in accounts %}
                                <tr>
                                    <td class="account-name">{{ a.name }}</td>
                                    <td>
                                        {% if a.status == "✅" %}
                                            <span class="status-badge status-online">Online</span>
                                        {% else %}
                                            <span class="status-badge status-offline">Offline</span>
                                        {% endif %}
                                    </td>
                                    <td class="neutral">${{ "%.2f"|format(a.start) }}</td>
                                    <td class="neutral">${{ "%.2f"|format(a.balance) }}</td>
                                    <td class="pnl-value {% if a.pnl >= 0 %}profit{% else %}loss{% endif %}">
                                        ${{ "%.2f"|format(a.pnl) }}
                                    </td>
                                    <td class="pnl-value {% if a.pnl_percent >= 0 %}profit{% else %}loss{% endif %}">
                                        {{ "%.2f"|format(a.pnl_percent) }}%
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Positions Table -->
            <div class="col-lg-6">
                <div class="data-table">
                    <h5 class="table-title">
                        <i class="fas fa-chart-area icon-blue"></i>
                        Offene Positionen
                    </h5>
                    <div class="table-container">
                        <table class="table custom-table">
                            <thead>
                                <tr>
                                    <th>Account</th>
                                    <th>Symbol</th>
                                    <th>Größe</th>
                                    <th>Einstieg</th>
                                    <th>PnL</th>
                                    <th>Seite</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for name, pos in positions_all %}
                                <tr>
                                    <td class="account-name">{{ name }}</td>
                                    <td>
                                        <span class="symbol-badge">{{ pos.symbol }}</span>
                                    </td>
                                    <td class="neutral">{{ pos.size }}</td>
                                    <td class="neutral">${{ pos.avgPrice }}</td>
                                    <td class="pnl-value {% if pos.unrealisedPnl|float >= 0 %}profit{% else %}loss{% endif %}">
                                        ${{ "%.2f"|format(pos.unrealisedPnl|float) }}
                                    </td>
                                    <td>
                                        {% if pos.side == "Buy" %}
                                            <span class="side-long">Long</span>
                                        {% else %}
                                            <span class="side-short">Short</span>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Footer Timestamp -->
    <div class="footer-timestamp">
        <i class="fas fa-clock me-2"></i>
        Letztes Update: {{ now }}
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
