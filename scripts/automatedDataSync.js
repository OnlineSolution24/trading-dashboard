// scripts/automatedDataSync.js
const { GoogleSpreadsheet } = require('google-spreadsheet');
const fs = require('fs').promises;
const path = require('path');

class AutomatedTradingDataSync {
  constructor() {
    this.startTime = new Date();
    this.logEntries = [];
    this.successCount = 0;
    this.errorCount = 0;
    
    // API Konfiguration - passe an deine spezifischen APIs an
    this.apis = [
      {
        name: 'Binance',
        endpoint: 'https://api.binance.com/api/v3/ticker/24hr',
        apiKey: process.env.BINANCE_API_KEY,
        rateLimitMs: 1200,
        headers: { 'X-MBX-APIKEY': process.env.BINANCE_API_KEY }
      },
      {
        name: 'Coinbase',
        endpoint: 'https://api.exchange.coinbase.com/products',
        apiKey: process.env.COINBASE_API_KEY,
        rateLimitMs: 1000,
        headers: { 'CB-ACCESS-KEY': process.env.COINBASE_API_KEY }
      },
      {
        name: 'Kraken',
        endpoint: 'https://api.kraken.com/0/public/Ticker',
        apiKey: process.env.KRAKEN_API_KEY,
        rateLimitMs: 1500,
        headers: {}
      },
      {
        name: 'AlphaVantage',
        endpoint: 'https://www.alphavantage.co/query',
        apiKey: process.env.ALPHA_VANTAGE_API_KEY,
        rateLimitMs: 12000, // 5 calls per minute
        headers: {}
      },
      {
        name: 'Polygon',
        endpoint: 'https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks',
        apiKey: process.env.POLYGON_API_KEY,
        rateLimitMs: 2000,
        headers: { 'Authorization': `Bearer ${process.env.POLYGON_API_KEY}` }
      },
      {
        name: 'TwelveData',
        endpoint: 'https://api.twelvedata.com/time_series',
        apiKey: process.env.TWELVEDATA_API_KEY,
        rateLimitMs: 8000, // 8 calls per minute for free tier
        headers: {}
      },
      {
        name: 'Finnhub',
        endpoint: 'https://finnhub.io/api/v1/quote',
        apiKey: process.env.FINNHUB_API_KEY,
        rateLimitMs: 1000,
        headers: { 'X-Finnhub-Token': process.env.FINNHUB_API_KEY }
      },
      {
        name: 'TradingView',
        endpoint: 'https://scanner.tradingview.com/markets/scan',
        apiKey: process.env.TRADINGVIEW_API_KEY,
        rateLimitMs: 2000,
        headers: {}
      },
      {
        name: 'YahooFinance',
        endpoint: 'https://yfapi.net/v6/finance/quote',
        apiKey: process.env.YAHOO_FINANCE_API_KEY,
        rateLimitMs: 1000,
        headers: { 'X-API-KEY': process.env.YAHOO_FINANCE_API_KEY }
      },
      {
        name: 'MarketStack',
        endpoint: 'https://api.marketstack.com/v1/eod/latest',
        apiKey: process.env.MARKETSTACK_API_KEY,
        rateLimitMs: 1000,
        headers: {}
      },
      {
        name: 'IEXCloud',
        endpoint: 'https://cloud.iexapis.com/stable/stock/market/batch',
        apiKey: process.env.IEXCLOUD_API_KEY,
        rateLimitMs: 1000,
        headers: {}
      }
    ];
  }

  log(level, message, data = null) {
    const timestamp = new Date().toISOString();
    const logEntry = { timestamp, level, message, data };
    this.logEntries.push(logEntry);
    console.log(`[${timestamp}] ${level.toUpperCase()}: ${message}`, data || '');
  }

  async initializeGoogleSheets() {
    try {
      this.log('info', 'Initializing Google Sheets connection...');
      
      const doc = new GoogleSpreadsheet(process.env.GOOGLE_SHEET_ID);
      
      await doc.useServiceAccountAuth({
        client_email: process.env.GOOGLE_CLIENT_EMAIL,
        private_key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n'),
      });
      
      await doc.loadInfo();
      this.sheet = doc.sheetsByTitle['TradingData'] || doc.sheetsByIndex[0];
      
      // Erstelle Header falls nicht vorhanden
      await this.ensureHeaders();
      
      this.log('info', `Connected to sheet: ${doc.title}`);
      return true;
    } catch (error) {
      this.log('error', 'Failed to initialize Google Sheets', error.message);
      throw error;
    }
  }

