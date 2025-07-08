// scripts/trading-data-sync.js
const { google } = require('googleapis');
const fetch = require('node-fetch');

class MultiAccountTradingSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    this.successfulAccounts = 0;
    
    // Alle Trading Accounts konfigurieren
    this.accounts = [
      // Blofin Account
      {
        name: 'Blofin',
        sheetName: 'Blofin',
        api: {
          url: 'https://openapi.blofin.com/api/v1/market/tickers',
          key: process.env.BLOFIN_API_KEY,
          secret: process.env.BLOFIN_API_SECRET,
          passphrase: process.env.BLOFIN_API_PASSPHRASE,
          type: 'blofin'
        }
      },
      // Alle Bybit Accounts
      {
        name: 'Bybit 1K',
        sheetName: 'Bybit_1K',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_1K_API_KEY,
          secret: process.env.BYBIT_1K_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit 2K',
        sheetName: 'Bybit_2K',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_2K_API_KEY,
          secret: process.env.BYBIT_2K_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit AltStrategies',
        sheetName: 'Bybit_AltStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_ALTSSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ALTSSTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit BTC Strategies',
        sheetName: 'Bybit_BTCStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_BTCSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_BTCSTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit Claude Projekt',
        sheetName: 'Bybit_Claude_Projekt',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit Core Strategies',
        sheetName: 'Bybit_CoreStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit ETH Ape Strategies',
        sheetName: 'Bybit_ETHApeStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_ETHAPESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ETHAPESTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit Incubator Zone',
        sheetName: 'Bybit_IncubatorZone',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_INCUBATORZONE_API_KEY,
          secret: process.env.BYBIT_INCUBATORZONE_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit Meme Strategies',
        sheetName: 'Bybit_MemeStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_MEMESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_MEMESTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Bybit SOL Strategies',
        sheetName: 'Bybit_SOLStrategies',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_SOLSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_SOLSTRATEGIES_API_SECRET,
          type: 'bybit'
        }
      }
    ];
  }

  log(level, message, data) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ${level.toUpperCase()}: ${message}`);
    if (data) {
      console.log('Data:', JSON.stringify(data, null, 2));
    }
  }

  async initializeGoogleSheets() {
    try {
      this.log('info', '🔗 Initializing Google Sheets connection...');
      
      const auth = new google.auth.GoogleAuth({
        credentials: {
          client_email: process.env.GOOGLE_CLIENT_EMAIL,
          private_key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
        },
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      });

      this.sheets = google.sheets({ version: 'v4', auth });
      this.spreadsheetId = process.env.GOOGLE_SHEET_ID;
      
      const response = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      this.log('info', `📊 Connected to: "${response.data.properties.title}"`);
      
      // Alle benötigten Sheets erstellen/prüfen
      await this.ensureAllSheets();
      
      return true;
      
    } catch (error) {
      this.log('error', 'Google Sheets failed', { error: error.message });
      throw error;
    }
  }

  async ensureAllSheets() {
    try {
      const spreadsheet = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      const existingSheets = spreadsheet.data.sheets.map(sheet => sheet.properties.title);
      this.log('info', `📋 Found existing sheets: ${existingSheets.join(', ')}`);
      
      // Erstelle fehlende Sheets
      for (const account of this.accounts) {
        if (!existingSheets.includes(account.sheetName)) {
          await this.createSheet(account.sheetName, account.api.type);
          this.log('info', `✅ Created sheet: ${account.sheetName}`);
        }
      }
      
    } catch (error) {
      this.log('error', 'Failed to ensure sheets', { error: error.message });
    }
  }

  async createSheet(sheetName, type) {
    try {
      // Sheet erstellen
      await this.sheets.spreadsheets.batchUpdate({
        spreadsheetId: this.spreadsheetId,
        resource: {
          requests: [{
            addSheet: {
              properties: {
                title: sheetName
              }
            }
          }]
        }
      });
      
      // Header basierend auf Account-Typ erstellen
      let headers;
      if (type === 'bybit') {
        headers = [
          'timestamp', 
          'account_name',
          'coin', 
          'wallet_balance', 
          'available_balance',
          'locked_balance',
          'usd_value',
          'sync_id'
        ];
      } else if (type === 'blofin') {
        headers = [
          'timestamp',
          'account_name', 
          'symbol', 
          'last_price', 
          'change_24h',
          'volume_24h',
          'high_24h',
          'low_24h',
          'sync_id'
        ];
      }
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: `${sheetName}!A1:${String.fromCharCode(64 + headers.length)}1`,
        valueInputOption: 'RAW',
        resource: { values: [headers] },
      });
      
    } catch (error) {
      this.log('error', `Failed to create sheet ${sheetName}`, { error: error.message });
    }
  }

  async fetchAccountData(account) {
    try {
      this.log('info', `📡 Fetching ${account.name}...`);
      
      if (!account.api.key) {
        this.log('warn', `⚠️ ${account.name}: API key missing, skipping`);
        return [];
      }
      
      const headers = {
        'User-Agent': 'Trading-Sync/1.0',
        'Accept': 'application/json'
      };
      
      // API-spezifische Header
      if (account.api.type === 'bybit') {
        const timestamp = Date.now().toString();
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = '5000';
        
        // Hier würde normalerweise die Signatur berechnet werden
        // Für Demo: vereinfachte Version ohne Signatur
      } else if (account.api.type === 'blofin') {
        headers['BF-ACCESS-KEY'] = account.api.key;
        headers['BF-ACCESS-TIMESTAMP'] = new Date().toISOString();
        
        // Hier würde normalerweise die Signatur berechnet werden
        // Für Demo: vereinfachte Version ohne Signatur
      }
      
      const response = await fetch(account.api.url, {
        method: 'GET',
        headers: headers
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      this.log('info', `✅ ${account.name}: Got data`);
      
      return this.processAccountData(account, data);
      
    } catch (error) {
      this.log('error', `❌ ${account.name} failed: ${error.message}`);
      this.errors.push(`${account.name}: ${error.message}`);
      return [];
    }
  }

  processAccountData(account, rawData) {
    const timestamp = new Date().toISOString();
    const syncId = `sync_${Date.now()}`;
    const rows = [];
    
    try {
      if (account.api.type === 'bybit') {
        // Bybit Wallet Balance Daten verarbeiten
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          rawData.result.list.forEach(wallet => {
            if (wallet.coin && Array.isArray(wallet.coin)) {
              wallet.coin.forEach(coin => {
                // Nur Coins mit Balance > 0 speichern
                if (parseFloat(coin.walletBalance || 0) > 0) {
                  rows.push([
                    timestamp,
                    account.name,
                    coin.coin,
                    parseFloat(coin.walletBalance || 0),
                    parseFloat(coin.availableBalance || 0),
                    parseFloat(coin.locked || 0),
                    parseFloat(coin.usdValue || 0),
                    syncId
                  ]);
                }
              });
            }
          });
        }
      } else if (account.api.type === 'blofin') {
        // Blofin Market Data verarbeiten  
        if (rawData.data && Array.isArray(rawData.data)) {
          // Filter auf wichtigste Trading Pairs
          const majorPairs = ['BTC-USDT', 'ETH-USDT', 'ADA-USDT', 'SOL-USDT', 'LINK-USDT'];
          rawData.data.forEach(item => {
            if (majorPairs.includes(item.instId)) {
              rows.push([
                timestamp,
                account.name,
                item.instId,
                parseFloat(item.last || 0),
                parseFloat(item.sodUtc8 || 0),
                parseFloat(item.vol24h || 0),
                parseFloat(item.high24h || 0),
                parseFloat(item.low24h || 0),
                syncId
              ]);
            }
          });
        }
      }
      
      this.log('info', `📊 ${account.name}: Processed ${rows.length} records`);
      
    } catch (error) {
      this.log('error', `Error processing ${account.name} data: ${error.message}`);
    }
    
    return rows;
  }

  async saveToGoogleSheet(account, data) {
    if (data.length === 0) {
      this.log('info', `ℹ️ ${account.name}: No data to save`);
      return 0;
    }
    
    try {
      this.log('info', `💾 ${account.name}: Saving ${data.length} records...`);
      
      const existingData = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${account.sheetName}!A:A`,
      });
      
      const nextRow = (existingData.data.values?.length || 1) + 1;
      const endCol = account.api.type === 'bybit' ? 'H' : 'I';
      const range = `${account.sheetName}!A${nextRow}:${endCol}${nextRow + data.length - 1}`;
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: range,
        valueInputOption: 'RAW',
        resource: { values: data },
      });
      
      this.log('info', `✅ ${account.name}: Saved ${data.length} records!`);
      return data.length;
      
    } catch (error) {
      this.log('error', `${account.name}: Save failed - ${error.message}`);
      return 0;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting Multi-Account Trading Sync...');
    this.log('info', `📊 Processing ${this.accounts.length} accounts...`);
    
    try {
      await this.initializeGoogleSheets();
      
      // Alle Accounts parallel verarbeiten (mit Rate Limiting)
      for (const account of this.accounts) {
        const data = await this.fetchAccountData(account);
        const savedCount = await this.saveToGoogleSheet(account, data);
        
        if (savedCount > 0) {
          this.successfulAccounts++;
          this.totalRecords += savedCount;
        }
        
        // Rate Limiting zwischen Accounts
        await new Promise(r => setTimeout(r, 1500));
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      const summary = {
        duration: `${duration.toFixed(1)}s`,
        totalRecords: this.totalRecords,
        successfulAccounts: this.successfulAccounts,
        totalAccounts: this.accounts.length,
        errors: this.errors.length
      };
      
      this.log('info', '🎉 Multi-Account Sync completed!', summary);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some accounts had errors:', { errors: this.errors });
      }
      
      // Exit mit Status basierend auf Erfolg
      const exitCode = this.successfulAccounts > 0 ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 Multi-Account Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new MultiAccountTradingSync();
syncer.runSync();
