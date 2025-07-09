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
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'Claude_Projekt_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET
        }
      },
      {
        name: 'Core Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_CoreStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'CoreStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'CoreStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_CORESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_CORESTRATEGIES_API_SECRET
        }
      },
      {
        name: 'BTC Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_BTCStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'BTCStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'BTCStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_BTCSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_BTCSTRATEGIES_API_SECRET
        }
      },
      {
        name: 'ETH Ape Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_ETHApeStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'ETHApeStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'ETHApeStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_ETHAPESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ETHAPESTRATEGIES_API_SECRET
        }
      },
      {
        name: 'Alt Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_AltStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'AltStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'AltStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_ALTSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_ALTSTRATEGIES_API_SECRET
        }
      },
      {
        name: 'Sol Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_SolStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'SolStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'SolStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_SOLSTRATEGIES_API_KEY,
          secret: process.env.BYBIT_SOLSTRATEGIES_API_SECRET
        }
      },
      {
        name: 'Meme Strategies',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_MemeStrategies_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'MemeStrategies_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'MemeStrategies_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_MEMESTRATEGIES_API_KEY,
          secret: process.env.BYBIT_MEMESTRATEGIES_API_SECRET
        }
      },
      {
        name: 'Incubator Zone',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_IncubatorZone_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: 'IncubatorZone_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: 'IncubatorZone_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_INCUBATORZONE_API_KEY,
          secret: process.env.BYBIT_INCUBATORZONE_API_SECRET
        }
      },
      {
        name: '1K',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_1K_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: '1K_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: '1K_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_1K_API_KEY,
          secret: process.env.BYBIT_1K_API_SECRET
        }
      },
      {
        name: '2K',
        endpoints: {
          orders: {
            url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
            sheetName: 'Bybit_2K_Orders',
            type: 'orders'
          },
          executions: {
            url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
            sheetName: '2K_Executions',
            type: 'executions'
          },
          positions: {
            url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
            sheetName: '2K_Positions',
            type: 'positions'
          }
        },
        api: {
          key: process.env.BYBIT_2K_API_KEY,
          secret: process.env.BYBIT_2K_API_SECRET
        }
      },
      // Blofin disabled - different API structure needed
      // {
      //   name: 'Blofin',
      //   endpoints: {
      //     orders: {
      //       url: 'https://api.bybit.com/v5/order/history?category=linear&limit=200',
      //       sheetName: 'Bybit_Blofin_Orders',
      //       type: 'orders'
      //     },
      //     executions: {
      //       url: 'https://api.bybit.com/v5/execution/list?category=linear&limit=200',
      //       sheetName: 'Blofin_Executions',
      //       type: 'executions'
      //     },
      //     positions: {
      //       url: 'https://api.bybit.com/v5/position/list?category=linear&settleCoin=USDT',
      //       sheetName: 'Blofin_Positions',
      //       type: 'positions'
      //     }
      //   },
      //   api: {
      //     key: process.env.BLOFIN_API_KEY,
      //     secret: process.env.BLOFIN_API_SECRET
      //   }
      // }
    ];
  }

  log(level, message, data) {
    const timestamp = new Date().toISOString().substring(11, 19);
    const emoji = { 
      info: '📊', 
      success: '✅', 
      warn: '⚠️', 
      error: '❌' 
    };
    console.log(`[${timestamp}] ${emoji[level] || '📊'} ${message}`);
    if (data) {
      console.log('Data:', JSON.stringify(data, null, 2));
    }
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
      
      this.log('success', '✅ Google Sheets connected');
      return true;
      
    } catch (error) {
      this.log('error', `Google Sheets connection failed: ${error.message}`);
      throw error;
    }
  }

  async createSheet(sheetName) {
    try {
      this.log('info', `Creating sheet: ${sheetName}`);
      
      // Check if sheet already exists to avoid duplicate errors
      const sheetMetadata = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      const sheetExists = sheetMetadata.data.sheets.some(sheet => 
        sheet.properties.title === sheetName
      );
      
      if (sheetExists) {
        this.log('info', `Sheet ${sheetName} already exists, skipping creation`);
        return;
      }
      
      let headers = [];
      if (sheetName.includes('Orders')) {
        headers = [
          'order_time', 'account_name', 'symbol', 'side', 'quantity', 'price', 'avg_price', 
          'cum_exec_qty', 'cum_exec_value', 'cum_exec_fee', 'order_status', 'order_type', 
          'time_in_force', 'order_id', 'order_link_id', 'created_time', 'updated_time', 
          'data_source', 'import_timestamp', 'raw_data'
        ];
      } else if (sheetName.includes('Executions')) {
        headers = [
          'execution_time', 'account_name', 'symbol', 'side', 'executed_qty', 'entry_price', 
          'exit_price', 'realized_pnl', 'execution_type', 'trade_id', 'created_time', 'fee', 
          'fee_currency', 'data_source', 'import_timestamp', 'raw_data'
        ];
      } else if (sheetName.includes('Positions')) {
        headers = [
          'position_time', 'account_name', 'category', 'symbol', 'side', 'size', 'position_value', 
          'avg_price', 'mark_price', 'liq_price', 'unrealised_pnl', 'cum_realised_pnl', 
          'realised_pnl', 'leverage', 'trade_mode', 'position_status', 'created_time', 
          'updated_time', 'data_source', 'import_timestamp', 'raw_data'
        ];
      }
      
      // Create the sheet
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
      
      // Add headers
      if (headers.length > 0) {
        await this.sheets.spreadsheets.values.update({
          spreadsheetId: this.spreadsheetId,
          range: `${sheetName}!A1:${String.fromCharCode(65 + headers.length - 1)}1`,
          valueInputOption: 'RAW',
          resource: { values: [headers] }
        });
      }
      
      this.log('success', `✅ Created sheet: ${sheetName}`);
      
    } catch (error) {
      this.log('error', `Failed to create sheet ${sheetName}: ${error.message}`);
    }
  }

  async getLastSyncTime(sheetName) {
    try {
      // Check if sheet exists first
      const sheetMetadata = await this.sheets.spreadsheets.get({
        spreadsheetId: this.spreadsheetId,
      });
      
      const sheetExists = sheetMetadata.data.sheets.some(sheet => 
        sheet.properties.title === sheetName
      );
      
      if (!sheetExists) {
        this.log('warn', `Sheet ${sheetName} does not exist - creating it`);
        await this.createSheet(sheetName);
        const oneDayAgo = new Date();
        oneDayAgo.setDate(oneDayAgo.getDate() - 1);
        return oneDayAgo.getTime();
      }
      
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
        const lastSync = timestamps[0] + (5 * 60 * 1000); // +5 min overlap
        this.log('info', `${sheetName}: Last sync + 5min buffer`);
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
    
    if (!account.api.key || !account.api.secret) {
      this.log('warn', `⚠️ ${account.name}: API credentials missing, skipping`);
      return;
    }
    
    let accountSuccessCount = 0;
    
    for (const [endpointType, endpoint] of Object.entries(account.endpoints)) {
      try {
        this.log('info', `📡 Fetching ${endpointType} for ${account.name}`);
        
        const startTime = await this.getLastSyncTime(endpoint.sheetName);
        const endTime = Date.now();
        
        let apiUrl = endpoint.url;
        
        // Add time parameters only for orders and executions, not positions
        if (endpointType !== 'positions') {
          const separator = apiUrl.includes('?') ? '&' : '?';
          apiUrl += `${separator}startTime=${startTime}&endTime=${endTime}`;
        }
        
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(apiUrl).search.substring(1);
        
        const headers = {
          'User-Agent': 'Extended-Trading-Dashboard-11Accounts/2.0',
          'Accept': 'application/json',
          'X-BAPI-API-KEY': account.api.key,
          'X-BAPI-TIMESTAMP': timestamp,
          'X-BAPI-RECV-WINDOW': recvWindow,
          'X-BAPI-SIGN': this.createBybitSignature(
            timestamp, account.api.key, recvWindow, queryString, account.api.secret
          )
        };
        
        const response = await fetch(apiUrl, { 
          method: 'GET', 
          headers,
          timeout: 30000
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        const data = await response.json();
        
        if (data.retCode !== 0) {
          throw new Error(`Bybit API Error ${data.retCode}: ${data.retMsg}`);
        }
        
        const itemCount = data.result?.list?.length || 0;
        this.log('success', `✅ ${account.name} ${endpointType}: ${itemCount} items`);
        
        if (itemCount > 0) {
          await this.saveData(endpoint.sheetName, data.result.list, endpointType, account.name);
          accountSuccessCount++;
        }
        
        // Rate limiting - 1 second between requests
        await new Promise(r => setTimeout(r, 1000));
        
      } catch (error) {
        this.log('error', `❌ ${account.name} ${endpointType}: ${error.message}`);
        this.errors.push(`${account.name} ${endpointType}: ${error.message}`);
      }
    }
    
    if (accountSuccessCount > 0) {
      this.successfulAccounts++;
    }
    
    // Longer pause between accounts to avoid rate limits
    await new Promise(r => setTimeout(r, 2000));
  }

  async saveData(sheetName, items, endpointType, accountName) {
    if (!items || items.length === 0) return;
    
    try {
      const currentTimestamp = new Date().toISOString();
      const rows = [];
      
      items.forEach(item => {
        if (endpointType === 'executions') {
          const execTime = new Date(parseInt(item.execTime || Date.now())).toISOString();
          rows.push([
            execTime,                                    // execution_time
            accountName,                                 // account_name
            item.symbol,                                 // symbol
            item.side,                                   // side
            parseFloat(item.execQty || 0),              // executed_qty
            parseFloat(item.orderPrice || 0),           // entry_price
            parseFloat(item.execPrice || 0),            // exit_price
            0,                                          // realized_pnl
            'Trade',                                    // execution_type
            item.execId,                                // trade_id
            execTime,                                   // created_time
            parseFloat(item.execFee || 0),              // fee
            item.feeCurrency || 'USDT',                 // fee_currency
            'API_SYNC',                                 // data_source
            currentTimestamp,                           // import_timestamp
            JSON.stringify(item)                        // raw_data
          ]);
        } else if (endpointType === 'positions') {
          const posTime = new Date(parseInt(item.updatedTime || Date.now())).toISOString();
          // Only save positions that have actual size
          if (parseFloat(item.size || 0) !== 0) {
            rows.push([
              posTime,                                  // position_time
              accountName,                              // account_name
              item.category || 'linear',                // category
              item.symbol,                              // symbol
              item.side || 'None',                      // side
              parseFloat(item.size || 0),               // size
              parseFloat(item.positionValue || 0),      // position_value
              parseFloat(item.avgPrice || 0),           // avg_price
              parseFloat(item.markPrice || 0),          // mark_price
              parseFloat(item.liqPrice || 0),           // liq_price
              parseFloat(item.unrealisedPnl || 0),      // unrealised_pnl
              parseFloat(item.cumRealisedPnl || 0),     // cum_realised_pnl
              parseFloat(item.cumRealisedPnl || 0),     // realised_pnl
              parseFloat(item.leverage || 0),           // leverage
              item.tradeMode || 'cross',                // trade_mode
              item.positionStatus || 'Normal',          // position_status
              item.createdTime || posTime,              // created_time
              item.updatedTime || posTime,              // updated_time
              'API_SYNC',                               // data_source
              currentTimestamp,                         // import_timestamp
              JSON.stringify(item)                      // raw_data
            ]);
          }
        } else if (endpointType === 'orders') {
          const orderTime = new Date(parseInt(item.createdTime || Date.now())).toISOString();
          rows.push([
            orderTime,                                  // order_time
            accountName,                                // account_name
            item.symbol,                                // symbol
            item.side,                                  // side
            parseFloat(item.qty || 0),                  // quantity
            parseFloat(item.price || 0),                // price
            parseFloat(item.avgPrice || 0),             // avg_price
            parseFloat(item.cumExecQty || 0),           // cum_exec_qty
            parseFloat(item.cumExecValue || 0),         // cum_exec_value
            parseFloat(item.cumExecFee || 0),           // cum_exec_fee
            item.orderStatus || 'Unknown',              // order_status
            item.orderType || 'Unknown',                // order_type
            item.timeInForce || 'GTC',                  // time_in_force
            item.orderId,                               // order_id
            item.orderLinkId || '',                     // order_link_id
            item.createdTime || orderTime,              // created_time
            item.updatedTime || orderTime,              // updated_time
            'API_SYNC',                                 // data_source
            currentTimestamp,                           // import_timestamp
            JSON.stringify(item)                        // raw_data
          ]);
        }
      });
      
      if (rows.length > 0) {
        // Check if sheet exists first
        const sheetMetadata = await this.sheets.spreadsheets.get({
          spreadsheetId: this.spreadsheetId,
        });
        
        const sheetExists = sheetMetadata.data.sheets.some(sheet => 
          sheet.properties.title === sheetName
        );
        
        if (!sheetExists) {
          this.log('warn', `Sheet ${sheetName} does not exist - creating it`);
          await this.createSheet(sheetName);
        }
        
        // Get existing data to determine next row
        const existingData = await this.sheets.spreadsheets.values.get({
          spreadsheetId: this.spreadsheetId,
          range: `${sheetName}!A:A`,
        });
        
        const nextRow = (existingData.data.values?.length || 1) + 1;
        
        // Determine column range based on endpoint type
        let endCol;
        if (endpointType === 'executions') endCol = 'P';
        else if (endpointType === 'positions') endCol = 'U';
        else if (endpointType === 'orders') endCol = 'T';
        else endCol = 'Z';
        
        const range = `${sheetName}!A${nextRow}:${endCol}${nextRow + rows.length - 1}`;
        
        await this.sheets.spreadsheets.values.update({
          spreadsheetId: this.spreadsheetId,
          range: range,
          valueInputOption: 'RAW',
          resource: { values: rows },
        });
        
        this.log('success', `💾 Saved ${rows.length} ${endpointType} to ${sheetName}`);
        this.totalRecords += rows.length;
      }
      
    } catch (error) {
      this.log('error', `Failed to save ${endpointType} data: ${error.message}`);
      this.errors.push(`Save ${endpointType}: ${error.message}`);
    }
  }

  async runExtendedSync() {
    this.log('info', '🚀 Starting Extended Trading Sync - 11 Accounts...');
    this.log('info', '📊 Syncing: Orders + Executions + Positions for all accounts');
    
    try {
      await this.initializeGoogleSheets();
      
      // Sync all accounts
      for (const account of this.accounts) {
        await this.syncAccount(account);
      }
      
      const duration = (new Date() - this.startTime) / 1000;
      
      // SUCCESS SUMMARY
      console.log('\n' + '='.repeat(60));
      console.log('🎉 EXTENDED SYNC COMPLETED - 11 ACCOUNTS!');
      console.log('='.repeat(60));
      console.log(`⏱️  Duration: ${duration.toFixed(1)}s`);
      console.log(`📊 Total records: ${this.totalRecords}`);
      console.log(`✅ Successful accounts: ${this.successfulAccounts}/${this.accounts.length}`);
      console.log(`📈 Active Accounts: Claude, Core, BTC, ETH, Sol, Meme, Incubator, 1K, 2K`);
      
      if (this.errors.length > 0) {
        console.log(`⚠️  Errors: ${this.errors.length}`);
        this.errors.forEach(error => console.log(`   - ${error}`));
      }
      
      console.log('='.repeat(60));
      
      // Exit with success if we have records or no errors
      const exitCode = (this.totalRecords > 0 || this.errors.length === 0) ? 0 : 1;
      process.exit(exitCode);
      
    } catch (error) {
      this.log('error', `💥 Extended sync failed: ${error.message}`);
      process.exit(1);
    }
  }
}

// Start the extended sync for all 11 accounts
const syncer = new ExtendedTradingSync();
syncer.runExtendedSync();
