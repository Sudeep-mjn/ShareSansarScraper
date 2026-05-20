import re
import urllib.request
import os

URL = 'https://www.sharesansar.com/today-share-price'
DOCS_INDEX = os.path.join('docs', 'index.html')


def fetch_raw_table():
    try:
        with urllib.request.urlopen(URL, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')
            m = re.search(r'(<table[^>]*class=["\']?[^"\'>]*table-bordered[^>]*>.*?</table>)', html, re.S | re.I)
            if m:
                return m.group(1)
    except Exception as e:
        print('fetch error:', e)
    return None


def embed_raw_table(raw_html):
    if not os.path.exists(DOCS_INDEX):
        raise FileNotFoundError(DOCS_INDEX)
    with open(DOCS_INDEX, 'r', encoding='utf-8') as f:
        content = f.read()

    insertion_point = content.rfind('<div class="footer">')
    if insertion_point == -1:
        # fallback: append at end
        new_content = content + '\n<!-- RAW TABLE -->\n' + (raw_html or '<p>No raw table</p>')
    else:
        raw_block = '\n        <div id="rawTableContainer" class="section">\n            <h2>🧾 Original Extracted Table (Exact)</h2>\n            <div class="stock-table">\n' + (raw_html or '<p>No raw table available</p>') + '\n            </div>\n        </div>\n\n'
        new_content = content[:insertion_point] + raw_block + content[insertion_point:]

    with open(DOCS_INDEX, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Embedded raw table into', DOCS_INDEX)


if __name__ == '__main__':
    raw = fetch_raw_table()
    if not raw:
        print('Could not fetch raw table from', URL)
    else:
        print('Fetched raw table length:', len(raw))
    embed_raw_table(raw)