  async ensureHeaders() {
    const headers = await this.sheet.headerValues;
    const requiredHeaders = [
      'timestamp', 'source', 'symbol', 'price', 'volume', 
      'change_24h', 'market_cap', 'data_json', 'sync_id'
    ];
    
    if (headers.length === 0) {
      await this.sheet.setHeaderRow(requiredHeaders);
      this.log('info', 'Header row created in Google Sheet');
    }
  }

  async getLastSyncTimestamp(apiName) {
    try {
      const rows = await this.sheet.getRows();
      const apiRows = rows.filter(row => row.source === apiName);
      
      if (apiRows.length === 0) {
        // Erstes Mal - hole Daten der letzten 24 Stunden
        const yesterday = new Date();
        yesterday.setHours(yesterday.getHours() - 24);
        return yesterday;
      }
      
      // Sortiere nach Timestamp und nimm den neuesten
      const sortedRows = apiRows.sort((a, b) => 
        new Date(b.timestamp) - new Date(a.timestamp)
      );
      
      return new Date(sortedRows[0].timestamp);
    } catch (error) {
      this.log('error', `Error getting last sync timestamp for ${apiName}`, error.message);
      // Fallback: letzte 2 Stunden
      const fallbackTime = new Date();
      fallbackTime.setHours(fallbackTime.getHours() - 2);
      return fallbackTime;
    }
  }

