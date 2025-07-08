// scripts/trading-data-sync.js - API DEBUG VERSION
const { google } = require('googleapis');
const fetch = require('node-fetch');
const crypto = require('crypto');

class APIDebugSync {
  constructor() {
    this.startTime = new Date();
    
    // Test nur 2 Accounts für detaillierte Diagnose
    this.accounts = [
      {
        name: 'Bybit Claude Projekt',
        api: {
          // Teste verschiedene Endpoints
          endpoints: [
            'https://api.bybit.com/v5/execution/list?category=linear&limit=10',
            'https://api.bybit.com/v5/order/history?category=linear&limit=10',
            'https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED',
            'https://api.bybit.com/v5/position/list?category=linear'
          ],
          key: process.env.BYBIT_CLAUDE_PROJEKT_API_KEY,
          secret: process.env.BYBIT_CLAUDE_PROJEKT_API_SECRET,
          type: 'bybit'
        }
      },
      {
        name: 'Blofin',
        api: {
          endpoints: [
            'https://openapi.blofin.com/api/v1/trade/fills?limit=10',
            'https://openapi.blofin.com/api/v1/trade/orders-history?limit=10',
            'https://openapi.blofin.com/api/v1/account/balance'
          ],
          key: process.env.BLOFIN_API_KEY,
          secret: process.env.BLOFIN_API_SECRET,
          passphrase: process.env.BLOFIN_API_PASSPHRASE,
          type: 'blofin'
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

  async testEndpoint(account, endpoint) {
    try {
      this.log('info', `🔍 TESTING ${account.name} - ${endpoint}`);
      
      if (!account.api.key) {
        this.log('error', `❌ No API key for ${account.name}`);
        return;
      }
      
      const headers = {
        'User-Agent': 'Trading-Debug/1.0',
        'Accept': 'application/json'
      };
      
      if (account.api.type === 'bybit') {
        const timestamp = Date.now().toString();
        const recvWindow = '5000';
        const queryString = new URL(endpoint).search.substring(1);
        
        headers['X-BAPI-API-KEY'] = account.api.key;
        headers['X-BAPI-TIMESTAMP'] = timestamp;
        headers['X-BAPI-RECV-WINDOW'] = recvWindow;
        headers['X-BAPI-SIGN'] = this.createBybitSignature(
          timestamp, account.api.key, recvWindow, queryString, account.api.secret
        );
        
        this.log('info', `🔐 Bybit Auth: Key=${account.api.key.substring(0,10)}..., Timestamp=${timestamp}`);
        
      } else if (account.api.type === 'blofin') {
        const timestamp = new Date().toISOString();
        const method = 'GET';
        const requestPath = new URL(endpoint).pathname + new URL(endpoint).search;
        
        headers['BF-ACCESS-KEY'] = account.api.key;
        headers['BF-ACCESS-TIMESTAMP'] = timestamp;
        headers['BF-ACCESS-PASSPHRASE'] = account.api.passphrase;
        headers['BF-ACCESS-SIGN'] = this.createBlofinSignature(
          timestamp, method, requestPath, '', account.api.secret
        );
        
        this.log('info', `🔐 Blofin Auth: Key=${account.api.key.substring(0,10)}..., Timestamp=${timestamp}`);
      }
      
      this.log('info', `📡 Making request...`);
      
      const response = await fetch(endpoint, {
        method: 'GET',
        headers: headers
      });
      
      this.log('info', `📊 Response Status: ${response.status} ${response.statusText}`);
      this.log('info', `📋 Response Headers:`, Object.fromEntries(response.headers.entries()));
      
      if (!response.ok) {
        const errorText = await response.text();
        this.log('error', `❌ HTTP Error Response:`, {
          status: response.status,
          statusText: response.statusText,
          body: errorText
        });
        return;
      }
      
      const data = await response.json();
      
      this.log('info', `📦 SUCCESS! Response Structure:`, {
        topLevelKeys: Object.keys(data),
        hasResult: !!data.result,
        hasData: !!data.data,
        hasCode: !!data.code,
        hasMessage: !!data.message,
        retCode: data.retCode,
        retMsg: data.retMsg
      });
      
      // Zeige ersten Teil der Daten
      if (data.result) {
        this.log('info', `📊 Result Structure:`, Object.keys(data.result));
        if (data.result.list) {
          this.log('info', `📈 Found ${data.result.list.length} items in result.list`);
          if (data.result.list.length > 0) {
            this.log('info', `📝 First item sample:`, data.result.list[0]);
          }
        }
      }
      
      if (data.data && Array.isArray(data.data)) {
        this.log('info', `📈 Found ${data.data.length} items in data array`);
        if (data.data.length > 0) {
          this.log('info', `📝 First item sample:`, data.data[0]);
        }
      }
      
      // Zeige komplette Antwort (begrenzt)
      const responseString = JSON.stringify(data, null, 2);
      if (responseString.length > 3000) {
        this.log('info', `📋 Complete Response (truncated):`, responseString.substring(0, 3000) + '...[TRUNCATED]');
      } else {
        this.log('info', `📋 Complete Response:`, data);
      }
      
    } catch (error) {
      this.log('error', `💥 Request failed:`, {
        error: error.message,
        stack: error.stack
      });
    }
  }

  async runDebug() {
    this.log('info', '🔍 Starting DETAILED API Debug...');
    this.log('info', '🎯 Testing multiple endpoints per account...');
    
    for (const account of this.accounts) {
      this.log('info', `\n${'='.repeat(60)}`);
      this.log('info', `🏦 TESTING ACCOUNT: ${account.name}`);
      this.log('info', `${'='.repeat(60)}`);
      
      for (let i = 0; i < account.api.endpoints.length; i++) {
        const endpoint = account.api.endpoints[i];
        
        this.log('info', `\n📍 ENDPOINT ${i + 1}/${account.api.endpoints.length}:`);
        await this.testEndpoint(account, endpoint);
        
        // Rate limiting zwischen Endpoints
        if (i < account.api.endpoints.length - 1) {
          this.log('info', '⏳ Waiting 2 seconds before next endpoint...');
          await new Promise(r => setTimeout(r, 2000));
        }
      }
      
      this.log('info', '⏳ Waiting 5 seconds before next account...');
      await new Promise(r => setTimeout(r, 5000));
    }
    
    this.log('info', '✅ API Debug completed!');
    this.log('info', '📝 Check the logs above to see which endpoints work and what data they return.');
    
    // Erfolgreicher Exit
    process.exit(0);
  }
}

const debugger = new APIDebugSync();
debugger.runDebug();
