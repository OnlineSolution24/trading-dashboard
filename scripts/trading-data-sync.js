// scripts/trading-data-sync.js
const { google } = require('googleapis');
const fetch = require('node-fetch');
const crypto = require('crypto');

class WalletBalanceSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    this.successfulAccounts = 0;
    
    // Alle Accounts für Wallet Balance & Position Tracking
    this.accounts = [
      // Blofin Account - Account Balance
      {
        name: 'Blofin',
        sheetName: 'Blofin_Balance',
        api: {
          url: 'https://openapi.blofin.com/api/v1/account/balance',
          key: process.env.BLOFIN_API_KEY,
          secret: process.env.BLOFIN_API_SECRET,
          passphrase: process.env.BLOFIN_API_PASSPHRASE,
          type: 'blofin_balance'
        }
      },
      // Alle Bybit Accounts - Wallet Balance
      {
        name: 'Bybit 1K',
        sheetName: 'Bybit_1K_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_1K_API_KEY,
          secret: process.env.BYBIT_1K_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit 2K',
        sheetName: 'Bybit_2K_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_2K_API_KEY,
          secret: process.env.BYBIT_2K_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit AltStrategies',
        sheetName: 'Bybit_AltStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_ALTSSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ALTSSTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit BTC Strategies',
        sheetName: 'Bybit_BTCStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_BTCSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_BTCSTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit Claude Projekt',
        sheetName: 'Bybit_Claude_Projekt_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit Core Strategies',
        sheetName: 'Bybit_CoreStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit ETH Ape Strategies',
        sheetName: 'Bybit_ETHApeStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_ETHAPESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ETHAPESTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit Incubator Zone',
        sheetName: 'Bybit_IncubatorZone_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_INCUBATORZONE_API_KEY,
          secret: process.env.BYBIT_INCUBATORZONE_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit Meme Strategies',
        sheetName: 'Bybit_MemeStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_MEMESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_MEMESTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      {
        name: 'Bybit SOL Strategies',
        sheetName: 'Bybit_SOLStrategies_Balance',
        api: {
          url: 'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
          key: process.env.BYBIT_SOLSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_SOLSTRATEGIES_API_SECRET,
          type: 'bybit_balance'
        }
      },
      // Zusätzlich: Positionen für einige Accounts
      {
        name: 'Bybit Claude Projekt Positions',
        sheetName: 'Bybit_Claude_Projekt_Positions',
        api: {
          url: 'https://api.bybit.com/v5/position/list?category=linear',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit_positions'
        }
      },
      {
        name: 'Bybit Core Strategies Positions',
        sheetName: 'Bybit_CoreStrategies_Positions',
        api: {
          url: 'https://api.bybit.com/v5/position/list?category=linear',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit_positions'
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

  createBybitSignature(timestamp, apiKey, recvWindow, queryString, secret) {
    const param = timestamp + apiKey + recvWindow + queryString;
    return crypto.createHmac('sha256', secret).update(param).digest('hex');
  }

  createBlofinSignature(timestamp, method, requestPath, body, secret) {
    const prehash = timestamp + method.toUpperCase() + requestPath + (body || '');
    return crypto.createHmac('sha256', secret).update(prehash).digest('base64');
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
      this.log('info', `📋 Found existing sheets: ${existingSheets.length} sheets`);
      
      for (const account of this.accounts) {
        if (!existingSheets.includes(account.sheetName)) {
          await this.createSheet(account.sheetName, account.api.type);
          this.log('info', `✅ Created sheet: ${account.sheetName}`);
          await new Promise(r => setTimeout(r, 500));
        }
      }
      
    } catch (error) {
      this.log('error', 'Failed to ensure sheets', { error: error.message });
    }
  }

  async createSheet(sheetName, type) {
    try {
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
      
      let headers = [];
      
      if (type === 'bybit_balance') {
        headers = [
          'timestamp', 'account_name', 'coin', 'wallet_balance', 'available_balance', 
          'locked_balance', 'transferable_balance', 'bonus', 'available_to_withdraw',
          'usd_value', 'unrealized_pnl', 'cum_realized_pnl', 'sync_id', 'raw_data'
        ];
      } else if (type === 'bybit_positions') {
        headers = [
          'timestamp', 'account_name', 'category', 'symbol', 'side', 'size', 
          'position_value', 'entry_price', 'mark_price', 'liq_price', 'leverage',
          'unrealized_pnl', 'cum_realized_pnl', 'position_status', 'sync_id', 'raw_data'
        ];
      } else if (type === 'blofin_balance') {
        headers = [
          'timestamp', 'account_name', 'ccy', 'available_balance', 'frozen_balance',
          'equity', 'usd_equity', 'sync_id', 'raw_data'
        ];
      }
      
      if (headers.length > 0) {
        const endCol = String.fromCharCode(64 + headers.length);
        await this.sheets.spreadsheets.values.update({
          spreadsheetId: this.spreadsheetId,
          range: `${sheetName}!A1:${endCol}1`,
          valueInputOption: 'RAW',
          resource: { values: [headers] },
        });
      }
      
    } catch (error) {
      this.log('error', `Failed to create sheet ${sheetName}`, { error: error.message });
    }
  }

  async fetchAccountData(account) {
    try {
      this.log('info', `📡 Fetching ${account.api.type} from ${account.name}...`);
      
      if (!account.api.key) {
        this.log('warn', `⚠️ ${account.name}: API key missing, skipping`);
        return [];
      }
      
      const headers = {
        'User-Agent': 'Trading-Dashboard/1.0',
        'Accept': 'application/json'
      };
      
      if (account.api.type.startsWith('bybit')) {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(account.api.url).search.substring(1);
        
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = recvWindow;
        headers['X-BAPI-SIGN'] = this.createBybitSignature(
          timestamp, account.api.key, recvWindow, queryString, account.api.secret
        );
        
      } else if (account.api.type === 'blofin_balance') {
        const timestamp = new Date().toISOString();
        const method = 'GET';
        const requestPath = new URL(account.api.url).pathname;
        
        headers['BF-ACCESS-KEY'] = account.api.key;
        headers['BF-ACCESS-TIMESTAMP'] = timestamp;
        headers['BF-ACCESS-PASSPHRASE'] = account.api.passphrase;
        headers['BF-ACCESS-SIGN'] = this.createBlofinSignature(
          timestamp, method, requestPath, '', account.api.secret
        );
      }
      
      const response = await fetch(account.api.url, {
        method: 'GET',
        headers: headers
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      this.log('info', `✅ ${account.name}: Retrieved ${account.api.type} data`);
      
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
      if (account.api.type === 'bybit_balance') {
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          rawData.result.list.forEach(wallet => {
            if (wallet.coin && Array.isArray(wallet.coin)) {
              wallet.coin.forEach(coin => {
                // Speichere alle Coins, auch mit 0 Balance für Tracking
                rows.push([
                  timestamp,
                  account.name,
                  coin.coin,
                  parseFloat(coin.walletBalance || 0),
                  parseFloat(coin.availableBalance || 0),
                  parseFloat(coin.locked || 0),
                  parseFloat(coin.transferBalance || 0),
                  parseFloat(coin.bonus || 0),
                  parseFloat(coin.availableToWithdraw || 0),
                  parseFloat(coin.usdValue || 0),
                  parseFloat(coin.unrealisedPnl || 0),
                  parseFloat(coin.cumRealisedPnl || 0),
                  syncId,
                  JSON.stringify(coin)
                ]);
              });
            }
          });
        }
      } else if (account.api.type === 'bybit_positions') {
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          rawData.result.list.forEach(position => {
            // Nur offene Positionen speichern
            if (parseFloat(position.size || 0) > 0) {
              rows.push([
                timestamp,
                account.name,
                position.category || 'linear',
                position.symbol,
                position.side,
                parseFloat(position.size || 0),
                parseFloat(position.positionValue || 0),
                parseFloat(position.avgPrice || 0),
                parseFloat(position.markPrice || 0),
                parseFloat(position.liqPrice || 0),
                parseFloat(position.leverage || 0),
                parseFloat(position.unrealisedPnl || 0),
                parseFloat(position.cumRealisedPnl || 0),
                position.positionStatus,
                syncId,
                JSON.stringify(position)
              ]);
            }
          });
        }
      } else if (account.api.type === 'blofin_balance') {
        if (rawData.data && Array.isArray(rawData.data)) {
          rawData.data.forEach(balance => {
            rows.push([
              timestamp,
              account.name,
              balance.ccy,
              parseFloat(balance.availBal || 0),
              parseFloat(balance.frozenBal || 0),
              parseFloat(balance.eq || 0),
              parseFloat(balance.usdEq || 0),
              syncId,
              JSON.stringify(balance)
            ]);
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
      
      let endCol = 'N'; // Default für balance
      if (account.api.type === 'bybit_positions') endCol = 'P';
      if (account.api.type === 'blofin_balance') endCol = 'I';
      
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
    this.log('info', '🚀 Starting Wallet Balance & Position Sync...');
    this.log('info', '💰 Tracking account balances and positions...');
    this.log('info', `📊 Processing ${this.accounts.length} accounts...`);
    
    try {
      await this.initializeGoogleSheets();
      
      for (const account of this.accounts) {
        const data = await this.fetchAccountData(account);
        const savedCount = await this.saveToGoogleSheet(account, data);
        
        if (savedCount > 0) {
          this.successfulAccounts++;
          this.totalRecords += savedCount;
        }
        
        this.log('info', '⏳ Rate limiting: 2 seconds between accounts...');
        await new Promise(r => setTimeout(r, 2000));
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      const summary = {
        duration: `${duration.toFixed(1)}s`,
        totalRecords: this.totalRecords,
        successfulAccounts: this.successfulAccounts,
        totalAccounts: this.accounts.length,
        errors: this.errors.length
      };
      
      this.log('info', '🎉 Wallet Balance & Position Sync completed!', summary);
      this.log('info', `💰 Total records saved: ${this.totalRecords}`);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some accounts had errors:', { errors: this.errors });
      }
      
      const exitCode = this.successfulAccounts > 0 ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 Wallet Balance Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new WalletBalanceSync();
syncer.runSync();
