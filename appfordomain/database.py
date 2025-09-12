
import sqlite3
from werkzeug.security import generate_password_hash

def get_db_connection():
    """Creates a database connection."""
    conn = sqlite3.connect('lottery.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database from the schema file and adds default users."""
    conn = get_db_connection()
    with open('schema.sql') as f:
        conn.executescript(f.read())

    # Check if default users already exist
    admin_exists = conn.execute('SELECT id FROM users WHERE username = ?', ('admin',)).fetchone()
    seller_exists = conn.execute('SELECT id FROM users WHERE username = ?', ('vendedor1',)).fetchone()

    if not admin_exists:
        conn.execute('INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)',
                     ('admin', generate_password_hash('adminpass'), 'admin', 'Administrador Principal'))
        print("Admin user created.")

    if not seller_exists:
        conn.execute('INSERT INTO users (username, password, role, name, phone, province, commission_percentage) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     ('vendedor1', generate_password_hash('vendedorpass'), 'seller', 'Vendedor Uno', '6677-8899', 'Panamá', 10.0))
        print("Default seller user created.")

    conn.commit()
    conn.close()
    print("Database initialized.")

if __name__ == '__main__':
    init_db()
