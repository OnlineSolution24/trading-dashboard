// scripts/convert-existing-csv.js - Konvertiert bestehende Claude.csv für Executions Sheet
const fs = require('fs').promises;
const path = require('path');

class ExistingCSVConverter {
  constructor() {
    this.inputFile = 'Claude.csv'; // Ihre bestehende CSV
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
      // Von: "14:04 2025-07-06" zu ISO: "2025-07-06T14:04:00.000Z"
      const parts = dateTimeStr.trim().split(' ');
      if (parts.length !== 2) {
        throw new Error(`Invalid format: ${dateTimeStr}`);
      }
      
      const time = parts[0]; // "14:04"
      const date = parts[1]; // "2025-07-06"
      
      // Validiere Format
      if (!/^\d{2}:\d{2}$/.test(time) || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        throw new Error(`Invalid time/date: ${dateTimeStr}`);
      }
      
      return `${date}T${time}:00.000Z`;
      
    } catch (error) {
      this.log('warn', `Date conversion failed: ${error.message}`);
      return new Date().toISOString(); // Fallback
    }
  }

  generateTradeId(index, symbol, side, qty, price) {
    // Eindeutige Trade ID generieren
    const symbolShort = symbol.replace('USDT', '').toLowerCase();
    const qtyHash = Math.abs(parseFloat(qty) * 1000).toString(36);
    const priceHash = Math.abs(parseFloat(price)).toString(36);
    return `exec_${symbolShort}_${side.toLowerCase()}_${qtyHash}_${priceHash}_${index}`;
  }

  cleanNumericValue(value) {
    // Entferne übermäßige Dezimalstellen und konvertiere zu Number
    const num = parseFloat(value);
    return isNaN(num) ? 0 : Math.round(num * 100000000) / 100000000; // 8 Dezimalstellen max
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
      
      // Parse Header der originalen CSV
      const originalHeaders = lines[0].split(',').map(h => h.trim());
      this.log('info', 'Original CSV headers:', originalHeaders);
      
      // Mapping zu unserem Executions Schema
      const expectedHeaders = [
        'Contracts', 'Trade Type', 'Qty', 'Entry Price', 'Realized P&L', 
        'Filled Price', 'Exit Type', 'Filled/Settlement Time(UTC+0)', 'Create Time'
      ];
      
      // Validiere Header
      const headerValid = expectedHeaders.every(expected => 
        originalHeaders.some(original => original.includes(expected.split(' ')[0]))
      );
      
      if (!headerValid) {
        this.log('warn', 'Header validation failed, attempting flexible parsing...');
      }
      
      // Neuer Header für Executions Sheet
      const executionHeaders = [
        'execution_time',    // Konvertiertes Filled Time
        'account_name',      // "Claude Projekt"
        'symbol',           // Contracts
        'side',             // Trade Type
        'executed_qty',     // Qty (bereinigt)
        'entry_price',      // Entry Price (bereinigt)
        'exit_price',       // Filled Price (bereinigt)
        'realized_pnl',     // Realized P&L (bereinigt)
        'execution_type',   // Exit Type
        'trade_id',         // Generiert
        'created_time',     // Create Time (konvertiert)
        'fee',              // 0 (placeholder)
        'fee_currency',     // "USDT"
        'data_source',      // "CSV_IMPORT"
        'import_timestamp', // Aktueller Timestamp
        'raw_data'          // Original Zeile als JSON
      ];
      
      const convertedRows = [executionHeaders];
      const currentTimestamp = new Date().toISOString();
      let successCount = 0;
      
      // Verarbeite Datenzeilen
      for (let i = 1; i < lines.length; i++) {
        try {
          // Parse CSV-Zeile (handle potential commas in quoted fields)
          const csvLine = lines[i];
          const values = this.parseCSVLine(csvLine);
          
          if (values.length < 9) {
            this.log('warn', `Row ${i}: Insufficient columns (${values.length}), skipping`);
            continue;
          }
          
          // Extrahiere Werte
          const contracts = values[0]?.trim() || '';
          const tradeType = values[1]?.trim() || '';
          const qty = values[2]?.trim() || '0';
          const entryPrice = values[3]?.trim() || '0';
          const realizedPnL = values[4]?.trim() || '0';
          const filledPrice = values[5]?.trim() || '0';
          const exitType = values[6]?.trim() || 'Trade';
          const filledTime = values[7]?.trim() || '';
          const createTime = values[8]?.trim() || '';
          
          // Validiere kritische Felder
          if (!contracts || !tradeType || !filledTime) {
            this.log('warn', `Row ${i}: Missing critical data, skipping`);
            continue;
          }
          
          // Konvertiere Zeiten
          const executionTime = this.convertBybitDateTime(filledTime);
          const createdTime = this.convertBybitDateTime(createTime);
          
          // Bereinige numerische Werte
          const cleanQty = this.cleanNumericValue(qty);
          const cleanEntryPrice = this.cleanNumericValue(entryPrice);
          const cleanFilledPrice = this.cleanNumericValue(filledPrice);
          const cleanPnL = this.cleanNumericValue(realizedPnL);
          
          // Generiere Trade ID
          const tradeId = this.generateTradeId(i, contracts, tradeType, cleanQty, cleanEntryPrice);
          
          // Original Daten für raw_data
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
          
          // Neue Zeile zusammenstellen
          const newRow = [
            executionTime,               // execution_time
            'Claude Projekt',            // account_name
            contracts,                   // symbol
            tradeType.toUpperCase(),     // side (BUY/SELL)
            cleanQty,                    // executed_qty
            cleanEntryPrice,             // entry_price
            cleanFilledPrice,            // exit_price
            cleanPnL,                    // realized_pnl
            exitType,                    // execution_type
            tradeId,                     // trade_id
            createdTime,                 // created_time
            0,                           // fee (placeholder)
            'USDT',                      // fee_currency
            'CSV_IMPORT',                // data_source
            currentTimestamp,            // import_timestamp
            JSON.stringify(originalData).replace(/"/g, '""') // raw_data (escape quotes)
          ];
          
          convertedRows.push(newRow);
          successCount++;
          
        } catch (error) {
          this.log('error', `Row ${i} conversion failed: ${error.message}`);
          this.log('error', `Row content: ${lines[i]}`);
        }
      }
      
      this.log('success', `Converted ${successCount} trades successfully`);
      
      // Erstelle neue CSV
      const csvOutput = convertedRows.map(row => 
        row.map(cell => `"${cell}"`).join(',')
      ).join('\n');
      
      // Schreibe Output-Datei
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
    // Einfacher CSV Parser der mit Quoted Fields umgeht
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
    values.push(current); // Letzter Wert
    
    return values;
  }

  async generateImportGuide() {
    const guide = {
      title: "📥 Claude.csv Import Guide",
      file: this.outputFile,
      steps: [
        "1. 🔗 Öffne dein Google Sheets Trading Dashboard",
        "2. 📊 Gehe zum 'Claude_Projekt_Executions' Sheet",
        "3. 📍 Klicke auf Zelle A2 (erste Datenzeile unter Headers)",
        "4. 📤 File → Import → Upload",
        `5. 📁 Wähle die Datei: ${this.outputFile}`,
        "6. ⚙️ Settings:",
        "   - Import location: 'Insert new rows'",
        "   - Separator: 'Comma'",
        "   - Convert text to numbers: ✓",
        "7. ✅ Klicke 'Import data'",
        "8. 🔍 Validiere die importierten Daten"
      ],
      validation: [
        "✅ Alle 17 Trades importiert?",
        "✅ Timestamps im ISO-Format?", 
        "✅ Account Name = 'Claude Projekt'?",
        "✅ Data Source = 'CSV_IMPORT'?",
        "✅ Numerische Werte korrekt konvertiert?"
      ]
    };
    
    return guide;
  }

  async runConversion() {
    try {
      this.log('info', '🚀 Converting existing Claude.csv for Executions import...');
      
      const stats = await this.processCSV();
      const guide = await this.generateImportGuide();
      
      console.log('\n🎉 CONVERSION COMPLETED!');
      console.log('========================');
      console.log(`📁 Input: ${stats.inputFile}`);
      console.log(`📁 Output: ${stats.outputFile}`);
      console.log(`📊 Original trades: ${stats.originalRows}`);
      console.log(`📊 Converted trades: ${stats.convertedRows}`);
      console.log(`📊 Columns: ${stats.headers}`);
      
      console.log('\n📋 IMPORT STEPS:');
      guide.steps.forEach(step => console.log(`   ${step}`));
      
      console.log('\n🔍 VALIDATION CHECKLIST:');
      guide.validation.forEach(check => console.log(`   ${check}`));
      
      return {
        success: true,
        stats,
        guide,
        nextStep: "Import the converted CSV into Claude_Projekt_Executions sheet"
      };
      
    } catch (error) {
      this.log('error', `Conversion failed: ${error.message}`);
      throw error;
    }
  }
}

// Führe Konvertierung aus
const converter = new ExistingCSVConverter();
converter.runConversion()
  .then(result => {
    console.log('\n✅ CSV conversion completed successfully!');
    process.exit(0);
  })
  .catch(error => {
    console.error('\n❌ Conversion failed:', error.message);
    process.exit(1);
  });
