// scripts/quick-extended-setup.js - Erweitert bestehendes System um Executions/Positions
require('dotenv').config();
const { google } = require('googleapis');

class QuickExtendedSetup {
  constructor() {
    this.spreadsheetId = process.env.GOOGLE_SHEET_ID;
    
    // Nur die Accounts für die wir bereits API Keys haben
    this.accounts = [
      {
        name: 'Claude Projekt',
        baseName: 'Claude_Projekt',
        existing: 'Bybit_Claude_Projekt_Orders' // Bereits vorhanden
      },
      {
        name: 'Core Strategies', 
        baseName: 'Core_Strategies',
        existing: 'Bybit_CoreStrategies_Orders'
      },
      {
        name: 'BTC Strategies',
        baseName: 'BTC_Strategies', 
        existing: 'Bybit_BTCStrategies_Orders'
      },
      {
        name: 'ETH Ape Strategies',
        baseName: 'ETH_Ape_Strategies',
        existing: 'Bybit_ETHApeStrategies_Orders'
      },
      {
        name: 'Alt Strategies',
        baseName: 'Alt_Strategies',
        existing: 'Bybit_AltStrategies_Orders'
      }
    ];

    // Neue Sheet-Typen die wir hinzufügen
    this.newSheetTypes = {
      executions: {
        suffix: '_Executions',
        description: 'Trade Executions mit P&L',
        headers: [
          'execution_time',     // Timestamp der Ausführung
          'account_name',       // Account Name
          'symbol',            // Trading Pair
          'side',              // BUY/SELL
          'executed_qty',      // Ausgeführte Menge
          'entry_price',       // Einstiegspreis
          'exit_price',        // Ausstiegspreis
          'realized_pnl',      // Realisierter P&L
          'execution_type',    // Trade/Settlement
          'trade_id',          // Eindeutige Trade ID
          'created_time',      // Erstellungszeit
          'fee',               // Trading Fee
          'fee_currency',      // Fee Currency
          'data_source',       // CSV_IMPORT/API_SYNC
          'import_timestamp',  // Import-Zeit
          'raw_data'           // Original JSON
        ]
      },
      
      positions: {
        suffix: '_Positions',
        description: 'Position History und Account Status',
        headers: [
          'timestamp',         // Position Timestamp
          'account_name',      // Account Name
          'category',          // linear/spot
          'symbol',           // Trading Pair
          'side',             // Buy/Sell/None
          'size',             // Position Size
          'position_value',   // Position Value
          'entry_price',      // Entry Price
          'mark_price',       // Current Mark Price
          'liq_price',        // Liquidation Price
          'unrealised_pnl',   // Unrealized P&L
          'realised_pnl',     // Realized P&L
          'cum_realised_pnl', // Cumulative Realized P&L
          'leverage',         // Leverage
          'margin_mode',      // Cross/Isolated
          'position_status',  // Normal/Liq/Adl
          'created_time',     // Position Open Time
          'updated_time',     // Last Update
          'data_source',      // API_SYNC
          'import_timestamp', // Import Time
          'raw_data'          // Original JSON
        ]
      }
    };
  }

  log(level, message, data) {
    const timestamp = new Date().toISOString().substring(11, 19);
    const emoji = { 'info': 'ℹ️', 'success': '✅', 'warn': '⚠️', 'error': '❌' };
    console.log(`[${timestamp}] ${emoji[level]} ${message}`);
    if (data) console.log('Data:', JSON.stringify(data, null, 2));
  }

  async initializeGoogleSheets() {
    try {
      this.log('info', '🔗 Connecting to existing Google Sheets...');
      
      const auth = new google.auth.GoogleAuth({
        credentials: {
          client_email: process.env.GOOGLE_CLIENT_EMAIL,
          private_key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
        },
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      });

      this.sheets = google.sheets({ version: 'v4', auth });
      
      const response = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      this.log('success', `Connected to: "${response.data.properties.title}"`);
      this.log('info', `Current sheets: ${response.data.sheets.length}`);
      
      return true;
      
    } catch (error) {
      this.log('error', `Google Sheets connection failed: ${error.message}`);
      throw error;
    }
  }

