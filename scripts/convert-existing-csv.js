const fs = require('fs').promises;
const path = require('path');

class MultiAccountCSVConverter {
  constructor() {
    this.startTime = new Date();
    this.totalConverted = 0;
    this.errors = [];
    
    // CSV-Dateien Mapping - passe die Dateinamen an deine Downloads an
    this.csvFiles = [
      {
        filename: 'Claude_Projekt.csv',
        accountName: 'Claude Projekt',
        sheetName: 'Claude_Projekt_Executions'
      },
      {
        filename: 'Core_Strategies.csv',
        accountName: 'Core Strategies',
        sheetName: 'CoreStrategies_Executions'
      },
      {
        filename: 'BTC_Strategies.csv',
        accountName: 'BTC Strategies',
        sheetName: 'BTCStrategies_Executions'
      },
      {
        filename: 'ETH_Ape_Strategies.csv',
        accountName: 'ETH Ape Strategies',
        sheetName: 'ETHApeStrategies_Executions'
      },
      {
        filename: 'Alt_Strategies.csv',
        accountName: 'Alt Strategies',
        sheetName: 'AltStrategies_Executions'
      },
      {
        filename: 'Sol_Strategies.csv',
        accountName: 'Sol Strategies',
        sheetName: 'SolStrategies_Executions'
      },
      {
        filename: 'Meme_Strategies.csv',
        accountName: 'Meme Strategies',
        sheetName: 'MemeStrategies_Executions'
      },
      {
        filename: 'Incubator_Zone.csv',
        accountName: 'Incubator Zone',
        sheetName: 'IncubatorZone_Executions'
      },
      {
        filename: '1K_Account.csv',
        accountName: '1K',
        sheetName: '1K_Executions'
      },
      {
        filename: '2K_Account.csv',
        accountName: '2K',
        sheetName: '2K_Executions'
      }
    ];
  }

  log(level, message) {
    const timestamp = new Date().toISOString().substring(11, 19);
    const emoji = { 'info': 'ℹ️', 'success': '✅', 'warn': '⚠️', 'error': '❌' };
    console.log(`[${timestamp}] ${emoji[level]} ${message}`);
  }

  async checkFileExists(filename) {
    try {
      await fs.access(filename);
      return true;
    } catch {
      return false;
    }
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

  generateTradeId(index, symbol, side, qty, price, accountName) {
    const symbolShort = symbol.replace('USDT', '').toLowerCase();
    const accountShort = accountName.replace(/\s+/g, '').toLowerCase();
    const qtyHash = Math.abs(parseFloat(qty) * 1000).toString(36);
    const priceHash = Math.abs(parseFloat(price)).toString(36);
    return `hist_${accountShort}_${symbolShort}_${side.toLowerCase()}_${qtyHash}_${priceHash}_${index}`;
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

  async processCSVFile(csvFile) {
    const { filename, accountName, sheetName } = csvFile;
    
    this.log('info', `Processing ${filename} for ${accountName}...`);
    
    const fileExists = await this.checkFileExists(filename);
    if (!fileExists) {
      this.log('warn', `File ${filename} not found, skipping`);
      return { filename, accountName, status: 'skipped', reason: 'file_not_found' };
    }
    
    try {
      const csvContent = await fs.readFile(filename, 'utf8');
      const lines = csvContent.split('\n').filter(line => line.trim() !== '');
      
      if (lines.length === 0) {
        this.log('warn', `${filename} is empty, skipping`);
        return { filename, accountName, status: 'skipped', reason: 'empty_file' };
      }
      
      this.log('info', `Found ${lines.length} lines in ${filename}`);
      
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
            this.log('warn', `${filename} Row ${i}: Insufficient columns (${values.length}), skipping`);
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
            this.log('warn', `${filename} Row ${i}: Missing critical data, skipping`);
            continue;
          }
          
          const executionTime = this.convertBybitDateTime(filledTime);
          const createdTime = this.convertBybitDateTime(createTime);
          
          const cleanQty = this.cleanNumericValue(qty);
          const cleanEntryPrice = this.cleanNumericValue(entryPrice);
          const cleanFilledPrice = this.cleanNumericValue(filledPrice);
          const cleanPnL = this.cleanNumericValue(realizedPnL);
          
          const tradeId = this.generateTradeId(i, contracts, tradeType, cleanQty, cleanEntryPrice, accountName);
          
          const originalData = {
            contracts, tradeType, qty: cleanQty, entryPrice: cleanEntryPrice,
            realizedPnL: cleanPnL, filledPrice: cleanFilledPrice, exitType, filledTime, createTime
          };
          
          const newRow = [
            executionTime, accountName, contracts, tradeType.toUpperCase(), cleanQty,
            cleanEntryPrice, cleanFilledPrice, cleanPnL, exitType, tradeId, createdTime,
            0, 'USDT', 'CSV_IMPORT_HISTORICAL', currentTimestamp, JSON.stringify(originalData).replace(/"/g, '""')
          ];
          
          convertedRows.push(newRow);
          successCount++;
          
        } catch (error) {
          this.log('error', `${filename} Row ${i} conversion failed: ${error.message}`);
          this.errors.push(`${filename} Row ${i}: ${error.message}`);
        }
      }
      
      if (successCount > 0) {
        const outputFile = `${accountName.replace(/\s+/g, '_')}_Historical_Import.csv`;
        const csvOutput = convertedRows.map(row => 
          row.map(cell => `"${cell}"`).join(',')
        ).join('\n');
        
        await fs.writeFile(outputFile, csvOutput, 'utf8');
        this.log('success', `${filename}: Converted ${successCount} trades → ${outputFile}`);
        this.totalConverted += successCount;
        
        return { 
          filename, accountName, status: 'success', 
          converted: successCount, outputFile 
        };
      } else {
        this.log('warn', `${filename}: No valid trades found`);
        return { filename, accountName, status: 'no_data', converted: 0 };
      }
      
    } catch (error) {
      this.log('error', `Failed to process ${filename}: ${error.message}`);
      this.errors.push(`${filename}: ${error.message}`);
      return { filename, accountName, status: 'error', error: error.message };
    }
  }

