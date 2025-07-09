// scripts/trading-data-sync-fixed.js - Order History & Trade Activity (KORRIGIERT)
const { google } = require('googleapis');
const fetch = require('node-fetch');
const crypto = require('crypto');

class OrderHistorySync {
  constructor() {
    this.startTime = new Date();
    this.totalRecords = 0;
    this.errors = [];
    this.successfulAccounts = 0;
    
    // Alle Accounts für Order History (alle Status: filled, cancelled, rejected)
    this.accounts = [
      // Blofin Order History
      {
        name: 'Blofin',
        sheetName: 'Blofin_Orders',
        api: {
          url: 'https://openapi.blofin.com/api/v1/trade/orders-history?limit=100',
          key: process.env.BLOFIN_API_KEY,
          secret: process.env.BLOFIN_API_SECRET,
          passphrase: process.env.BLOFIN_API_PASSPHRASE,
          type: 'blofin_orders'
        }
      },
      // Bybit Order History für alle Accounts
      {
        name: 'Bybit 1K',
        sheetName: 'Bybit_1K_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_1K_API_KEY,
          secret: process.env.BYBIT_1K_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit 2K',
        sheetName: 'Bybit_2K_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_2K_API_KEY,
          secret: process.env.BYBIT_2K_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit AltStrategies',
        sheetName: 'Bybit_AltStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_ALTSSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ALTSSTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit BTC Strategies',
        sheetName: 'Bybit_BTCStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_BTCSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_BTCSTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit Claude Projekt',
        sheetName: 'Bybit_Claude_Projekt_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit Core Strategies',
        sheetName: 'Bybit_CoreStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit ETH Ape Strategies',
        sheetName: 'Bybit_ETHApeStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_ETHAPESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ETHAPESTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit Incubator Zone',
        sheetName: 'Bybit_IncubatorZone_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_INCUBATORZONE_API_KEY,
          secret: process.env.BYBIT_INCUBATORZONE_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit Meme Strategies',
        sheetName: 'Bybit_MemeStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_MEMESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_MEMESTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      {
        name: 'Bybit SOL Strategies',
        sheetName: 'Bybit_SOLStrategies_Orders',
        api: {
          url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
          key: process.env.BYBIT_SOLSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_SOLSTRATEGIES_API_SECRET,
          type: 'bybit_orders'
        }
      },
      // Zusätzlich: Aktive Orders
      {
        name: 'Bybit Claude Projekt Active',
        sheetName: 'Bybit_Claude_Projekt_ActiveOrders',
        api: {
          url: 'https://api.bybit.com/v5/order/realtime?category=linear&limit=200',
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit_active_orders'
        }
      },
      {
        name: 'Bybit Core Strategies Active',
        sheetName: 'Bybit_CoreStrategies_ActiveOrders',
        api: {
          url: 'https://api.bybit.com/v5/order/realtime?category=linear&limit=200',
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET,
          type: 'bybit_active_orders'
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
      
      if (type === 'bybit_orders' || type === 'bybit_active_orders') {
        headers = [
          'timestamp', 'account_name', 'category', 'symbol', 'order_id', 'order_link_id',
          'side', 'order_type', 'qty', 'price', 'time_in_force', 'order_status',
          'avg_price', 'cum_exec_qty', 'cum_exec_value', 'cum_exec_fee', 'reduce_only',
          'close_on_trigger', 'created_time', 'updated_time', 'reject_reason',
          'stop_order_type', 'trigger_price', 'take_profit', 'stop_loss', 'tp_trigger_by',
          'sl_trigger_by', 'trigger_direction', 'position_idx', 'sync_id', 'raw_data'
        ];
      } else if (type === 'blofin_orders') {
        headers = [
          'timestamp', 'account_name', 'inst_type', 'inst_id', 'order_id', 'cl_ord_id',
          'tag', 'px', 'sz', 'ord_type', 'side', 'pos_side', 'td_mode', 'state',
          'acc_fill_sz', 'fill_px', 'trade_id', 'fill_sz', 'fill_time', 'source',
          'fee', 'fee_ccy', 'rebate', 'rebate_ccy', 'pnl', 'c_time', 'u_time',
          'sync_id', 'raw_data'
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

  async getLastSyncTime(account) {
    try {
      const response = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${account.sheetName}!A:A`,
      });
      
      if (!response.data.values || response.data.values.length <= 1) {
        // KORRIGIERT: Reduzierter Zeitbereich je nach API Type
        let daysBack;
        if (account.api.type === 'bybit_active_orders') {
          daysBack = 1; // Aktive Orders: nur 1 Tag
        } else if (account.api.type.startsWith('bybit')) {
          daysBack = 7; // Bybit Order History: max 7 Tage (wegen cancelled/rejected orders)
        } else {
          daysBack = 7; // Blofin: auch 7 Tage zur Sicherheit
        }
        
        const startDate = new Date();
        startDate.setDate(startDate.getDate() - daysBack);
        this.log('info', `📅 ${account.name}: First import - getting orders since ${startDate.toISOString()} (${daysBack} days)`);
        return startDate.getTime();
      }
      
      // Inkrementeller Sync
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
      
      // Fallback: 1 Tag zurück
      const oneDayAgo = new Date();
      oneDayAgo.setDate(oneDayAgo.getDate() - 1);
      return oneDayAgo.getTime();
      
    } catch (error) {
      this.log('error', `Failed to get last sync time for ${account.name}`, { error: error.message });
      // KORRIGIERT: Bei Fehlern nur 1 Tag zurück statt 3 Tage
      const oneDayAgo = new Date();
      oneDayAgo.setDate(oneDayAgo.getDate() - 1);
      return oneDayAgo.getTime();
    }
  }

  async fetchAccountData(account) {
    try {
      this.log('info', `📡 Fetching ${account.api.type} from ${account.name}...`);
      
      if (!account.api.key) {
        this.log('warn', `⚠️ ${account.name}: API key missing, skipping`);
        return [];
      }
      
      const startTime = await this.getLastSyncTime(account);
      const endTime = Date.now();
      
      // KORRIGIERT: Zeitbereich-Validierung
      const maxDaysForType = {
        'bybit_orders': 7,          // Order History: max 7 Tage
        'bybit_active_orders': 365, // Aktive Orders: längerer Zeitbereich OK
        'blofin_orders': 7          // Blofin: auch 7 Tage
      };
      
      const maxDays = maxDaysForType[account.api.type] || 7;
      const maxTime = maxDays * 24 * 60 * 60 * 1000;
      const actualStartTime = Math.max(startTime, endTime - maxTime);
      
      if (actualStartTime !== startTime) {
        this.log('warn', `⚠️ ${account.name}: Zeitbereich reduziert auf ${maxDays} Tage (API Limit)`);
      }
      
      const startDate = new Date(actualStartTime);
      this.log('info', `📅 ${account.name}: Getting orders from ${startDate.toISOString()} to ${new Date(endTime).toISOString()}`);
      
      // URL mit Zeitfilter erweitern
      let apiUrl = account.api.url;
      if (account.api.type.startsWith('bybit')) {
        const separator = apiUrl.includes('?') ? '&' : '?';
        apiUrl += `${separator}startTime=${actualStartTime}&endTime=${endTime}`;
      } else if (account.api.type === 'blofin_orders') {
        const separator = apiUrl.includes('?') ? '&' : '?';
        apiUrl += `${separator}after=${Math.floor(actualStartTime / 1000)}`;
      }
      
      const headers = {
        'User-Agent': 'Trading-Dashboard/1.0',
        'Accept': 'application/json'
      };
      
      if (account.api.type.startsWith('bybit')) {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(apiUrl).search.substring(1);
        
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = recvWindow;
        headers['X-BAPI-SIGN'] = this.createBybitSignature(
          timestamp, account.api.key, recvWindow, queryString, account.api.secret
        );
        
      } else if (account.api.type === 'blofin_orders') {
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
      
      this.log('info', `🔗 ${account.name}: Making API request to ${apiUrl}`);
      
      const response = await fetch(apiUrl, {
        method: 'GET',
        headers: headers
      });
      
      // VERBESSERT: Detailliertes Error Logging
      if (!response.ok) {
        const errorText = await response.text();
        this.log('error', `❌ ${account.name}: HTTP ${response.status} ${response.statusText}`, {
          url: apiUrl,
          headers: Object.keys(headers),
          responseText: errorText.substring(0, 500)
        });
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }
      
      const data = await response.json();
      
      // VERBESSERT: Zeige Bybit API Response Code
      if (account.api.type.startsWith('bybit')) {
        this.log('info', `📊 ${account.name}: Bybit API Response`, {
          retCode: data.retCode,
          retMsg: data.retMsg,
          hasResult: !!data.result,
          hasData: !!data.data
        });
        
        if (data.retCode !== 0) {
          throw new Error(`Bybit API Error ${data.retCode}: ${data.retMsg}`);
        }
      }
      
      this.log('info', `✅ ${account.name}: Retrieved ${account.api.type} data successfully`);
      
      // VERBESSERT: Debug-Info über Datenstruktur
      this.log('info', `🔍 ${account.name}: Data structure:`, {
        hasResult: !!data.result,
        hasData: !!data.data,
        resultKeys: data.result ? Object.keys(data.result) : null,
        dataKeys: data.data ? Object.keys(data.data) : null,
        topLevelKeys: Object.keys(data),
        resultListLength: data.result?.list?.length || 0,
        dataLength: Array.isArray(data.data) ? data.data.length : 0
      });
      
      return this.processAccountData(account, data);
      
    } catch (error) {
      this.log('error', `❌ ${account.name} failed: ${error.message}`, {
        errorStack: error.stack?.split('\n')[0]
      });
      this.errors.push(`${account.name}: ${error.message}`);
      return [];
    }
  }

  processAccountData(account, rawData) {
    const syncId = `sync_${Date.now()}`;
    const rows = [];
    
    try {
      if (account.api.type.startsWith('bybit')) {
        if (rawData.result && rawData.result.list && Array.isArray(rawData.result.list)) {
          this.log('info', `📊 ${account.name}: Found ${rawData.result.list.length} orders in API response`);
          
          rawData.result.list.forEach(order => {
            const orderTime = new Date(parseInt(order.createdTime || Date.now())).toISOString();
            
            rows.push([
              orderTime,
              account.name,
              order.category || 'linear',
              order.symbol,
              order.orderId,
              order.orderLinkId || '',
              order.side,
              order.orderType,
              parseFloat(order.qty || 0),
              parseFloat(order.price || 0),
              order.timeInForce,
              order.orderStatus,
              parseFloat(order.avgPrice || 0),
              parseFloat(order.cumExecQty || 0),
              parseFloat(order.cumExecValue || 0),
              parseFloat(order.cumExecFee || 0),
              order.reduceOnly || false,
              order.closeOnTrigger || false,
              order.createdTime,
              order.updatedTime,
              order.rejectReason || '',
              order.stopOrderType || '',
              parseFloat(order.triggerPrice || 0),
              parseFloat(order.takeProfit || 0),
              parseFloat(order.stopLoss || 0),
              order.tpTriggerBy || '',
              order.slTriggerBy || '',
              order.triggerDirection || '',
              order.positionIdx || 0,
              syncId,
              JSON.stringify(order)
            ]);
          });
        } else {
          this.log('warn', `⚠️ ${account.name}: No result.list found in API response - möglicherweise keine Orders im Zeitraum`);
        }
      } else if (account.api.type === 'blofin_orders') {
        if (rawData.data && Array.isArray(rawData.data)) {
          this.log('info', `📊 ${account.name}: Found ${rawData.data.length} orders in API response`);
          
          rawData.data.forEach(order => {
            const orderTime = new Date(parseInt(order.cTime || Date.now())).toISOString();
            
            rows.push([
              orderTime,
              account.name,
              order.instType,
              order.instId,
              order.ordId,
              order.clOrdId || '',
              order.tag || '',
              parseFloat(order.px || 0),
              parseFloat(order.sz || 0),
              order.ordType,
              order.side,
              order.posSide || '',
              order.tdMode || '',
              order.state,
              parseFloat(order.accFillSz || 0),
              parseFloat(order.fillPx || 0),
              order.tradeId || '',
              parseFloat(order.fillSz || 0),
              order.fillTime || '',
              order.source || '',
              parseFloat(order.fee || 0),
              order.feeCcy || '',
              parseFloat(order.rebate || 0),
              order.rebateCcy || '',
              parseFloat(order.pnl || 0),
              order.cTime,
              order.uTime,
              syncId,
              JSON.stringify(order)
            ]);
          });
        } else {
          this.log('warn', `⚠️ ${account.name}: No data array found in API response - möglicherweise keine Orders im Zeitraum`);
        }
      }
      
      this.log('info', `📊 ${account.name}: Processed ${rows.length} order records`);
      
    } catch (error) {
      this.log('error', `Error processing ${account.name} order data: ${error.message}`);
    }
    
    return rows;
  }

  async saveToGoogleSheet(account, data) {
    if (data.length === 0) {
      this.log('info', `ℹ️ ${account.name}: No new orders to save`);
      return 0;
    }
    
    try {
      this.log('info', `💾 ${account.name}: Saving ${data.length} orders...`);
      
      const existingData = await this.sheets.spreadsheets.values.get({
        spreadsheetId: this.spreadsheetId,
        range: `${account.sheetName}!A:A`,
      });
      
      const nextRow = (existingData.data.values?.length || 1) + 1;
      
      let endCol = 'AD'; // Bybit orders
      if (account.api.type === 'blofin_orders') endCol = 'AB';
      
      const range = `${account.sheetName}!A${nextRow}:${endCol}${nextRow + data.length - 1}`;
      
      await this.sheets.spreadsheets.values.update({
        spreadsheetId: this.spreadsheetId,
        range: range,
        valueInputOption: 'RAW',
        resource: { values: data },
      });
      
      this.log('info', `✅ ${account.name}: Saved ${data.length} orders!`);
      return data.length;
      
    } catch (error) {
      this.log('error', `${account.name}: Save failed - ${error.message}`);
      return 0;
    }
  }

  async runSync() {
    this.log('info', '🚀 Starting Order History & Trade Activity Sync (FIXED VERSION)...');
    this.log('info', '📋 Fetching order history with corrected time ranges...');
    this.log('info', `📊 Processing ${this.accounts.length} accounts...`);
    
    try {
      await this.initializeGoogleSheets();
      
      for (const account of this.accounts) {
        this.log('info', `\n🔄 Processing ${account.name} (${account.api.type})...`);
        
        const orders = await this.fetchAccountData(account);
        const savedCount = await this.saveToGoogleSheet(account, orders);
        
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
        totalOrders: this.totalRecords,
        successfulAccounts: this.successfulAccounts,
        totalAccounts: this.accounts.length,
        errors: this.errors.length
      };
      
      this.log('info', '\n🎉 Order History & Trade Activity Sync completed!', summary);
      this.log('info', `📋 Total orders imported: ${this.totalRecords}`);
      
      if (this.errors.length > 0) {
        this.log('warn', '⚠️ Some accounts had errors:', { errors: this.errors });
      }
      
      const exitCode = this.successfulAccounts > 0 ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 Order History Sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

const syncer = new OrderHistorySync();
syncer.runSync();
