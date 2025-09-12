import sqlite3
import os
import psycopg2
from werkzeug.security import generate_password_hash

def get_db_connection():
    """Creates a database connection."""
    if 'DATABASE_URL' in os.environ:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
    else:
        conn = sqlite3.connect('lottery.db')
        conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database from the schema file and adds default users."""
    conn = get_db_connection()
    # The rest of the init_db function needs to be adapted for psycopg2 vs sqlite3
    # This is a more complex change, as the cursor and execution syntax can differ.
    # For now, we will focus on the connection. The init_db() function is typically
    # run locally or as a one-off job, not on every deployment.
    
    # The original init_db logic was for sqlite3. You would run this locally
    # to set up lottery.db or adapt it to run against your production DB once.
    if isinstance(conn, sqlite3.Connection):
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
        print("Database initialized for SQLite.")
    
    conn.close()


if __name__ == '__main__':
    # This will now only initialize an SQLite database.
    # You will need to manually set up your Render Postgres database.
    init_db()