  async runMultiAccountConversion() {
    this.log('info', '🚀 Starting Multi-Account CSV Conversion...');
    this.log('info', `📁 Processing ${this.csvFiles.length} potential CSV files...`);
    
    const results = [];
    
    for (const csvFile of this.csvFiles) {
      const result = await this.processCSVFile(csvFile);
      results.push(result);
      
      // Small delay between files
      await new Promise(r => setTimeout(r, 100));
    }
    
    const duration = (new Date() - this.startTime) / 1000;
    
    console.log('\n' + '='.repeat(60));
    console.log('🎉 MULTI-ACCOUNT CSV CONVERSION COMPLETED!');
    console.log('='.repeat(60));
    console.log(`⏱️  Duration: ${duration.toFixed(1)}s`);
    console.log(`📊 Total trades converted: ${this.totalConverted}`);
    
    // Summary by status
    const successful = results.filter(r => r.status === 'success');
    const skipped = results.filter(r => r.status === 'skipped');
    const failed = results.filter(r => r.status === 'error');
    const noData = results.filter(r => r.status === 'no_data');
    
    console.log(`✅ Successful: ${successful.length} files`);
    console.log(`⚠️  Skipped: ${skipped.length} files`);
    console.log(`❌ Failed: ${failed.length} files`);
    console.log(`📝 No data: ${noData.length} files`);
    
    if (successful.length > 0) {
      console.log('\n📄 Generated Files:');
      successful.forEach(result => {
        console.log(`   - ${result.outputFile} (${result.converted} trades)`);
      });
    }
    
    if (skipped.length > 0) {
      console.log('\n⚠️  Skipped Files:');
      skipped.forEach(result => {
        console.log(`   - ${result.filename} (${result.reason})`);
      });
    }
    
    if (this.errors.length > 0) {
      console.log('\n❌ Errors:');
      this.errors.forEach(error => console.log(`   - ${error}`));
    }
    
    console.log('\n📋 NEXT STEPS:');
    console.log('1. Check the generated *_Historical_Import.csv files');
    console.log('2. Upload each file to the corresponding Google Sheet');
    console.log('3. Import via: File → Import → Upload → Append to current sheet');
    console.log('='.repeat(60));
    
    return results;
  }
}

// Run the conversion
const converter = new MultiAccountCSVConverter();
converter.runMultiAccountConversion().then(results => {
  const totalSuccessful = results.filter(r => r.status === 'success').length;
  process.exit(totalSuccessful > 0 ? 0 : 1);
}).catch(error => {
  console.error('❌ Conversion failed:', error.message);
  process.exit(1);
});
