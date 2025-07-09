const fs = require('fs').promises;

class ExistingCSVConverter {
  constructor() {
    this.inputFile = 'Claude.csv';
    this.outputFile = 'Claude_Executions_Import.csv';
  }

  log(level, message) {
    const timestamp = new Date().toISOString().substring(11, 19);
    const emoji = { 'info': 'ℹ️', 'success': '✅', 'warn': '⚠️', 'error': '❌' };
    console.log(`[${timestamp}] ${emoji[level]} ${message}`);
  }

  convertBybitDateTime(dateTimeStr) {
    try {
      const parts = dateTimeStr.trim().split(' ');
      if (parts.length !== 2) {
        throw new Error(`Invalid format: ${dateTimeStr}`);
      }
      
      const time = parts[0];
      const date = parts[1];
      
      if (!/^\d{2}:\d{2}$/.test(time) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        throw new Error(`Invalid time/date: ${dateTimeStr}`);
      }
      
      return `${date}T${time}:00.000Z`;
      
    } catch (error) {
      this.log('warn', `Date conversion failed: ${error.message}`);
      return new Date().toISOString();
    }
  }

  generateTradeId(index, symbol, side, qty, price) {
    const symbolShort = symbol.replace('USDT', '').toLowerCase();
    const qtyHash = Math.abs(parseFloat(qty) * 1000).toString(36);
    const priceHash = Math.abs(parseFloat(price)).toString(36);
    return `exec_${symbolShort}_${side.toLowerCase()}_${qtyHash}_${priceHash}_${index}`;
  }

  cleanNumericValue(value) {
    const num = parseFloat(value);
    return isNaN(num) ? 0 : Math.round(num * 100000000) / 100000000;
  }

  parseCSVLine(line) {
    const values = [];
    let current = '';
    let inQuotes = false;
    
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        values.push(current);
        current = '';
      } else {
        current += char;
      }
    }
    values.push(current);
    
    return values;
  }

  async processCSV() {
    try {
      this.log('info', `Reading ${this.inputFile}...`);
      
      const csvContent = await fs.readFile(this.inputFile, 'utf8');
      const lines = csvContent.split('\n').filter(line => line.trim() !== '');
      
      if (lines.length === 0) {
        throw new Error('CSV file is empty');
      }
      
      this.log('info', `Found ${lines.length} lines (including header)`);
      
      const executionHeaders = [
        'execution_time', 'account_name', 'symbol', 'side', 'executed_qty',
        'entry_price', 'exit_price', 'realized_pnl', 'execution_type', 'trade_id',
        'created_time', 'fee', 'fee_currency', 'data_source', 'import_timestamp', 'raw_data'
      ];
      
      const convertedRows = [executionHeaders];
      const currentTimestamp = new Date().toISOString();
      let successCount = 0;
      
      for (let i = 1; i < lines.length; i++) {
        try {
          const values = this.parseCSVLine(lines[i]);
          
          if (values.length < 9) {
            this.log('warn', `Row ${i}: Insufficient columns (${values.length}), skipping`);
            continue;
          }
          
          const contracts = values[0]?.trim() || '';
          const tradeType = values[1]?.trim() || '';
          const qty = values[2]?.trim() || '0';
          const entryPrice = values[3]?.trim() || '0';
          const realizedPnL = values[4]?.trim() || '0';
          const filledPrice = values[5]?.trim() || '0';
          const exitType = values[6]?.trim() || 'Trade';
          const filledTime = values[7]?.trim() || '';
          const createTime = values[8]?.trim() || '';
          
          if (!contracts || !tradeType || !filledTime) {
            this.log('warn', `Row ${i}: Missing critical data, skipping`);
            continue;
          }
          
          const executionTime = this.convertBybitDateTime(filledTime);
          const createdTime = this.convertBybitDateTime(createTime);
          
          const cleanQty = this.cleanNumericValue(qty);
          const cleanEntryPrice = this.cleanNumericValue(entryPrice);
          const cleanFilledPrice = this.cleanNumericValue(filledPrice);
          const cleanPnL = this.cleanNumericValue(realizedPnL);
          
          const tradeId = this.generateTradeId(i, contracts, tradeType, cleanQty, cleanEntryPrice);
          
          const originalData = {
            contracts, tradeType, qty: cleanQty, entryPrice: cleanEntryPrice,
            realizedPnL: cleanPnL, filledPrice: cleanFilledPrice, exitType, filledTime, createTime
          };
          
          const newRow = [
            executionTime, 'Claude Projekt', contracts, tradeType.toUpperCase(), cleanQty,
            cleanEntryPrice, cleanFilledPrice, cleanPnL, exitType, tradeId, createdTime,
            0, 'USDT', 'CSV_IMPORT', currentTimestamp, JSON.stringify(originalData).replace(/"/g, '""')
          ];
          
          convertedRows.push(newRow);
          successCount++;
          
        } catch (error) {
          this.log('error', `Row ${i} conversion failed: ${error.message}`);
        }
      }
      
      this.log('success', `Converted ${successCount} trades successfully`);
      
      const csvOutput = convertedRows.map(row => 
        row.map(cell => `"${cell}"`).join(',')
      ).join('\n');
      
      await fs.writeFile(this.outputFile, csvOutput, 'utf8');
      this.log('success', `Saved to: ${this.outputFile}`);
      
      return { originalRows: lines.length - 1, convertedRows: successCount };
      
    } catch (error) {
      this.log('error', `CSV processing failed: ${error.message}`);
      throw error;
    }
  }

  async runConversion() {
    try {
      this.log('info', '🚀 Converting Claude.csv for Google Sheets import...');
      
      const stats = await this.processCSV();
      
      console.log('\n🎉 CONVERSION COMPLETED!');
      console.log(`📊 Converted ${stats.convertedRows} trades`);
      console.log(`📁 Output file: ${this.outputFile}`);
      
      console.log('\n📋 NEXT STEPS:');
      console.log('1. Download Claude_Executions_Import.csv from Codespaces');
      console.log('2. Open Google Sheets → Claude_Projekt_Executions');
      console.log('3. Click cell A2, then File → Import → Upload CSV');
      
      return true;
      
    } catch (error) {
      this.log('error', `Conversion failed: ${error.message}`);
      return false;
    }
  }
}

const converter = new ExistingCSVConverter();
converter.runConversion();