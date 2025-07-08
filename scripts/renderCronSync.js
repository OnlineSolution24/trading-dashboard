// scripts/renderCronSync.js
import { GoogleSpreadsheet } from 'google-spreadsheet';

class TradingDataSync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    
    // API Konfiguration für Bybit und Blofin
    this.apis = [
      {
        name: 'Bybit',
        url: 'https://api.bybit.com/v5/market/tickers?category=spot&symbol=BTCUSDT,ETHUSDT,ADAUSDT,SOLUSDT',
        requiresAuth: true,
        apiKey: process.env.BYBIT_API_KEY,
        apiSecret: process.env.BYBIT_API_SECRET,
        headers: process.env.BYBIT_API_KEY ? { 
          'X-BAPI-API-KEY': process.env.BYBIT_API_KEY,
          'X-BAPI-TIMESTAMP': '',
          'X-BAPI-SIGN': ''
        } : {},
        rateLimitMs: 1000
      },
      {
        name: 'Blofin',
        url: 'https://openapi.blofin.com/api/v1/market/tickers',
        requiresAuth: true,
        apiKey: process.env.BLOFIN_API_KEY,
        apiSecret: process.env.BLOFIN_API_SECRET,
        passphrase: process.env.BLOFIN_PASSPHRASE,
        headers: process.env.BLOFIN_API_KEY ? {
          'BF-ACCESS-KEY': process.env.BLOFIN_API_KEY,
          'BF-ACCESS-TIMESTAMP': '',
          'BF-ACCESS-SIGN': '',
          'BF-ACCESS-PASSPHRASE': process.env.BLOFIN_PASSPHRASE
        } : {},
        rateLimitMs: 2000
      },
      {
        name: 'CoinGecko',
        url: 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,cardano,solana&vs_currencies=usd&include_24hr_change=true&include_market_cap=true',
        requiresAuth: false,
        rateLimitMs: 1000
      }
    ];
  }

  log(level, message, data = null) {
    const timestamp = new Date().toISOString();
    const logMessage = `[${timestamp}] ${level.toUpperCase()}: ${message}`;
    console.log(logMessage);
    
    if (data) {
      console.log('Data:', JSON.stringify(data, null, 2));
    }
  }

  async initializeGoogleSheets() {
    try {
      this.log('info', '🔗 Initializing Google Sheets connection...');
      
      // Prüfe Environment Variables
      if (!process.env.GOOGLE_SHEET_ID) {
        throw new Error('GOOGLE_SHEET_ID environment variable is missing');
      }
      if (!process.env.GOOGLE_CLIENT_EMAIL) {
        throw new Error('GOOGLE_CLIENT_EMAIL environment variable is missing');
      }
      if (!process.env.GOOGLE_PRIVATE_KEY) {
        throw new Error('GOOGLE_PRIVATE_KEY environment variable is missing');
      }

      const doc = new GoogleSpreadsheet(process.env.GOOGLE_SHEET_ID);
      
      await doc.useServiceAccountAuth({
        client_email: process.env.GOOGLE_CLIENT_EMAIL,
        private_key: process.env.GOOGLE_PRIVATE_KEY.replace(/\\n/g, '\n')
      });
      
      await doc.loadInfo();
      this.log('info', `📊 Connected to sheet: "${doc.title}"`);
      
      // Verwende erstes Sheet oder erstelle neues
      if (doc.sheetsByIndex.length === 0) {
        this.sheet = await doc.addSheet({ title: 'TradingData' });
        this.log('info', '📝 Created new sheet: TradingData');
      } else {
        this.sheet = doc.sheetsByIndex[0];
        this.log('info', `📄 Using existing sheet: "${this.sheet.title}"`);
      }
      
      // Header prüfen/erstellen
      await this.ensureHeaders();
      
      return true;
      
    } catch (error) {
      this.log('error', 'Failed to initialize Google Sheets', { error: error.message });
      throw error;
    }
  }

  async ensureHeaders() {
    try {
      const headers = await this.sheet.headerValues;
      const requiredHeaders = [
        'timestamp', 
        'source', 
        'symbol', 
        'price_usd', 
        'change_24h_percent', 
        'market_cap_usd',
        'volume_24h',
        'sync_id',
        'raw_data'
      ];
      
      if (headers.length === 0) {
        await this.sheet.setHeaderRow(requiredHeaders);
        this.log('info', '✅ Header row created in Google Sheet');
      } else {
        this.log('info', `📋 Found ${headers.length} existing headers`);
      }
      
    } catch (error) {
      this.log('error', 'Failed to ensure headers', { error: error.message });
      throw error;
    }
  }

  async fetchApiData(api) {
    try {
      this.log('info', `📡 Fetching data from ${api.name}...`);
      
      // Prüfe API Key falls erforderlich
      if (api.requiresAuth && !api.apiKey) {
        this.log('warn', `⚠️ ${api.name}: API key not configured, skipping`);
        return [];
      }
      
      // Spezielle Authentifikation für verschiedene APIs
      let headers = {
        'User-Agent': 'Trading-Dashboard-Sync/1.0',
        'Accept': 'application/json',
        ...api.headers
      };
      
      // Bybit Authentifikation
      if (api.name === 'Bybit' && api.apiKey && api.apiSecret) {
        const timestamp = Date.now().toString();
        const queryString = new URL(api.url).search.substring(1);
        const signaturePayload = timestamp + api.apiKey + '5000' + queryString;
        
        // Einfache HMAC-SHA256 Signatur (für Production solltest du crypto verwenden)
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = '5000';
        // Signatur würde hier berechnet werden - für Demo vereinfacht
      }
      
      // Blofin Authentifikation  
      if (api.name === 'Blofin' && api.apiKey && api.apiSecret) {
        const timestamp = new Date().toISOString();
        headers['BF-ACCESS-TIMESTAMP'] = timestamp;
        // Signatur würde hier berechnet werden - für Demo vereinfacht
      }
      
      const requestOptions = {
        method: 'GET',
        headers: headers
      };
      
      const response = await fetch(api.url, requestOptions);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const rawData = await response.json();
      const processedData = this.processApiData(api.name, rawData);
      
      this.log('info', `✅ ${api.name}: Successfully processed ${processedData.length} records`);
      return processedData;
      
    } catch (error) {
      this.log('error', `❌ ${api.name}: Failed to fetch data`, { error: error.message });
      this.errors.push(`${api.name}: ${error.message}`);
      return [];
    }
  }

  processApiData(source, rawData) {
    const timestamp = new Date().toISOString();
    const syncId = `sync_${Date.now()}`;
    const processedData = [];
    
    try {
      switch (source) {
        case 'Bybit':
          if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
            rawData.result.list.forEach(item => {
              processedData.push({
                timestamp,
                source,
                symbol: item.symbol,
                price_usd: parseFloat(item.lastPrice || 0),
                change_24h_percent: parseFloat(item.price24hPcnt || 0) * 100,
                market_cap_usd: null,
                volume_24h: parseFloat(item.volume24h || 0),
                sync_id: syncId,
                raw_data: JSON.stringify(item)
              });
            });
          }
          break;
          
        case 'Blofin':
          if (rawData.data && Array.isArray(rawData.data)) {
            rawData.data.forEach(item => {
              processedData.push({
                timestamp,
                source,
                symbol: item.instId || item.symbol,
                price_usd: parseFloat(item.last || item.lastPrice || 0),
                change_24h_percent: parseFloat(item.sodUtc8 || item.change24h || 0),
                market_cap_usd: null,
                volume_24h: parseFloat(item.vol24h || item.volume24h || 0),
                sync_id: syncId,
                raw_data: JSON.stringify(item)
              });
            });
          }
          break;
          
        case 'CoinGecko':
          Object.entries(rawData).forEach(([coinId, data]) => {
            processedData.push({
              timestamp,
              source,
              symbol: coinId.toUpperCase(),
              price_usd: data.usd || 0,
              change_24h_percent: data.usd_24h_change || 0,
              market_cap_usd: data.usd_market_cap || 0,
              volume_24h: null,
              sync_id: syncId,
              raw_data: JSON.stringify(data)
            });
          });
          break;
          
        default:
          this.log('warn', `⚠️ No processor defined for ${source}`);
      }
      
    } catch (error) {
      this.log('error', `Error processing ${source} data`, { error: error.message });
    }
    
    return processedData;
  }

  async saveToGoogleSheets(allData) {
    if (allData.length === 0) {
      this.log('info', 'ℹ️ No new data to save to Google Sheets');
      return 0;
    }
    
    try {
      this.log('info', `💾 Saving ${allData.length} records to Google Sheets...`);
      
      // Daten in Batches aufteilen (Google Sheets Limit)
      const batchSize = 100;
      let totalSaved = 0;
      
      for (let i = 0; i < allData.length; i += batchSize) {
        const batch = allData.slice(i, i + batchSize);
        await this.sheet.addRows(batch);
        totalSaved += batch.length;
        
        this.log('info', `📝 Saved batch: ${totalSaved}/${allData.length} records`);
        
        // Kurze Pause zwischen Batches
        if (i + batchSize < allData.length) {
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }
      
      this.log('info', `✅ Successfully saved ${totalSaved} records to Google Sheets`);
      return totalSaved;
      
    } catch (error) {
      this.log('error', 'Failed to save data to Google Sheets', { error: error.message });
      throw error;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting Render Cron Trading Data Sync...');
    this.log('info', `📅 Start time: ${this.startTime.toISOString()}`);
    
    try {
      // 1. Google Sheets initialisieren
      await this.initializeGoogleSheets();
      
      // 2. Alle APIs nacheinander abfragen
      let allData = [];
      
      for (const api of this.apis) {
        const apiData = await this.fetchApiData(api);
        allData = allData.concat(apiData);
        
        // Rate Limiting zwischen API-Calls
        if (api.rateLimitMs) {
          this.log('info', `⏳ Rate limiting: waiting ${api.rateLimitMs}ms...`);
          await new Promise(resolve => setTimeout(resolve, api.rateLimitMs));
        }
      }
      
      // 3. Daten in Google Sheets speichern
      this.totalRecords = await this.saveToGoogleSheets(allData);
      
      // 4. Zusammenfassung und Erfolg
      const duration = (new Date() - this.startTime) / 1000;
      const summary = {
        duration: `${duration.toFixed(1)}s`,
        totalRecords: this.totalRecords,
        apisProcessed: this.apis.length,
        errors: this.errors.length,
        timestamp: new Date().toISOString()
      };
      
      this.log('info', '🎉 Sync completed successfully!', summary);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some APIs had errors:', { errors: this.errors });
      }
      
      // Erfolgreicher Exit für Render
      process.exit(0);
      
    } catch (error) {
      this.log('error', '💥 Critical sync failure', { 
        error: error.message,
        duration: `${(new Date() - this.startTime) / 1000}s`
      });
      
      // Fehler-Exit für Render
      process.exit(1);
    }
  }
}

// Hauptprogramm starten
const syncer = new TradingDataSync();
syncer.runSync().catch(error => {
  console.error('Unhandled error:', error);
  process.exit(1);
});
