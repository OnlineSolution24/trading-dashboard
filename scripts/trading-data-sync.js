// scripts/trading-data-sync.js
const { google } = require('googleapis');
const fetch = require('node-fetch');

class TradingDataSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    
    // Nur Bybit und Blofin APIs
    this.apis = [
      {
        name: 'Bybit',
        url: 'https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT,LINKUSDT,DOTUSDT,AVAXUSDT,MATICUSDT',
        requiresAuth: true,
        apiKey: process.env.BYBIT_API_KEY,
        rateLimitMs: 1000
      },
      {
        name: 'Blofin',
        url: 'https://openapi.blofin.com/api/v1/market/tickers',
        requiresAuth: true,
        apiKey: process.env.BLOFIN_API_KEY,
        rateLimitMs: 2000
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
      
      if (!process.env.GOOGLE_SHEET_ID) {
        throw new Error('GOOGLE_SHEET_ID missing');
      }
      if (!process.env.GOOGLE_CLIENT_EMAIL) {
        throw new Error('GOOGLE_CLIENT_EMAIL missing');
      }
      if (!process.env.GOOGLE_PRIVATE_KEY) {
        throw new Error('GOOGLE_PRIVATE_KEY missing');
      }

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
      this.sheetName = response.data.sheets[0].properties.title;
      
      await this.ensureHeaders();
      return true;
      
    } catch (error) {
      this.log('error', 'Google Sheets failed', { error: error.message });
      throw error;
    }
  }

  async ensureHeaders() {
    try {
      const response = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${this.sheetName}!A1:I1`,
      });
      
      if (!response.data.values || response.data.values.length === 0) {
        const headers = [
          'timestamp', 
          'source', 
          'symbol', 
          'price_usd', 
          'change_24h_percent', 
          'volume_24h', 
          'high_24h',
          'low_24h',
          'sync_id'
        ];
        
        await this.sheets.spreadsheets.values.update({
          spreadsheetId: this.spreadsheetId,
          range: `${this.sheetName}!A1:I1`,
          valueInputOption: 'RAW',
          resource: { values: [headers] },
        });
        
        this.log('info', '✅ Headers created');
      } else {
        this.log('info', '📋 Headers exist');
      }
      
    } catch (error) {
      this.log('error', 'Header setup failed', { error: error.message });
    }
  }

  async fetchApiData(api) {
    try {
      this.log('info', `📡 Fetching ${api.name}...`);
      
      if (api.requiresAuth && !api.apiKey) {
        this.log('warn', `⚠️ ${api.name}: API key missing, skipping`);
        return [];
      }
      
      const headers = {
        'User-Agent': 'Trading-Sync/1.0',
        'Accept': 'application/json'
      };
      
      // Bybit Authentication
      if (api.name === 'Bybit' && api.apiKey) {
        headers['X-BAPI-API-KEY'] = api.apiKey;
        headers['X-BAPI-TIMESTAMP'] = Date.now().toString();
        headers['X-BAPI-RECV-WINDOW'] = '5000';
      }
      
      // Blofin Authentication
      if (api.name === 'Blofin' && api.apiKey) {
        headers['BF-ACCESS-KEY'] = api.apiKey;
        headers['BF-ACCESS-TIMESTAMP'] = new Date().toISOString();
        // Für vollständige Blofin Auth würde hier auch Signatur berechnet werden
      }
      
      const response = await fetch(api.url, {
        method: 'GET',
        headers: headers
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      this.log('info', `✅ ${api.name}: Got data`);
      
      return this.processApiData(api.name, data);
      
    } catch (error) {
      this.log('error', `❌ ${api.name} failed: ${error.message}`);
      this.errors.push(`${api.name}: ${error.message}`);
      return [];
    }
  }

  processApiData(source, rawData) {
    const timestamp = new Date().toISOString();
    const syncId = `sync_${Date.now()}`;
    const rows = [];
    
    try {
      if (source === 'Bybit') {
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          rawData.result.list.forEach(item => {
            rows.push([
              timestamp,
              source,
              item.symbol,
              parseFloat(item.lastPrice || 0),
              parseFloat(item.price24hPcnt || 0) * 100, // Convert to percentage
              parseFloat(item.volume24h || 0),
              parseFloat(item.highPrice24h || 0),
              parseFloat(item.lowPrice24h || 0),
              syncId
            ]);
          });
          this.log('info', `📊 Bybit: Processed ${rows.length} trading pairs`);
        }
      } else if (source === 'Blofin') {
        if (rawData.data && Array.isArray(rawData.data)) {
          rawData.data.forEach(item => {
            // Filter nur die wichtigsten Trading Pairs
            const majorPairs = ['BTC-USDT', 'ETH-USDT', 'ADA-USDT', 'SOL-USDT', 'LINK-USDT'];
            if (majorPairs.includes(item.instId)) {
              rows.push([
                timestamp,
                source,
                item.instId,
                parseFloat(item.last || 0),
                parseFloat(item.sodUtc8 || 0), // 24h change
                parseFloat(item.vol24h || 0),
                parseFloat(item.high24h || 0),
                parseFloat(item.low24h || 0),
                syncId
              ]);
            }
          });
          this.log('info', `📊 Blofin: Processed ${rows.length} major trading pairs`);
        }
      }
      
    } catch (error) {
      this.log('error', `Error processing ${source} data: ${error.message}`);
    }
    
    return rows;
  }

  async saveToGoogleSheets(allData) {
    if (allData.length === 0) {
      this.log('info', 'ℹ️ No data to save');
      return 0;
    }
    
    try {
      this.log('info', `💾 Saving ${allData.length} records...`);
      
      const existingData = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${this.sheetName}!A:A`,
      });
      
      const nextRow = (existingData.data.values?.length || 1) + 1;
      const range = `${this.sheetName}!A${nextRow}:I${nextRow + allData.length - 1}`;
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: range,
        valueInputOption: 'RAW',
        resource: { values: allData },
      });
      
      this.log('info', `✅ Saved ${allData.length} trading records!`);
      return allData.length;
      
    } catch (error) {
      this.log('error', `Save failed: ${error.message}`);
      throw error;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting Bybit & Blofin sync...');
    
    try {
      await this.initializeGoogleSheets();
      
      let allData = [];
      let successfulApis = 0;
      
      for (const api of this.apis) {
        const data = await this.fetchApiData(api);
        if (data.length > 0) {
          allData = allData.concat(data);
          successfulApis++;
        }
        
        // Rate limiting zwischen API-Calls
        if (api.rateLimitMs) {
          this.log('info', `⏳ Waiting ${api.rateLimitMs}ms...`);
          await new Promise(r => setTimeout(r, api.rateLimitMs));
        }
      }
      
      this.totalRecords = await this.saveToGoogleSheets(allData);
      
      const duration = (new Date() - this.startTime) / 1000;
      const summary = {
        duration: `${duration.toFixed(1)}s`,
        totalRecords: this.totalRecords,
        successfulApis: successfulApis,
        totalApis: this.apis.length,
        errors: this.errors.length
      };
      
      this.log('info', '🎉 Sync completed!', summary);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some APIs had errors:', { errors: this.errors });
      }
      
      // Exit mit Status basierend auf Erfolg
      const exitCode = successfulApis > 0 ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new TradingDataSync();
syncer.runSync();
