// scripts/trading-data-sync.js
const { google } = require('googleapis');
const fetch = require('node-fetch');
const crypto = require('crypto');

class FlexibleTradingHistorySync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    this.successfulAccounts = 0;
    
    // Accounts mit individuellen Start-Daten (falls bekannt)
    this.accounts = [
      {
        name: 'Blofin',
        sheetName: 'Blofin_Trades',
        startDate: '2025-05-22', // Falls du weißt wann gestartet
        api: {
          url: 'https://openapi.blofin.com/api/v1/trade/fills',
          key: process.env.BLOFIN_API_KEY,
          secret: process.env.BLOFIN_API_SECRET,
          passphrase: process.env.BLOFIN_API_PASSPHRASE,
          type: 'blofin_trades'
        }
      },
      {
        name: 'Bybit 1K',
        sheetName: 'Bybit_1K_Trades',
        startDate: null, // Automatisch ermitteln
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_1K_API_KEY,
          secret: process.env.BYBIT_1K_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit 2K',
        sheetName: 'Bybit_2K_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_2K_API_KEY,
          secret: process.env.BYBIT_2K_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit AltStrategies',
        sheetName: 'Bybit_AltStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_ALTSSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ALTSSTRATEGIES_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit BTC Strategies',
        sheetName: 'Bybit_BTCStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_BTCSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_BTCSTRATEGIES_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit Claude Projekt',
        sheetName: 'Bybit_Claude_Projekt_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit Core Strategies',
        sheetName: 'Bybit_CoreStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit ETH Ape Strategies',
        sheetName: 'Bybit_ETHApeStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_ETHAPESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ETHAPESTRATEGIES_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit Incubator Zone',
        sheetName: 'Bybit_IncubatorZone_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_INCUBATORZONE_API_KEY,
          secret: process.env.BYBIT_INCUBATORZONE_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit Meme Strategies',
        sheetName: 'Bybit_MemeStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_MEMESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_MEMESTRATEGIES_API_SECRET,
          type: 'bybit_trades'
        }
      },
      {
        name: 'Bybit SOL Strategies',
        sheetName: 'Bybit_SOLStrategies_Trades',
        startDate: null,
        api: {
          url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=1000',
          key: process.env.BYBIT_SOLSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_SOLSTRATEGIES_API_SECRET,
          type: 'bybit_trades'
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
      
      if (type === 'bybit_trades') {
        headers = [
          'timestamp', 'account_name', 'category', 'symbol', 'exec_id', 'order_id', 
          'order_link_id', 'side', 'exec_qty', 'exec_price', 'order_type', 'exec_type',
          'exec_value', 'exec_fee', 'fee_rate', 'trade_iv', 'mark_iv', 'mark_price',
          'index_price', 'underlying_price', 'block_trade_id', 'closed_size',
          'seq', 'next_page_cursor', 'exec_time', 'is_maker', 'sync_id', 'raw_data'
        ];
      } else if (type === 'blofin_trades') {
        headers = [
          'timestamp', 'account_name', 'inst_type', 'inst_id', 'trade_id', 'order_id',
          'cl_ord_id', 'bill_id', 'tag', 'fill_px', 'fill_sz', 'side', 'exec_type',
          'fee_ccy', 'fee', 'ts', 'sync_id', 'raw_data'
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

  async getOptimalStartTime(account) {
    try {
      // 1. Prüfe ob bereits Daten im Sheet sind
      const response = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${account.sheetName}!A:A`,
      });
      
      if (response.data.values && response.data.values.length > 1) {
        // Sheet hat bereits Daten - inkrementeller Sync
        const timestamps = response.data.values
          .slice(1)
          .map(row => new Date(row[0]).getTime())
          .filter(ts => !isNaN(ts))
          .sort((a, b) => b - a);
        
        if (timestamps.length > 0) {
          const lastSync = new Date(timestamps[0]);
          this.log('info', `📅 ${account.name}: Incremental sync since ${lastSync.toISOString()}`);
          return timestamps[0];
        }
      }
      
      // 2. Verwende Account-spezifisches Start-Datum falls definiert
      if (account.startDate) {
        const startDate = new Date(`${account.startDate}T00:00:00.000Z`);
        this.log('info', `📅 ${account.name}: Using defined start date ${startDate.toISOString()}`);
        return startDate.getTime();
      }
      
      // 3. Automatische Erkennung: Probe verschiedene Zeiträume
      const probePeriods = [
        { name: '7 days', days: 7 },
        { name: '30 days', days: 30 },
        { name: '60 days', days: 60 },
        { name: '90 days', days: 90 }
      ];
      
      for (const period of probePeriods) {
        const testDate = new Date();
        testDate.setDate(testDate.getDate() - period.days);
        
        const hasData = await this.probeForData(account, testDate.getTime());
        if (hasData) {
          this.log('info', `📅 ${account.name}: Auto-detected start: ${period.name} ago (${testDate.toISOString()})`);
          return testDate.getTime();
        }
      }
      
      // 4. Fallback: Letzte 7 Tage
      const fallbackDate = new Date();
      fallbackDate.setDate(fallbackDate.getDate() - 7);
      this.log('info', `📅 ${account.name}: Using fallback: last 7 days (${fallbackDate.toISOString()})`);
      return fallbackDate.getTime();
      
    } catch (error) {
      this.log('error', `Failed to determine start time for ${account.name}`, { error: error.message });
      const fallbackDate = new Date();
      fallbackDate.setDate(fallbackDate.getDate() - 7);
      return fallbackDate.getTime();
    }
  }

  async probeForData(account, startTime) {
    try {
      // Mache einen kleinen Test-Request um zu schauen ob Daten existieren
      let testUrl = account.api.url.replace('limit=1000', 'limit=1');
      
      if (account.api.type === 'bybit_trades') {
        const separator = testUrl.includes('?') ? '&' : '?';
        testUrl += `${separator}startTime=${startTime}&endTime=${Date.now()}`;
      } else if (account.api.type === 'blofin_trades') {
        const separator = testUrl.includes('?') ? '&' : '?';
        testUrl += `${separator}after=${Math.floor(startTime / 1000)}&limit=1`;
      }
      
      const headers = { 'User-Agent': 'Trading-Probe/1.0', 'Accept': 'application/json' };
      
      if (account.api.type === 'bybit_trades') {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(testUrl).search.substring(1);
        
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = recvWindow;
        headers['X-BAPI-SIGN'] = this.createBybitSignature(
          timestamp, account.api.key, recvWindow, queryString, account.api.secret
        );
      }
      
      const response = await fetch(testUrl, { method: 'GET', headers });
      
      if (response.ok) {
        const data = await response.json();
        
        if (account.api.type === 'bybit_trades') {
          return data.result && data.result.list && data.result.list.length > 0;
        } else if (account.api.type === 'blofin_trades') {
          return data.data && data.data.length > 0;
        }
      }
      
      return false;
      
    } catch (error) {
      this.log('warn', `Probe failed for ${account.name}: ${error.message}`);
      return false;
    }
  }

  async fetchAccountData(account) {
    try {
      this.log('info', `📡 Fetching trades from ${account.name}...`);
      
      if (!account.api.key) {
        this.log('warn', `⚠️ ${account.name}: API key missing, skipping`);
        return [];
      }
      
      const startTime = await this.getOptimalStartTime(account);
      const startDate = new Date(startTime);
      this.log('info', `📅 ${account.name}: Getting trades since ${startDate.toISOString()}`);
      
      let apiUrl = account.api.url;
      if (account.api.type === 'bybit_trades') {
        const separator = apiUrl.includes('?') ? '&' : '?';
        apiUrl += `${separator}startTime=${startTime}&endTime=${Date.now()}`;
      } else if (account.api.type === 'blofin_trades') {
        const separator = apiUrl.includes('?') ? '&' : '?';
        apiUrl += `${separator}after=${Math.floor(startTime / 1000)}&limit=100`;
      }
      
      const headers = {
        'User-Agent': 'Trading-Dashboard/1.0',
        'Accept': 'application/json'
      };
      
      if (account.api.type === 'bybit_trades') {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(apiUrl).search.substring(1);
        
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = recvWindow;
        headers['X-BAPI-SIGN'] = this.createBybitSignature(
          timestamp, account.api.key, recvWindow, queryString, account.api.secret
        );
        
      } else if (account.api.type === 'blofin_trades') {
        const timestamp = new Date().toISOString();
        const method = 'GET';
        const requestPath = new URL(apiUrl).pathname + new URL(apiUrl).search;
        
        headers['BF-ACCESS-KEY'] = account.api.key;
        headers['BF-ACCESS-TIMESTAMP'] = timestamp;
        headers['BF-ACCESS-PASSPHRASE'] = account.api.passphrase;
        headers['BF-ACCESS-SIGN'] = this.createBlofinSignature(
          timestamp, method, requestPath, '', account.api.secret
        );
      }
      
      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: headers
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      this.log('info', `✅ ${account.name}: Retrieved trade data`);
      
      return this.processAccountData(account, data);
      
    } catch (error) {
      this.log('error', `❌ ${account.name} failed: ${error.message}`);
      this.errors.push(`${account.name}: ${error.message}`);
      return [];
    }
  }

  processAccountData(account, rawData) {
    const syncId = `sync_${Date.now()}`;
    const rows = [];
    
    try {
      if (account.api.type === 'bybit_trades') {
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          rawData.result.list.forEach(trade => {
            const tradeTime = new Date(parseInt(trade.execTime || Date.now())).toISOString();
            
            rows.push([
              tradeTime,
              account.name,
              trade.category || 'linear',
              trade.symbol,
              trade.execId,
              trade.orderId,
              trade.orderLinkId || '',
              trade.side,
              parseFloat(trade.execQty || 0),
              parseFloat(trade.execPrice || 0),
              trade.orderType,
              trade.execType,
              parseFloat(trade.execValue || 0),
              parseFloat(trade.execFee || 0),
              parseFloat(trade.feeRate || 0),
              parseFloat(trade.tradeIv || 0),
              parseFloat(trade.markIv || 0),
              parseFloat(trade.markPrice || 0),
              parseFloat(trade.indexPrice || 0),
              parseFloat(trade.underlyingPrice || 0),
              trade.blockTradeId || '',
              parseFloat(trade.closedSize || 0),
              trade.seq || 0,
              trade.nextPageCursor || '',
              trade.execTime,
              trade.isMaker || false,
              syncId,
              JSON.stringify(trade)
            ]);
          });
        }
      } else if (account.api.type === 'blofin_trades') {
        if (rawData.data && Array.isArray(rawData.data)) {
          rawData.data.forEach(trade => {
            const tradeTime = new Date(parseInt(trade.ts || Date.now())).toISOString();
            
            rows.push([
              tradeTime,
              account.name,
              trade.instType,
              trade.instId,
              trade.tradeId,
              trade.orderId,
              trade.clOrdId || '',
              trade.billId || '',
              trade.tag || '',
              parseFloat(trade.fillPx || 0),
              parseFloat(trade.fillSz || 0),
              trade.side,
              trade.execType || '',
              trade.feeCcy || '',
              parseFloat(trade.fee || 0),
              trade.ts,
              syncId,
              JSON.stringify(trade)
            ]);
          });
        }
      }
      
      this.log('info', `📊 ${account.name}: Processed ${rows.length} trades`);
      
    } catch (error) {
      this.log('error', `Error processing ${account.name} trade data: ${error.message}`);
    }
    
    return rows;
  }

  async saveToGoogleSheet(account, data) {
    if (data.length === 0) {
      this.log('info', `ℹ️ ${account.name}: No new trades to save`);
      return 0;
    }
    
    try {
      this.log('info', `💾 ${account.name}: Saving ${data.length} trades...`);
      
      const existingData = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${account.sheetName}!A:A`,
      });
      
      const nextRow = (existingData.data.values?.length || 1) + 1;
      const endCol = account.api.type === 'bybit_trades' ? 'AB' : 'R';
      const range = `${account.sheetName}!A${nextRow}:${endCol}${nextRow + data.length - 1}`;
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: range,
        valueInputOption: 'RAW',
        resource: { values: data },
      });
      
      this.log('info', `✅ ${account.name}: Saved ${data.length} trades!`);
      return data.length;
      
    } catch (error) {
      this.log('error', `${account.name}: Save failed - ${error.message}`);
      return 0;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting FLEXIBLE Trading History Sync...');
    this.log('info', '📅 Auto-detecting optimal date ranges per account...');
    this.log('info', `📊 Processing ${this.accounts.length} trading accounts...`);
    
    try {
      await this.initializeGoogleSheets();
      
      for (const account of this.accounts) {
        const trades = await this.fetchAccountData(account);
        const savedCount = await this.saveToGoogleSheet(account, trades);
        
        if (savedCount > 0) {
          this.successfulAccounts++;
          this.totalRecords += savedCount;
        }
        
        this.log('info', '⏳ Rate limiting: 3 seconds between accounts...');
        await new Promise(r => setTimeout(r, 3000));
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      const summary = {
        duration: `${duration.toFixed(1)}s`,
        totalTrades: this.totalRecords,
        successfulAccounts: this.successfulAccounts,
        totalAccounts: this.accounts.length,
        errors: this.errors.length
      };
      
      this.log('info', '🎉 FLEXIBLE Trading History Sync completed!', summary);
      this.log('info', `📈 Total trades imported: ${this.totalRecords}`);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some accounts had errors:', { errors: this.errors });
      }
      
      const exitCode = this.successfulAccounts > 0 ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 FLEXIBLE Trading History Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new FlexibleTradingHistorySync();
syncer.runSync();
