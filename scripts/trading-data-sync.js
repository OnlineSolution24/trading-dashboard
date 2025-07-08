// scripts/trading-data-sync.js
const { google } = require('googleapis');
const fetch = require('node-fetch');

class TradingDataSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    
    this.apis = [
      {
        name: 'CoinGecko',
        url: 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,cardano,solana&vs_currencies=usd&include_24hr_change=true',
        requiresAuth: false,
        rateLimitMs: 1000
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
        const headers = ['timestamp', 'source', 'symbol', 'price_usd', 'change_24h', 'market_cap', 'volume_24h', 'sync_id', 'raw_data'];
        
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
      
      const response = await fetch(api.url, {
        headers: { 'User-Agent': 'Trading-Sync/1.0' }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      this.log('info', `✅ ${api.name}: Got data`);
      
      return this.processApiData(api.name, data);
      
    } catch (error) {
      this.log('error', `❌ ${api.name} failed: ${error.message}`);
      return [];
    }
  }

  processApiData(source, rawData) {
    const timestamp = new Date().toISOString();
    const syncId = `sync_${Date.now()}`;
    const rows = [];
    
    if (source === 'CoinGecko') {
      Object.entries(rawData).forEach(([coin, data]) => {
        rows.push([
          timestamp,
          source,
          coin.toUpperCase(),
          data.usd || 0,
          data.usd_24h_change || 0,
          data.usd_market_cap || 0,
          null,
          syncId,
          JSON.stringify(data)
        ]);
      });
    }
    
    return rows;
  }

  async saveToGoogleSheets(allData) {
    if (allData.length === 0) {
      this.log('info', 'No data to save');
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
      
      this.log('info', `✅ Saved ${allData.length} records!`);
      return allData.length;
      
    } catch (error) {
      this.log('error', `Save failed: ${error.message}`);
      throw error;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting sync...');
    
    try {
      await this.initializeGoogleSheets();
      
      let allData = [];
      for (const api of this.apis) {
        const data = await this.fetchApiData(api);
        allData = allData.concat(data);
        await new Promise(r => setTimeout(r, 1000));
      }
      
      await this.saveToGoogleSheets(allData);
      
      this.log('info', '🎉 Sync completed!');
      process.exit(0);
      
    } catch (error) {
      this.log('error', `💥 Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new TradingDataSync();
syncer.runSync();
