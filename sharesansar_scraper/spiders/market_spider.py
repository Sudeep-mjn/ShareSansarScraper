import scrapy
from scrapy.selector import Selector
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re
import os
from string import Template
import gspread.exceptions

class MarketSpider(scrapy.Spider):
    name = "market"
    start_urls = ['https://www.sharesansar.com/today-share-price']
    
    def __init__(self, *args, **kwargs):
        super(MarketSpider, self).__init__(*args, **kwargs)
        
        # Google Sheets setup with your service account
        self.scope = ['https://spreadsheets.google.com/feeds',
                      'https://www.googleapis.com/auth/drive']
        
        # Create Data directory if it doesn't exist
        if not os.path.exists('Data'):
            os.makedirs('Data')
        
        try:
            # Use your service account
            self.creds = ServiceAccountCredentials.from_json_keyfile_name(
                'google_creds.json', self.scope)
            self.client = gspread.authorize(self.creds)
            
            # Open your Google Sheet (create one named "NEPSE_Stock_Data" first)
            self.sheet = self.client.open('NEPSE_Stock_Data').sheet1
            
            # Add headers if sheet is empty
            if len(self.sheet.get_all_values()) == 0:
                headers = ['Date', 'Symbol', 'Open', 'High', 'Low', 'Close', 
                          'Volume', 'Previous Close', 'Traded Shares', 'Amount', 
                          'Difference', 'Percent Change']
                self.sheet.append_row(headers)
                self.logger.info("Google Sheet headers added")
            else:
                self.logger.info(f"Google Sheet found with {len(self.sheet.get_all_values())-1} existing records")
                
        except Exception as e:
            self.logger.error(f"Error connecting to Google Sheets: {e}")
            self.logger.info("Will continue with CSV backup only")
            self.sheet = None
    
    def parse(self, response):
        """Extract stock data and save to Google Sheets and CSV"""
        
        # Find the table containing stock data
        table_rows = response.css('table.table-bordered tr')
        
        current_date = datetime.now().strftime('%Y-%m-%d')
        current_time = datetime.now().strftime('%H:%M:%S')
        scraped_count = 0
        stock_data_list = []
        
        for row in table_rows[1:]:  # Skip header row
            columns = row.css('td')
            if len(columns) >= 12:
                try:
                    symbol = self.clean_text(columns[1].css('::text').get())
                    
                    # Skip if symbol is empty or if row is just a serial number row
                    if not symbol:
                        continue
                    
                    stock_data = {
                        'Date': current_date,
                        'Time': current_time,
                        'Symbol': symbol,
                        'Previous Close': self.clean_text(columns[2].css('::text').get()),
                        'Open': self.clean_text(columns[3].css('::text').get()),
                        'High': self.clean_text(columns[4].css('::text').get()),
                        'Low': self.clean_text(columns[5].css('::text').get()),
                        'Close': self.clean_text(columns[6].css('::text').get()),
                        'Difference': self.clean_text(columns[7].css('::text').get()),
                        'Percent Change': self.clean_text(columns[8].css('::text').get()),
                        'Volume': self.clean_text(columns[9].css('::text').get()),
                        'Traded Shares': self.clean_text(columns[10].css('::text').get()),
                        'Amount': self.clean_text(columns[11].css('::text').get())
                    }
                    
                    stock_data_list.append(stock_data)
                    
                    # collect rows; we'll write to Google Sheets in bulk later
                    
                    scraped_count += 1
                    
                except Exception as e:
                    self.logger.warning(f"Error processing row: {e}")
        
        # Save to CSV backup
        if stock_data_list:
            self.save_to_csv(stock_data_list, current_date)

        # Save daily worksheet to Google Sheets (bulk) with dedup/closed checks
        if self.sheet:
            try:
                self.save_daily_sheet(stock_data_list, current_date)
            except Exception as e:
                self.logger.error(f"Error saving daily sheet: {e}")
        self.logger.info(f"Successfully scraped {scraped_count} stocks")

        # Capture the raw HTML table from the source so we can render it exactly
        try:
            raw_table_html = response.css('table.table-bordered').get()
        except Exception:
            raw_table_html = None

        # Create HTML report (include raw table HTML for exact view)
        self.create_html_report(stock_data_list, current_date, raw_table_html)

        return stock_data_list
    
    def clean_text(self, text):
        """Clean extracted text data"""
        if text is None:
            return ''
        return text.strip().replace(',', '').replace('₹', '').strip()
    
    def add_to_google_sheets(self, stock_data):
        """Add stock data to Google Sheets"""
        try:
            row = [
                stock_data['Date'],
                stock_data['Symbol'],
                stock_data['Open'],
                stock_data['High'],
                stock_data['Low'],
                stock_data['Close'],
                stock_data['Volume'],
                stock_data['Previous Close'],
                stock_data['Traded Shares'],
                stock_data['Amount'],
                stock_data['Difference'],
                stock_data['Percent Change']
            ]
            # Deprecated: per-row append removed in favor of bulk daily writes
            self.logger.debug("add_to_google_sheets called but per-row append is disabled")
        except Exception as e:
            self.logger.error(f"Error adding to Google Sheets: {e}")

    def save_daily_sheet(self, stock_data_list, current_date):
        """Save full day's data as a new worksheet in the Google Spreadsheet.

        - Skip if market appears closed (no rows)
        - Skip if today's full table equals previous day's table
        - Do not overwrite an existing worksheet for the same date
        """
        if not stock_data_list:
            self.logger.info("No stock data extracted — skipping sheet save (market closed?)")
            return

        try:
            spreadsheet = self.client.open('NEPSE_Stock_Data')
        except Exception as e:
            self.logger.error(f"Could not open spreadsheet: {e}")
            return

        # If worksheet for this date already exists, do not modify it
        try:
            ws_existing = spreadsheet.worksheet(current_date)
            self.logger.info(f"Worksheet '{current_date}' already exists — not modifying")
            return
        except gspread.exceptions.WorksheetNotFound:
            pass

        df_today = pd.DataFrame(stock_data_list)

        # Compare with previous day's data using master CSV if available
        master_file = 'Data/all_stocks_master.csv'
        if os.path.exists(master_file):
            try:
                master_df = pd.read_csv(master_file)
                # find previous date (latest date different from current_date)
                prev_dates = [d for d in master_df['Date'].unique() if d != current_date]
                if prev_dates:
                    prev_date = max(prev_dates)
                    prev_df = master_df[master_df['Date'] == prev_date]

                    # compare core columns (exclude Date/Time ordering differences)
                    compare_cols = [
                        'Symbol','Previous Close','Open','High','Low','Close',
                        'Difference','Percent Change','Volume','Traded Shares','Amount'
                    ]
                    if set(compare_cols).issubset(prev_df.columns) and set(compare_cols).issubset(df_today.columns):
                        prev_sorted = prev_df[compare_cols].sort_values(by='Symbol').reset_index(drop=True)
                        today_sorted = df_today[compare_cols].sort_values(by='Symbol').reset_index(drop=True)
                        if prev_sorted.equals(today_sorted):
                            self.logger.info("Today's data matches previous day's data — skipping sheet save")
                            return
            except Exception as e:
                self.logger.warning(f"Error comparing with master CSV: {e}")

        # Otherwise create new worksheet and upload data
        headers = ['Date','Time','Symbol','Previous Close','Open','High','Low','Close',
                   'Difference','Percent Change','Volume','Traded Shares','Amount']

        try:
            rows = [headers]
            for _, row in df_today.iterrows():
                rows.append([str(row.get(h, '')) for h in headers])

            ws = spreadsheet.add_worksheet(title=current_date, rows=str(len(rows)+5), cols=str(len(headers)))
            ws.update(rows)
            self.logger.info(f"Created worksheet '{current_date}' with {len(rows)-1} rows")
        except Exception as e:
            self.logger.error(f"Failed to create/update worksheet '{current_date}': {e}")
    
    def save_to_csv(self, stock_data_list, current_date):
        """Save data to CSV file"""
        try:
            df = pd.DataFrame(stock_data_list)
            filename = f"Data/{current_date}.csv"
            df.to_csv(filename, index=False)
            self.logger.info(f"CSV backup saved to {filename}")
            
            # Also save to a master file with all historical data
            master_file = "Data/all_stocks_master.csv"
            if os.path.exists(master_file):
                existing_df = pd.read_csv(master_file)
                combined_df = pd.concat([existing_df, df], ignore_index=True)
                combined_df.to_csv(master_file, index=False)
            else:
                df.to_csv(master_file, index=False)
            self.logger.info(f"Master CSV updated")
            
        except Exception as e:
            self.logger.error(f"Error saving CSV: {e}")
    
    def create_html_report(self, stock_data_list, current_date, raw_table_html=None):
        """Create HTML report for browser viewing"""
        try:
            df = pd.DataFrame(stock_data_list)
            master_file = 'Data/all_stocks_master.csv'
            master_df = pd.read_csv(master_file) if os.path.exists(master_file) else df.copy()
            
            # Calculate some statistics
            top_gainers = df.nlargest(10, 'Percent Change') if not df.empty else pd.DataFrame()
            top_losers = df.nsmallest(10, 'Percent Change') if not df.empty else pd.DataFrame()
            total_volume = df['Volume'].astype(float).sum() if not df.empty else 0
            avg_close = df['Close'].astype(float).mean() if not df.empty else 0
            
            # Prepare HTML parts to avoid f-string brace issues
            top_gainers_html = self.generate_top_gainers_html(top_gainers)
            top_losers_html = self.generate_top_losers_html(top_losers)
            complete_table_html = self.generate_complete_table_html(df)
            history_table_html = self.generate_history_table_html(master_df)
            now_time = datetime.now().strftime('%H:%M:%S')
            # Pre-format numeric values for template
            avg_close_str = f"{avg_close:,.2f}"
            total_volume_str = f"{total_volume:,.0f}"
            len_df_str = str(len(df))

            html_template = Template("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NEPSE Stock Market Report - $current_date</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.25);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .header p {{
            font-size: 1.05em;
            opacity: 0.95;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 30px;
            background: #f8f9fa;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        }}
        .stat-card h3 {{
            color: #667eea;
            margin-bottom: 10px;
            font-size: 0.9em;
            text-transform: uppercase;
        }}
        .stat-card .value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }}
        .button-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin: 20px 30px;
        }}
        .btn {{
            background: #667eea;
            border: none;
            color: white;
            padding: 12px 18px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 0.95em;
            transition: background 0.25s ease;
        }}
        .btn:hover {{
            background: #5563d4;
        }}
        .btn-secondary {{
            background: #444b7a;
        }}
        .search-section {{
            padding: 20px 30px;
            background: white;
            border-bottom: 1px solid #e0e0e0;
        }}
        .search-box {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        .search-box:focus {{
            outline: none;
            border-color: #667eea;
        }}
        .date-range {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 14px;
            margin: 0 30px 20px 30px;
        }}
        .date-range input {{
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }}
        .section {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin: 0 30px 30px 30px;
        }}
        .section h2 {{
            color: #667eea;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }}
        .stock-table {{
            width: 100%;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 1;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e0e0e0;
        }}
        tr:hover {{
            background: #f5f5f5;
        }}
        .positive {{
            color: #10b981;
            font-weight: bold;
        }}
        .negative {{
            color: #ef4444;
            font-weight: bold;
        }}
        .hidden {{
            display: none;
        }}
        .footer {{
            background: #333;
            color: white;
            text-align: center;
            padding: 20px;
            font-size: 0.95em;
        }}
        @media (max-width: 768px) {{
            .stats {{
                grid-template-columns: 1fr;
            }}
            .header h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📈 NEPSE Stock Market Report</h1>
            <p>Data scraped from ShareSansar.com | $current_date at $now_time</p>
        </div>
        <div class="stats">
            <div class="stat-card">
                <h3>Total Companies</h3>
                <div class="value">$len_df</div>
            </div>
            <div class="stat-card">
                <h3>Average Closing Price</h3>
                <div class="value">रू $avg_close</div>
            </div>
            <div class="stat-card">
                <h3>Total Volume</h3>
                <div class="value">$total_volume</div>
            </div>
            <div class="stat-card">
                <h3>Last Updated</h3>
                <div class="value">$now_time</div>
            </div>
        </div>
        <div class="button-row">
            <button class="btn" onclick="showSection('latest')">Show Latest Data</button>
            <button class="btn btn-secondary" onclick="showSection('history')">Load Previous Data</button>
            <button class="btn" onclick="toggleRaw()">Show Original Extracted Table</button>
            <button class="btn" onclick="downloadCsv('../Data/$current_date.csv', 'share_sansar_$current_date.csv')">Download Today's CSV</button>
            <button class="btn btn-secondary" onclick="downloadCsv('../Data/all_stocks_master.csv', 'share_sansar_all_data.csv')">Download All Data</button>
            <button class="btn" onclick="downloadFilteredTable()">Download Filtered View</button>
        </div>
        <div class="search-section">
            <input type="text" class="search-box" id="searchInput" placeholder="🔍 Search by symbol, date, or company...">
        </div>
        <div class="date-range">
            <input type="date" id="startDate" placeholder="Start date">
            <input type="date" id="endDate" placeholder="End date">
            <button class="btn btn-secondary" onclick="applyDateFilter()">Apply Date Range</button>
            <button class="btn" onclick="resetFilters()">Reset Filters</button>
        </div>
        <div id="latest" class="section">
            <h2>📊 Latest Scraped Data</h2>
            <div class="stock-table">
                <table id="latestTable">
                    <thead>
                        <tr>
                            <th>Symbol</th><th>Open</th><th>High</th><th>Low</th><th>Close</th>
                            <th>Change</th><th>% Change</th><th>Volume</th><th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        $complete_table_html
                    </tbody>
                </table>
            </div>
        </div>

        <div id="rawTableContainer" class="section hidden">
            <h2>🧾 Original Extracted Table (Exact)</h2>
            <div class="stock-table">
                <!-- Raw HTML from source inserted below -->
                {raw_table_html if raw_table_html else '<p>No raw table available</p>'}
            </div>
        </div>
        <div id="history" class="section hidden">
            <h2>📁 Historical Data</h2>
            <div class="stock-table">
                <table id="historyTable">
                    <thead>
                        <tr>
                            <th>Date</th><th>Time</th><th>Symbol</th><th>Open</th><th>High</th><th>Low</th>
                            <th>Close</th><th>Change</th><th>% Change</th><th>Volume</th><th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        $history_table_html
                    </tbody>
                </table>
            </div>
        </div>
        <div class="footer">
            <p>Data automatically scraped daily from ShareSansar.com.</p>
            <p>Use search, date range, and download buttons to view, select, or export data in bulk.</p>
        </div>
    </div>
    <script>
        const searchInput = document.getElementById('searchInput');
        const latestTable = document.getElementById('latestTable');
        const historyTable = document.getElementById('historyTable');

        searchInput.addEventListener('keyup', function() {
            filterTable(latestTable, this.value);
            filterTable(historyTable, this.value);
        });

        function showSection(section) {
            document.getElementById('latest').classList.toggle('hidden', section !== 'latest');
            document.getElementById('history').classList.toggle('hidden', section !== 'history');
        }

        function filterTable(table, searchValue) {
            if (!table) return;
            const query = searchValue.toLowerCase();
            const rows = table.getElementsByTagName('tr');
            for (let i = 1; i < rows.length; i++) {
                const cells = rows[i].getElementsByTagName('td');
                if (!cells.length) continue;
                const text = Array.from(cells).map(cell => cell.textContent.toLowerCase()).join(' ');
                rows[i].style.display = text.indexOf(query) > -1 ? '' : 'none';
            }
        }

        function applyDateFilter() {
            const start = document.getElementById('startDate').value;
            const end = document.getElementById('endDate').value;
            const rows = historyTable.getElementsByTagName('tr');
            for (let i = 1; i < rows.length; i++) {
                const dateCell = rows[i].getElementsByTagName('td')[0];
                if (!dateCell) continue;
                const rowDate = dateCell.textContent.trim();
                const dateValue = new Date(rowDate);
                const validStart = start ? new Date(start) : null;
                const validEnd = end ? new Date(end) : null;
                let show = true;
                if (validStart && dateValue < validStart) show = false;
                if (validEnd && dateValue > validEnd) show = false;
                rows[i].style.display = show ? '' : 'none';
            }
        }

        function resetFilters() {
            document.getElementById('searchInput').value = '';
            document.getElementById('startDate').value = '';
            document.getElementById('endDate').value = '';
            filterTable(latestTable, '');
            filterTable(historyTable, '');
        }

        function downloadCsv(path, fileName) {
            const link = document.createElement('a');
            link.href = path;
            link.download = fileName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function downloadFilteredTable() {
            const activeTable = document.getElementById('latest').classList.contains('hidden') ? historyTable : latestTable;
            const fileName = document.getElementById('latest').classList.contains('hidden') ? 'share_sansar_history_filtered.csv' : 'share_sansar_latest_filtered.csv';
            exportTableToCSV(activeTable, fileName);
        }

        function exportTableToCSV(table, filename) {
            if (!table) return;
            const rows = table.querySelectorAll('tr');
            const csv = [];
            rows.forEach(row => {
                if (row.style.display === 'none') return;
                const cols = row.querySelectorAll('td, th');
                const rowData = Array.from(cols).map(col => '"' + col.innerText.replace(/"/g, '""') + '"').join(',');
                csv.push(rowData);
            });
            const csvString = csv.join('\n');
            const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }
    </script>
</body>
</html>
            """
            )
            html_content = html_template.substitute(
                current_date=current_date,
                now_time=now_time,
                avg_close=avg_close_str,
                total_volume=total_volume_str,
                len_df=len_df_str,
                top_gainers_html=top_gainers_html,
                top_losers_html=top_losers_html,
                complete_table_html=complete_table_html,
                history_table_html=history_table_html,
                raw_table_html=(raw_table_html if raw_table_html else '<p>No raw table available</p>')
            )
            
            # Save HTML file
            with open('docs/index.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Also save dated version
            with open(f'docs/report_{current_date}.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML report generated at docs/index.html")
        except Exception as e:
            self.logger.error(f"Error creating HTML report: {e}")
    
    def generate_history_table_html(self, df):
        if df.empty:
            return "<tr><td colspan='11'>No historical data available</td></tr>"
        
        html = ""
        for _, row in df.iterrows():
            change_class = "positive" if float(row['Percent Change']) > 0 else "negative"
            html += f"""
            <tr>
                <td>{row.get('Date', '')}</td>
                <td>{row.get('Time', '')}</td>
                <td><strong>{row['Symbol']}</strong></td>
                <td>रू {float(row['Open']):,.2f}</td>
                <td>रू {float(row['High']):,.2f}</td>
                <td>रू {float(row['Low']):,.2f}</td>
                <td><strong>रू {float(row['Close']):,.2f}</strong></td>
                <td class="{change_class}">{row['Difference']}</td>
                <td class="{change_class}">{row['Percent Change']}</td>
                <td>{float(row['Volume']):,.0f}</td>
                <td>रू {float(row['Amount']):,.2f}</td>
            </tr>
            """
        return html
    
    def generate_top_losers_html(self, df):
        if df.empty:
            return "<tr><td colspan='4'>No data available</td></tr>"
        
        html = ""
        for _, row in df.iterrows():
            change_class = "positive" if float(row['Percent Change']) > 0 else "negative"
            html += f"""
            <tr>
                <td><strong>{row['Symbol']}</strong></td>
                <td>रू {float(row['Close']):,.2f}</td>
                <td class="{change_class}">{row['Difference']}</td>
                <td>{float(row['Volume']):,.0f}</td>
            </tr>
            """
        return html
    
    def generate_complete_table_html(self, df):
        if df.empty:
            return "<tr><td colspan='9'>No data available</td></tr>"
        
        html = ""
        for _, row in df.iterrows():
            change_class = "positive" if float(row['Percent Change']) > 0 else "negative"
            percent_change = row['Percent Change'].replace('%', '')
            html += f"""
            <tr>
                <td><strong>{row['Symbol']}</strong></td>
                <td>रू {float(row['Open']):,.2f}</td>
                <td>रू {float(row['High']):,.2f}</td>
                <td>रू {float(row['Low']):,.2f}</td>
                <td><strong>रू {float(row['Close']):,.2f}</strong></td>
                <td class="{change_class}">{row['Difference']}</td>
                <td class="{change_class}">{row['Percent Change']}</td>
                <td>{float(row['Volume']):,.0f}</td>
                <td>रू {float(row['Amount']):,.2f}</td>
            </tr>
            """
        return html