  async fetchApiData(api, sinceTimestamp) {
    try {
      this.log('info', `Fetching data from ${api.name}...`);
      
      // API-spezifische Parameter basierend auf dem letzten Sync
      const params = this.buildApiParams(api, sinceTimestamp);
      const url = `${api.endpoint}${params}`;
      
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Trading-Dashboard/1.0',
          ...api.headers
        },
        timeout: 30000
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      const processedData = this.processApiResponse(api.name, data);
      
      this.log('info', `${api.name}: Received ${processedData.length} records`);
      return processedData;
      
    } catch (error) {
      this.log('error', `Failed to fetch from ${api.name}`, error.message);
      return [];
    }
  }

  buildApiParams(api, sinceTimestamp) {
    // Beispiel-Parameter - passe diese an deine spezifischen APIs an
    const params = new URLSearchParams();
    
    switch (api.name) {
      case 'AlphaVantage':
        params.append('function', 'TIME_SERIES_INTRADAY');
        params.append('symbol', 'AAPL');
        params.append('interval', '1hour');
        params.append('apikey', api.apiKey);
        break;
        
      case 'Polygon':
        const dateStr = sinceTimestamp.toISOString().split('T')[0];
        return `/${dateStr}?adjusted=true&apiKey=${api.apiKey}`;
        
      case 'TwelveData':
        params.append('symbol', 'AAPL');
        params.append('interval', '1h');
        params.append('apikey', api.apiKey);
        params.append('start_date', sinceTimestamp.toISOString().split('T')[0]);
        break;
        
      case 'MarketStack':
        params.append('access_key', api.apiKey);
        params.append('date_from', sinceTimestamp.toISOString().split('T')[0]);
        params.append('limit', '100');
        break;
        
      case 'IEXCloud':
        params.append('symbols', 'AAPL,MSFT,GOOGL');
        params.append('types', 'quote');
        params.append('token', api.apiKey);
        break;
        
      default:
        // Für APIs ohne spezielle Parameter
        if (api.apiKey && !api.headers['Authorization']) {
          params.append('apikey', api.apiKey);
        }
    }
    
    return params.toString() ? `?${params.toString()}` : '';
  }

  processApiResponse(apiName, rawData) {
    const processedData = [];
    const currentTime = new Date().toISOString();
    
    try {
      switch (apiName) {
        case 'Binance':
          rawData.forEach(item => {
            processedData.push({
              timestamp: currentTime,
              source: apiName,
              symbol: item.symbol,
              price: parseFloat(item.lastPrice),
              volume: parseFloat(item.volume),
              change_24h: parseFloat(item.priceChangePercent),
              market_cap: null,
              data_json: JSON.stringify(item)
            });
          });
          break;
          
        case 'Coinbase':
          rawData.forEach(item => {
            processedData.push({
              timestamp: currentTime,
              source: apiName,
              symbol: item.id,
              price: parseFloat(item.price || 0),
              volume: parseFloat(item.volume_24h || 0),
              change_24h: null,
              market_cap: null,
              data_json: JSON.stringify(item)
            });
          });
          break;
          
        case 'AlphaVantage':
          if (rawData['Time Series (1hour)']) {
            Object.entries(rawData['Time Series (1hour)']).forEach(([time, data]) => {
              processedData.push({
                timestamp: time,
                source: apiName,
                symbol: rawData['Meta Data']['2. Symbol'],
                price: parseFloat(data['4. close']),
                volume: parseFloat(data['5. volume']),
                change_24h: null,
                market_cap: null,
                data_json: JSON.stringify(data)
              });
            });
          }
          break;
          
        default:
          // Generische Verarbeitung für andere APIs
          if (Array.isArray(rawData)) {
            rawData.forEach(item => {
              processedData.push({
                timestamp: currentTime,
                source: apiName,
                symbol: item.symbol || item.ticker || 'UNKNOWN',
                price: parseFloat(item.price || item.last || item.close || 0),
                volume: parseFloat(item.volume || 0),
                change_24h: parseFloat(item.change || item.change_percent || 0),
                market_cap: parseFloat(item.market_cap || 0),
                data_json: JSON.stringify(item)
              });
            });
          }
      }
    } catch (error) {
      this.log('error', `Error processing ${apiName} response`, error.message);
    }
    
    return processedData;
  }

  async insertDataToSheet(data) {
    if (data.length === 0) return 0;
    
    try {
      const syncId = `sync_${Date.now()}`;
      const rowsToInsert = data.map(item => ({
        ...item,
        sync_id: syncId
      }));
      
      await this.sheet.addRows(rowsToInsert);
      this.log('info', `Inserted ${data.length} rows to Google Sheet`);
      return data.length;
      
    } catch (error) {
      this.log('error', 'Failed to insert data to Google Sheet', error.message);
      throw error;
    }
  }

  async syncSingleApi(api) {
    try {
      const lastSync = await this.getLastSyncTimestamp(api.name);
      this.log('info', `${api.name}: Last sync was at ${lastSync.toISOString()}`);
      
      const newData = await this.fetchApiData(api, lastSync);
      
      if (newData.length > 0) {
        const insertedCount = await this.insertDataToSheet(newData);
        this.successCount += insertedCount;
        this.log('info', `${api.name}: Successfully synced ${insertedCount} records`);
      } else {
        this.log('info', `${api.name}: No new data to sync`);
      }
      
      // Rate Limiting
      await new Promise(resolve => setTimeout(resolve, api.rateLimitMs));
      
    } catch (error) {
      this.errorCount++;
      this.log('error', `${api.name}: Sync failed`, error.message);
    }
  }

  async sendNotification(summary) {
    try {
      if (process.env.DISCORD_WEBHOOK_URL) {
        await fetch(process.env.DISCORD_WEBHOOK_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content: `🔄 **Trading Data Sync Complete**\n\`\`\`\n${summary}\n\`\`\``
          })
        });
      }
      
      if (process.env.SLACK_WEBHOOK_URL) {
        await fetch(process.env.SLACK_WEBHOOK_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `Trading Data Sync Complete\n${summary}`
          })
        });
      }
    } catch (error) {
      this.log('error', 'Failed to send notification', error.message);
    }
  }

  async saveLogs() {
    try {
      const logsDir = path.join(process.cwd(), 'logs');
      await fs.mkdir(logsDir, { recursive: true });
      
      const logFile = path.join(logsDir, `sync_${this.startTime.toISOString().split('T')[0]}.json`);
      await fs.writeFile(logFile, JSON.stringify(this.logEntries, null, 2));
      
      console.log(`Logs saved to: ${logFile}`);
    } catch (error) {
      console.error('Failed to save logs:', error.message);
    }
  }

  async runAutomatedSync() {
    this.log('info', '🚀 Starting automated trading data sync...');
    
    try {
      await this.initializeGoogleSheets();
      
      for (const api of this.apis) {
        if (!api.apiKey) {
          this.log('warn', `${api.name}: API key not configured, skipping...`);
          continue;
        }
        
        await this.syncSingleApi(api);
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      const summary = [
        `Duration: ${duration.toFixed(1)}s`,
        `Success: ${this.successCount} records`,
        `Errors: ${this.errorCount} APIs`,
        `APIs processed: ${this.apis.filter(api => api.apiKey).length}/${this.apis.length}`
      ].join('\n');
      
      this.log('info', `✅ Sync completed successfully!\n${summary}`);
      
      await this.sendNotification(summary);
      await this.saveLogs();
      
    } catch (error) {
      this.log('error', '❌ Sync failed with critical error', error.message);
      await this.saveLogs();
      process.exit(1);
    }
  }
}

// Script ausführen
const syncManager = new AutomatedTradingDataSync();
syncManager.runAutomatedSync().catch(error => {
  console.error('Critical error:', error);
  process.exit(1);
});
