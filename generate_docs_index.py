import csv
import glob
import html
import os
from datetime import datetime

DATA_DIR = 'Data'
DOCS_DIR = 'docs'
MASTER_FILE = os.path.join(DATA_DIR, 'all_stocks_master.csv')


def normalize_shifted_row(row):
    symbol = (row.get('Symbol') or '').strip()
    prev_close = (row.get('Previous Close') or '').strip()
    if symbol.isdigit() and prev_close and any(ch.isalpha() for ch in prev_close):
        row['Symbol'] = prev_close
        row['Previous Close'] = row.get('Open', '')
        row['Open'] = row.get('High', '')
        row['High'] = row.get('Low', '')
        row['Low'] = row.get('Close', '')
        row['Close'] = row.get('Difference', '')
        row['Difference'] = row.get('Percent Change', '')
        row['Percent Change'] = row.get('Volume', '')
        row['Volume'] = row.get('Traded Shares', '')
        row['Traded Shares'] = row.get('Amount', '')
        row['Amount'] = row.get('Unnamed: 0', '')
    return row


def load_csv_rows(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [normalize_shifted_row(row) for row in reader]


def find_latest_daily_file():
    daily_files = [path for path in glob.glob(os.path.join(DATA_DIR, '*.csv')) if os.path.basename(path) != 'all_stocks_master.csv']
    if not daily_files:
        return None
    # sort by filename date if possible
    daily_files.sort(reverse=True)
    return daily_files[0]


def format_number(value):
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return html.escape(value or '')


def format_int(value):
    try:
        return f"{int(float(value)):,}"
    except Exception:
        return html.escape(value or '')


def safe_pct(value):
    text = (value or '').strip()
    if text.endswith('%'):
        return text
    return f"{text}%" if text else ''


def positive_class(value):
    try:
        return 'positive' if float(value.replace('%', '')) > 0 else 'negative'
    except Exception:
        return ''


def generate_recent_rows(rows):
    if not rows:
        return '<tr><td colspan="9">No latest data available</td></tr>'

    html_rows = []
    for row in rows:
        change_class = positive_class(row.get('Percent Change', '0'))
        html_rows.append(f"""
            <tr>
                <td><strong>{html.escape(row.get('Symbol', ''))}</strong></td>
                <td>रू {format_number(row.get('Open', ''))}</td>
                <td>रू {format_number(row.get('High', ''))}</td>
                <td>रू {format_number(row.get('Low', ''))}</td>
                <td><strong>रू {format_number(row.get('Close', ''))}</strong></td>
                <td class=\"{change_class}\">{html.escape(row.get('Difference', ''))}</td>
                <td class=\"{change_class}\">{safe_pct(row.get('Percent Change', ''))}</td>
                <td>{format_int(row.get('Volume', ''))}</td>
                <td>रू {format_number(row.get('Amount', ''))}</td>
            </tr>
        """)
    return '\n'.join(html_rows)


def generate_history_rows(rows):
    if not rows:
        return '<tr><td colspan="11">No history data available</td></tr>'

    html_rows = []
    for row in rows:
        change_class = positive_class(row.get('Percent Change', '0'))
        html_rows.append(f"""
            <tr>
                <td>{html.escape(row.get('Date', ''))}</td>
                <td>{html.escape(row.get('Time', ''))}</td>
                <td><strong>{html.escape(row.get('Symbol', ''))}</strong></td>
                <td>रू {format_number(row.get('Open', ''))}</td>
                <td>रू {format_number(row.get('High', ''))}</td>
                <td>रू {format_number(row.get('Low', ''))}</td>
                <td><strong>रू {format_number(row.get('Close', ''))}</strong></td>
                <td class=\"{change_class}\">{html.escape(row.get('Difference', ''))}</td>
                <td class=\"{change_class}\">{safe_pct(row.get('Percent Change', ''))}</td>
                <td>{format_int(row.get('Volume', ''))}</td>
                <td>रू {format_number(row.get('Amount', ''))}</td>
            </tr>
        """)
    return '\n'.join(html_rows)


from string import Template

def write_html(latest_rows, history_rows, current_date, latest_file_name):
    html_template = Template("""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>NEPSE Stock Market Report - $current_date</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; min-height: 100vh; }
        .container { max-width: 1400px; margin: 0 auto; background: white; border-radius: 15px; box-shadow: 0 20px 60px rgba(0,0,0,0.25); overflow: hidden; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .header p { font-size: 1.05em; opacity: 0.95; }
        .button-row { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 30px; }
        .btn { background: #667eea; border: none; color: white; padding: 12px 18px; border-radius: 10px; cursor: pointer; font-size: 0.95em; transition: background 0.25s ease; }
        .btn:hover { background: #5563d4; }
        .btn-secondary { background: #444b7a; }
        .search-section { padding: 20px 30px; background: white; border-bottom: 1px solid #e0e0e0; }
        .search-box { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 16px; }
        .search-box:focus { outline: none; border-color: #667eea; }
        .date-range { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 0 30px 20px 30px; }
        .date-range input { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 16px; }
        .section { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); margin: 0 30px 30px 30px; }
        .section h2 { color: #667eea; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }
        .stock-table { width: 100%; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #667eea; color: white; padding: 12px; text-align: left; font-weight: 600; position: sticky; top: 0; z-index: 1; }
        td { padding: 10px 12px; border-bottom: 1px solid #e0e0e0; }
        tr:hover { background: #f5f5f5; }
        .positive { color: #10b981; font-weight: bold; }
        .negative { color: #ef4444; font-weight: bold; }
        .hidden { display: none; }
        .footer { background: #333; color: white; text-align: center; padding: 20px; font-size: 0.95em; }
        @media (max-width: 768px) { .header h1 { font-size: 1.8em; } }
    </style>
</head>
<body>
    <div class=\"container\">
        <div class=\"header\">
            <h1>📈 NEPSE Stock Market Report</h1>
            <p>Data generated from local CSV files | $current_date</p>
        </div>
        <div class=\"button-row\">
            <button class=\"btn\" onclick=\"showSection('latest')\">Show Latest Data</button>
            <button class=\"btn btn-secondary\" onclick=\"showSection('history')\">Load Previous Data</button>
            <button class=\"btn\" onclick=\"downloadCsv('$latest_file_name', 'share_sansar_latest.csv')\">Download Today's CSV</button>
            <button class=\"btn btn-secondary\" onclick=\"downloadCsv('../Data/all_stocks_master.csv', 'share_sansar_all_data.csv')\">Download All Data</button>
            <button class=\"btn\" onclick=\"downloadFilteredTable()\">Download Filtered View</button>
        </div>
        <div class=\"search-section\">
            <input type=\"text\" class=\"search-box\" id=\"searchInput\" placeholder=\"🔍 Search by symbol, date, or value...\">
        </div>
        <div class=\"date-range\">
            <input type=\"date\" id=\"startDate\" placeholder=\"Start date\">
            <input type=\"date\" id=\"endDate\" placeholder=\"End date\">
            <button class=\"btn btn-secondary\" onclick=\"applyDateFilter()\">Apply Date Range</button>
            <button class=\"btn\" onclick=\"resetFilters()\">Reset Filters</button>
        </div>
        <div id=\"latest\" class=\"section\">
            <h2>📊 Latest Scraped Data</h2>
            <div class=\"stock-table\">
                <table id=\"latestTable\">
                    <thead>
                        <tr>
                            <th>Symbol</th><th>Open</th><th>High</th><th>Low</th><th>Close</th>
                            <th>Change</th><th>% Change</th><th>Volume</th><th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        $latest_rows
                    </tbody>
                </table>
            </div>
        </div>
        <div id=\"history\" class=\"section hidden\">
            <h2>📁 Historical Data</h2>
            <div class=\"stock-table\">
                <table id=\"historyTable\">
                    <thead>
                        <tr>
                            <th>Date</th><th>Time</th><th>Symbol</th><th>Open</th><th>High</th><th>Low</th>
                            <th>Close</th><th>Change</th><th>% Change</th><th>Volume</th><th>Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        $history_rows
                    </tbody>
                </table>
            </div>
        </div>
        <div class=\"footer\">
            <p>Data is served from local CSV backups so you can view and download stock data in the browser.</p>
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
""")

    html_content = html_template.substitute(
        current_date=current_date,
        latest_file_name=latest_file_name,
        latest_rows=latest_rows,
        history_rows=history_rows,
    )

    os.makedirs(DOCS_DIR, exist_ok=True)
    index_path = os.path.join(DOCS_DIR, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    report_path = os.path.join(DOCS_DIR, f'report_{current_date}.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f'Wrote {index_path} and {report_path}')


def main():
    if not os.path.exists(MASTER_FILE):
        raise FileNotFoundError(f'Master CSV not found: {MASTER_FILE}')

    history_rows = load_csv_rows(MASTER_FILE)
    latest_csv = find_latest_daily_file()
    latest_rows = load_csv_rows(latest_csv) if latest_csv else []
    current_date = datetime.now().strftime('%Y-%m-%d')
    latest_file_name = os.path.basename(latest_csv) if latest_csv else ''
    write_html(generate_recent_rows(latest_rows), generate_history_rows(history_rows), current_date, latest_file_name)


if __name__ == '__main__':
    main()
