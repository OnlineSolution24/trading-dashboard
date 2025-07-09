const { google } = require('googleapis');
const fetch = require('node-fetch');
const crypto = require('crypto');

class ExtendedTradingSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    this.successfulAccounts = 0;
    
    this.accounts = [
      {
        name: 'Claude Projekt',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_Claude_Projekt_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'Claude_Projekt_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear',
            sheetName: 'Claude_Projekt_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET
        }
      }
    ];
  }

  log(level, message, data) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ${level.toUpperCase()}: ${message}`);
    if (data) console.log('Data:', JSON.stringify(data, null, 2));
  }

  createBybitSignature(timestamp, apiKey, recvWindow, queryString, secret) {
    const param = timestamp + apiKey + recvWindow + queryString;
    return crypto.createHmac('sha256', secret).update(param).digest('hex');
  }

  async initializeGoogleSheets() {
    try {
      this.log('info', '🔗 Initializing Google Sheets...');
      
      const auth = new google.auth.GoogleAuth({
        credentials: {
          client_email: process.env.GOOGLE_CLIENT_EMAIL,
          private_key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
        },
        scopes: ['https://www.googleapis.com/auth/spreadsheets'],
      });

      this.sheets = google.sheets({ version: 'v4', auth });
      this.spreadsheetId = process.env.GOOGLE_SHEET_ID;
      
      this.log('info', '✅ Google Sheets connected');
      return true;
      
    } catch (error) {
      this.log('error', `Google Sheets connection failed: ${error.message}`);
      throw error;
    }
  }

  async getLastSyncTime(sheetName) {
    try {
      const response = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${sheetName}!A:A`,
      });
      
      if (!response.data.values || response.data.values.length <= 1) {
        const oneDayAgo = new Date();
        oneDayAgo.setDate(oneDayAgo.getDate() - 1);
        this.log('info', `${sheetName}: Starting from 24h ago`);
        return oneDayAgo.getTime();
      }
      
      const timestamps = response.data.values
        .slice(1)
        .map(row => {
          if (!row[0]) return null;
          const date = new Date(row[0]);
          return isNaN(date.getTime()) ? null : date.getTime();
        })
        .filter(ts => ts !== null)
        .sort((a, b) => b - a);
      
      if (timestamps.length > 0) {
        const lastSync = timestamps[0] + (5 * 60 * 1000);
        this.log('info', `${sheetName}: Last sync + 5min`);
        return lastSync;
      }
      
      const oneDayAgo = new Date();
      oneDayAgo.setDate(oneDayAgo.getDate() - 1);
      return oneDayAgo.getTime();
      
    } catch (error) {
      this.log('error', `Failed to get last sync time: ${error.message}`);
      const oneDayAgo = new Date();
      oneDayAgo.setDate(oneDayAgo.getDate() - 1);
      return oneDayAgo.getTime();
    }
  }

  async syncAccount(account) {
    this.log('info', `🔄 Syncing ${account.name}...`);
    
    if (!account.api.key) {
      this.log('warn', `⚠️ ${account.name}: API key missing, skipping`);
      return;
    }
    
    for (const [endpointType, endpoint] of Object.entries(account.endpoints)) {
      try {
        this.log('info', `📡 Fetching ${endpointType} for ${account.name}`);
        
        const startTime = await this.getLastSyncTime(endpoint.sheetName);
        const endTime = Date.now();
        
        let apiUrl = endpoint.url;
        if (endpointType !== 'positions') {
          const separator = apiUrl.includes('?') ? '&' : '?';
          apiUrl += `${separator}startTime=${startTime}&endTime=${endTime}`;
        }
        
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(apiUrl).search.substring(1);
        
        const headers = {
          'User-Agent': 'Trading-Dashboard-Extended/1.0',
          'Accept': 'application/json',
          'X-BAPI-API-KEY': account.api.key,
          'X-BAPI-TIMESTAMP': timestamp,
          'X-BAPI-RECV-WINDOW': recvWindow,
          'X-BAPI-SIGN': this.createBybitSignature(
            timestamp, account.api.key, recvWindow, queryString, account.api.secret
          )
        };
        
        const response = await fetch(apiUrl, { method: 'GET', headers });
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const data = await response.json();
        
        if (data.retCode !== 0) {
          throw new Error(`Bybit API Error ${data.retCode}: ${data.retMsg}`);
        }
        
        const itemCount = data.result?.list?.length || 0;
        this.log('info', `✅ ${account.name} ${endpointType}: ${itemCount} items`);
        
        if (itemCount > 0) {
          await this.saveData(endpoint.sheetName, data.result.list, endpointType, account.name);
        }
        
        await new Promise(r => setTimeout(r, 1000));
        
      } catch (error) {
        this.log('error', `❌ ${account.name} ${endpointType}: ${error.message}`);
        this.errors.push(`${account.name} ${endpointType}: ${error.message}`);
      }
    }
  }

  async saveData(sheetName, items, endpointType, accountName) {
    if (!items || items.length === 0) return;
    
    try {
      const syncId = `sync_${endpointType}_${Date.now()}`;
      const currentTimestamp = new Date().toISOString();
      const rows = [];
      
      items.forEach(item => {
        if (endpointType === 'executions') {
          const execTime = new Date(parseInt(item.execTime || Date.now())).toISOString();
          rows.push([
            execTime,
            accountName,
            item.symbol,
            item.side,
            parseFloat(item.execQty || 0),
            parseFloat(item.orderPrice || 0),
            parseFloat(item.execPrice || 0),
            0,
            'Trade',
            item.execId,
            execTime,
            parseFloat(item.execFee || 0),
            item.feeCurrency || 'USDT',
            'API_SYNC',
            currentTimestamp,
            JSON.stringify(item)
          ]);
        } else if (endpointType === 'positions') {
          const posTime = new Date(parseInt(item.updatedTime || Date.now())).toISOString();
          if (parseFloat(item.size || 0) !== 0) {
            rows.push([
              posTime,
              accountName,
              item.category || 'linear',
              item.symbol,
              item.side || 'None',
              parseFloat(item.size || 0),
              parseFloat(item.positionValue || 0),
              parseFloat(item.avgPrice || 0),
              parseFloat(item.markPrice || 0),
              parseFloat(item.liqPrice || 0),
              parseFloat(item.unrealisedPnl || 0),
              parseFloat(item.cumRealisedPnl || 0),
              parseFloat(item.cumRealisedPnl || 0),
              parseFloat(item.leverage || 0),
              item.tradeMode || 'cross',
              item.positionStatus || 'Normal',
              item.createdTime || posTime,
              item.updatedTime || posTime,
              'API_SYNC',
              currentTimestamp,
              JSON.stringify(item)
            ]);
          }
        }
      });
      
      if (rows.length > 0) {
        const existingData = await this.sheets.spreadsheets.values.get({
          spreadsheetId: this.spreadsheetId,
          range: `${sheetName}!A:A`,
        });
        
        const nextRow = (existingData.data.values?.length || 1) + 1;
        const endCol = endpointType === 'executions' ? 'P' : endpointType === 'positions' ? 'U' : 'Z';
        const range = `${sheetName}!A${nextRow}:${endCol}${nextRow + rows.length - 1}`;
        
        await this.sheets.spreadsheets.values.update({
          spreadsheetId: this.spreadsheetId,
          range: range,
          valueInputOption: 'RAW',
          resource: { values: rows },
        });
        
        this.log('info', `💾 Saved ${rows.length} ${endpointType} to ${sheetName}`);
        this.totalRecords += rows.length;
      }
      
    } catch (error) {
      this.log('error', `Failed to save ${endpointType} data: ${error.message}`);
    }
  }

  async runExtendedSync() {
    this.log('info', '🚀 Starting Extended Trading Sync...');
    this.log('info', '📊 Syncing Orders + Executions + Positions...');
    
    try {
      await this.initializeGoogleSheets();
      
      for (const account of this.accounts) {
        await this.syncAccount(account);
        this.successfulAccounts++;
        await new Promise(r => setTimeout(r, 3000));
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      this.log('info', `🎉 Extended sync completed in ${duration.toFixed(1)}s`);
      this.log('info', `📊 Total records: ${this.totalRecords}`);
      
      if (this.errors.length > 0) {
        this.log('warn', `⚠️ ${this.errors.length} errors occurred`);
        this.errors.forEach(error => this.log('error', error));
      }
      
      process.exit(this.totalRecords > 0 ? 0 : 1);
      
    } catch (error) {
      this.log('error', `💥 Extended sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new ExtendedTradingSync();
syncer.runExtendedSync();
