# Erstelle das Script
cat > scripts/convert-existing-csv.js << 'EOF'
// scripts/convert-existing-csv.js - Konvertiert bestehende Claude.csv für Executions Sheet
const fs = require('fs').promises;
const path = require('path');

class ExistingCSVConverter {
  constructor() {
    this.inputFile = 'Claude.csv';
    this.outputFile = 'Claude_Executions_Import.csv';
  }

  log(level, message, data) {
    const timestamp = new Date().toISOString().substring(11, 19);
    const emoji = { 'info': 'ℹ️', 'success': '✅', 'warn': '⚠️', 'error': '❌' };
    console.log(`[${timestamp}] ${emoji[level]} ${message}`);
    if (data) console.log('Data:', JSON.stringify(data, null, 2));
  }

  convertBybitDateTime(dateTimeStr) {
    try {
      const parts = dateTimeStr.trim().split(' ');
      if (parts.length !== 2) {
        throw new Error(`Invalid format: ${dateTimeStr}`);
      }
      
      const time = parts[0]; // "14:04"
      const date = parts[1]; // "2025-07-06"
      
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

  async processCSV() {
    try {
      this.log('info', `Reading ${this.inputFile}...`);
      
      const csvContent = await fs.readFile(this.inputFile, 'utf8');
      const lines = csvContent.split('\n').filter(line => line.trim() !== '');
      
      if (lines.length === 0) {
        throw new Error('CSV file is empty');
      }
      
      this.log('info', `Found ${lines.length} lines (including header)`);
      
      const originalHeaders = lines[0].split(',').map(h => h.trim());
      this.log('info', 'Original CSV headers:', originalHeaders);
      
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
          const csvLine = lines[i];
          const values = this.parseCSVLine(csvLine);
          
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
            row: i,
            contracts,
            tradeType,
            qty: cleanQty,
            entryPrice: cleanEntryPrice,
            realizedPnL: cleanPnL,
            filledPrice: cleanFilledPrice,
            exitType,
            filledTime,
            createTime
          };
          
          const newRow = [
            executionTime,
            'Claude Projekt',
            contracts,
            tradeType.toUpperCase(),
            cleanQty,
            cleanEntryPrice,
            cleanFilledPrice,
            cleanPnL,
            exitType,
            tradeId,
            createdTime,
            0,
            'USDT',
            'CSV_IMPORT',
            currentTimestamp,
            JSON.stringify(originalData).replace(/"/g, '""')
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
      
      return {
        inputFile: this.inputFile,
        outputFile: this.outputFile,
        originalRows: lines.length - 1,
        convertedRows: successCount,
        headers: executionHeaders.length
      };
      
    } catch (error) {
      this.log('error', `CSV processing failed: ${error.message}`);
      throw error;
    }
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

  async runConversion() {
    try {
      this.log('info', '🚀 Converting existing Claude.csv for Executions import...');
      
      const stats = await this.processCSV();
      
      console.log('\n🎉 CONVERSION COMPLETED!');
      console.log('========================');
      console.log(`📁 Input: ${stats.inputFile}`);
      console.log(`📁 Output: ${stats.outputFile}`);
      console.log(`📊 Original trades: ${stats.originalRows}`);
      console.log(`📊 Converted trades: ${stats.convertedRows}`);
      console.log(`📊 Columns: ${stats.headers}`);
      
      console.log('\n📋 IMPORT STEPS:');
      console.log('1. 🔗 Öffne dein Google Sheets Trading Dashboard');
      console.log('2. 📊 Gehe zum "Claude_Projekt_Executions" Sheet');
      console.log('3. 📍 Klicke auf Zelle A2 (erste Datenzeile unter Headers)');
      console.log('4. 📤 File → Import → Upload');
      console.log(`5. 📁 Wähle die Datei: ${stats.outputFile}`);
      console.log('6. ⚙️ Settings: Insert new rows, Comma separator, Convert text to numbers ✓');
      console.log('7. ✅ Klicke "Import data"');
      
      return true;
      
    } catch (error) {
      this.log('error', `Conversion failed: ${error.message}`);
      return false;
    }
  }
}

const converter = new ExistingCSVConverter();
converter.runConversion()
  .then(success => {
    if (success) {
      console.log('\n✅ CSV conversion completed successfully!');
      process.exit(0);
    } else {
      console.log('\n❌ Conversion failed');
      process.exit(1);
    }
  })
  .catch(error => {
    console.error('\n💥 Unexpected error:', error.message);
    process.exit(1);
  });
EOF
