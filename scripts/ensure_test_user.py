import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('lottery.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute('SELECT id FROM users WHERE username = ?', ('gitech',))
if cur.fetchone() is None:
    pw = generate_password_hash('gitech2025')
    cur.execute('INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)', ('gitech', pw, 'seller', 'Gitech Test'))
    conn.commit()
    print('Inserted test seller: gitech')
else:
    print('User gitech already exists')

conn.close()
