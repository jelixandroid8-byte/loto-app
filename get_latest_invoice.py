import sqlite3

conn = sqlite3.connect('lottery.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute('SELECT id FROM invoices ORDER BY creation_date DESC LIMIT 1')
row = cur.fetchone()
if row:
    print(row['id'])
else:
    print('NO_INVOICE')
conn.close()