  async analyzeExistingSheets() {
    try {
      const spreadsheet = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      const existingSheets = spreadsheet.data.sheets.map(sheet => sheet.properties.title);
      
      this.log('info', 'Analyzing existing sheets...');
      console.log('📊 Existing sheets:', existingSheets);
      
      // Prüfe welche Order Sheets bereits existieren
      const foundOrderSheets = [];
      this.accounts.forEach(account => {
        if (existingSheets.includes(account.existing)) {
          foundOrderSheets.push(account.existing);
          this.log('success', `Found existing: ${account.existing}`);
        } else {
          this.log('warn', `Missing: ${account.existing}`);
        }
      });
      
      // Plane neue Sheets
      const sheetsToCreate = [];
      this.accounts.forEach(account => {
        Object.keys(this.newSheetTypes).forEach(type => {
          const sheetName = account.baseName + this.newSheetTypes[type].suffix;
          if (!existingSheets.includes(sheetName)) {
            sheetsToCreate.push({
              name: sheetName,
              account: account,
              type: type
            });
          }
        });
      });
      
      this.log('info', `Need to create ${sheetsToCreate.length} new sheets`);
      
      return { existingSheets, foundOrderSheets, sheetsToCreate };
      
    } catch (error) {
      this.log('error', `Failed to analyze sheets: ${error.message}`);
      throw error;
    }
  }

  async createNewSheets(sheetsToCreate) {
    if (sheetsToCreate.length === 0) {
      this.log('success', 'All extended sheets already exist!');
      return;
    }
    
    try {
      this.log('info', `Creating ${sheetsToCreate.length} new sheets...`);
      
      // Erstelle Sheets in kleineren Batches
      const batchSize = 5;
      for (let i = 0; i < sheetsToCreate.length; i += batchSize) {
        const batch = sheetsToCreate.slice(i, i + batchSize);
        
        const requests = batch.map(sheet => ({
          addSheet: {
            properties: {
              title: sheet.name,
              gridProperties: {
                rowCount: 5000,
                columnCount: 25
              }
            }
          }
        }));
        
        await this.sheets.spreadsheets.batchUpdate({
          spreadsheetId: this.spreadsheetId,
          resource: { requests }
        });
        
        this.log('success', `Created batch ${Math.floor(i/batchSize) + 1}: ${batch.length} sheets`);
        
        // Setup headers für diesen Batch
        for (const sheet of batch) {
          await this.setupSheetHeaders(sheet);
        }
        
        // Rate limiting
        await new Promise(r => setTimeout(r, 2000));
      }
      
    } catch (error) {
      this.log('error', `Failed to create sheets: ${error.message}`);
      throw error;
    }
  }

  async setupSheetHeaders(sheetInfo) {
    try {
      const sheetType = this.newSheetTypes[sheetInfo.type];
      const headers = sheetType.headers;
      
      this.log('info', `Setting up ${sheetInfo.name} (${sheetType.description})`);
      
      // Headers setzen
      const endCol = String.fromCharCode(64 + headers.length);
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: `${sheetInfo.name}!A1:${endCol}1`,
        valueInputOption: 'RAW',
        resource: { values: [headers] },
      });
      
      // Header formatieren
      const sheetId = await this.getSheetId(sheetInfo.name);
      
      if (sheetId) {
        await this.sheets.spreadsheets.batchUpdate({
          spreadsheetId: this.spreadsheetId,
          resource: {
            requests: [{
              repeatCell: {
                range: {
                  sheetId: sheetId,
                  startRowIndex: 0,
                  endRowIndex: 1,
                  startColumnIndex: 0,
                  endColumnIndex: headers.length
                },
                cell: {
                  userEnteredFormat: {
                    backgroundColor: { red: 0.2, green: 0.6, blue: 0.9 },
                    textFormat: { bold: true, foregroundColor: { red: 1, green: 1, blue: 1 } }
                  }
                },
                fields: 'userEnteredFormat(backgroundColor,textFormat)'
              }
            }]
          }
        });
      }
      
      this.log('success', `Headers set for ${sheetInfo.name} (${headers.length} columns)`);
      
    } catch (error) {
      this.log('error', `Failed to setup headers for ${sheetInfo.name}: ${error.message}`);
    }
  }

  async getSheetId(sheetName) {
    try {
      const spreadsheet = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      const sheet = spreadsheet.data.sheets.find(s => s.properties.title === sheetName);
      return sheet ? sheet.properties.sheetId : null;
    } catch (error) {
      return null;
    }
  }

  async createUpgradeInstructions() {
    const instructions = {
      title: "🎯 Extended Trading Dashboard - Upgrade Complete",
      newFeatures: [
        "📈 Trade Executions Sheets (für CSV Import)",
        "💰 Position History Sheets (für API Sync)",
        "🔄 Erweiterte Automatisierung möglich"
      ],
      immediateActions: [
        {
          action: "1. CSV Import für Trade Executions",
          description: "Claude.csv → Claude_Projekt_Executions Sheet",
          priority: "HIGH"
        },
        {
          action: "2. Update bestehender Cron Job",
          description: "Erweitere um Executions & Positions Sync",
          priority: "MEDIUM"
        },
        {
          action: "3. Test neuer API Endpoints", 
          description: "Position & Execution History APIs testen",
          priority: "LOW"
        }
      ],
      csvImportSteps: [
        "📁 Öffne Google Sheets → Claude_Projekt_Executions",
        "📍 Klicke Zelle A2 (erste Datenzeile)",
        "📤 File → Import → Upload Claude.csv",
        "⚙️ Settings: Insert new rows, Comma separator",
        "✅ Validiere importierte Daten"
      ]
    };
    
    return instructions;
  }

  async runQuickSetup() {
    try {
      this.log('info', '🚀 Quick Extended Setup für bestehendes System...');
      
      await this.initializeGoogleSheets();
      
      const analysis = await this.analyzeExistingSheets();
      
      await this.createNewSheets(analysis.sheetsToCreate);
      
      const instructions = await this.createUpgradeInstructions();
      
      console.log('\n🎉 EXTENDED SETUP COMPLETED!');
      console.log('============================');
      console.log(`✅ Found ${analysis.foundOrderSheets.length} existing Order sheets`);
      console.log(`✅ Created ${analysis.sheetsToCreate.length} new Execution/Position sheets`);
      console.log('✅ Headers and formatting applied');
      
      console.log('\n📋 IMMEDIATE NEXT STEPS:');
      console.log('1. 📤 Import Claude.csv → Claude_Projekt_Executions');
      console.log('2. 🔄 Update Render Cron Job für neue APIs');
      console.log('3. 🧪 Test Position & Execution APIs');
      
      console.log('\n🎯 NEW SHEETS CREATED:');
      analysis.sheetsToCreate.forEach(sheet => {
        console.log(`   📊 ${sheet.name}`);
      });
      
      return {
        success: true,
        newSheets: analysis.sheetsToCreate.length,
        existingSheets: analysis.foundOrderSheets.length,
        instructions: instructions
      };
      
    } catch (error) {
      this.log('error', `Setup failed: ${error.message}`);
      throw error;
    }
  }
}

// Führe Quick Setup aus
const setup = new QuickExtendedSetup();
setup.runQuickSetup()
  .then(result => {
    console.log('\n✅ Quick Extended Setup completed successfully!');
    process.exit(0);
  })
  .catch(error => {
    console.error('\n❌ Setup failed:', error.message);
    process.exit(1);
  });
