import sqlite3
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import datetime
from database import get_db_connection
import psycopg2.extras
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import jwt
import time
import os
from flask_cors import CORS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
# Enable CORS for mobile clients (adjust origins in production)
# Configure CORS origins from environment variable CORS_ORIGINS (comma-separated) or '*' by default
cors_origins = os.environ.get('CORS_ORIGINS', '*')
if cors_origins.strip() == '*':
    CORS(app)
else:
    origins = [o.strip() for o in cors_origins.split(',') if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}, r"/api/mobile/*": {"origins": origins}})

# --- Helper function to get a cursor ---
def get_cursor(conn):
    # If this is a sqlite3 Connection, return a cursor object
    if isinstance(conn, sqlite3.Connection):
        return conn.cursor()

    # If it's a psycopg2 connection, return a DictCursor so rows are accessible by name
    try:
        if isinstance(conn, psycopg2.extensions.connection):
            return conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    except Exception:
        pass

    # Fallback: try to return a cursor if available
    try:
        return conn.cursor()
    except Exception:
        return conn


def generate_jwt(payload, exp_seconds=60*60*24):
    data = payload.copy()
    data['exp'] = int(time.time()) + exp_seconds
    token = jwt.encode(data, app.config['SECRET_KEY'], algorithm='HS256')
    return token


def verify_jwt(token):
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return data
    except Exception:
        return None

# --- Decorators for access control ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'admin':
            flash('Acceso no autorizado.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'seller':
            flash('Acceso no autorizado.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = get_cursor(conn)
        # Choose placeholder depending on DB adapter (sqlite uses '?', psycopg2 uses '%s')
        ph = '?' if isinstance(conn, sqlite3.Connection) else '%s'

        cur.execute(f'SELECT * FROM users WHERE username = {ph}', (username,))
        user = cur.fetchone()
        
        cur.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_role'] = user['role']
            session['username'] = user['username']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('seller_dashboard'))
        else:
            flash('Usuario o contraseña incorrectos.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión.', 'success')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        conn = get_db_connection()
        cur = get_cursor(conn)
        ph = '?' if isinstance(conn, sqlite3.Connection) else '%s'
        cur.execute(f'SELECT id, password FROM users WHERE id = {ph}', (session['user_id'],))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user is None:
            flash('Usuario no encontrado.', 'danger')
            return redirect(url_for('login'))

        if not check_password_hash(user['password'], current_password):
            flash('Contraseña actual incorrecta.', 'danger')
            return render_template('change_password.html')

        if new_password != confirm_password:
            flash('Las nuevas contraseñas no coinciden.', 'danger')
            return render_template('change_password.html')

        if len(new_password) < 6:
            flash('La nueva contraseña debe tener al menos 6 caracteres.', 'danger')
            return render_template('change_password.html')

        conn = get_db_connection()
        cur = get_cursor(conn)
        ph = '?' if isinstance(conn, sqlite3.Connection) else '%s'
        cur.execute(f'UPDATE users SET password = {ph} WHERE id = {ph}', (generate_password_hash(new_password), session['user_id']))
        conn.commit()
        cur.close()
        conn.close()

        flash('Contraseña actualizada exitosamente.', 'success')
        return redirect(url_for('index'))

    return render_template('change_password.html')

# --- Dashboard Routes ---
@app.route('/')
@login_required
def index():
    if session['user_role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('seller_dashboard'))


# Serve PWA manifest and service worker at the site root so they are discoverable by Lighthouse
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')


@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js')


@app.route('/lh-test')
def lh_test():
    return send_from_directory('static', 'lh-test.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/seller/dashboard')
@seller_required
def seller_dashboard():
    return render_template('seller_dashboard.html')

# --- Admin: Seller Management ---
@app.route('/admin/sellers')
@admin_required
def list_sellers():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT id, username, name, phone, province, commission_percentage, join_date FROM users WHERE role = %s ORDER BY name', ('seller',))
    sellers = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('sellers.html', sellers=sellers)

@app.route('/admin/sellers/new', methods=['GET', 'POST'])
@admin_required
def create_seller():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']
        phone = request.form['phone']
        province = request.form['province']
        commission = float(request.form['commission_percentage'])

        conn = get_db_connection()
        cur = get_cursor(conn)
        
        cur.execute('SELECT id FROM users WHERE username = %s', (username,))
        user_exists = cur.fetchone()
        
        if user_exists:
            flash('El nombre de usuario ya existe.', 'danger')
            cur.close()
            conn.close()
            return render_template('seller_form.html', form_action='create')

        cur.execute('INSERT INTO users (username, password, role, name, phone, province, commission_percentage) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                     (username, generate_password_hash(password), 'seller', name, phone, province, commission))
        conn.commit()
        cur.close()
        conn.close()
        flash('Vendedor creado exitosamente.', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('seller_form.html', form_action='create')

@app.route('/admin/sellers/edit/<int:seller_id>', methods=['GET', 'POST'])
@admin_required
def edit_seller(seller_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM users WHERE id = %s AND role = %s', (seller_id, 'seller'))
    seller = cur.fetchone()

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        province = request.form['province']
        commission = float(request.form['commission_percentage'])
        
        cur.execute('UPDATE users SET name = %s, phone = %s, province = %s, commission_percentage = %s WHERE id = %s',
                     (name, phone, province, commission, seller_id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Vendedor actualizado exitosamente.', 'success')
        return redirect(url_for('list_sellers'))

    cur.close()
    conn.close()
    if seller is None:
        flash('Vendedor no encontrado.', 'danger')
        return redirect(url_for('list_sellers'))
        
    return render_template('seller_form.html', seller=seller, form_action='edit')

# --- Admin: Raffle Management ---
@app.route('/admin/raffles')
@admin_required
def list_raffles():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM raffles ORDER BY raffle_date DESC')
    raffles = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('raffles.html', raffles=raffles)

@app.route('/admin/raffles/new', methods=['GET', 'POST'])
@admin_required
def create_raffle():
    if request.method == 'POST':
        raffle_date_str = request.form['raffle_date']
        
        if not raffle_date_str:
            flash('La fecha y hora del sorteo son requeridas.', 'danger')
            return render_template('raffle_form.html')

        raffle_date = datetime.datetime.fromisoformat(raffle_date_str)

        conn = get_db_connection()
        cur = get_cursor(conn)
        cur.execute('INSERT INTO raffles (raffle_date) VALUES (%s)', (raffle_date,))
        conn.commit()
        cur.close()
        conn.close()
        flash('Sorteo creado exitosamente.', 'success')
        return redirect(url_for('list_raffles'))

    return render_template('raffle_form.html')

# --- Client Management (Admin & Seller) ---
@app.route('/clients')
@login_required
def list_clients():
    conn = get_db_connection()
    cur = get_cursor(conn)
    if session['user_role'] == 'admin':
        cur.execute('''
            SELECT c.id, c.name, c.last_name, c.phone, c.address, u.name as seller_name
            FROM clients c JOIN users u ON c.seller_id = u.id
            ORDER BY c.name
        ''')
        clients = cur.fetchall()
    else: # Seller
        seller_id = session['user_id']
        cur.execute('SELECT * FROM clients WHERE seller_id = %s ORDER BY name', (seller_id,))
        clients = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('clients.html', clients=clients)

@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def create_client():
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT id, name FROM users WHERE role = %s', ('seller',))
    sellers = cur.fetchall()
    
    if request.method == 'POST':
        name = request.form['name']
        last_name = request.form.get('last_name', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        
        if session['user_role'] == 'admin':
            seller_id = request.form['seller_id']
        else: # Seller
            seller_id = session['user_id']

        cur.execute('INSERT INTO clients (name, last_name, phone, address, seller_id) VALUES (%s, %s, %s, %s, %s)',
                     (name, last_name, phone, address, seller_id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Cliente creado exitosamente.', 'success')
        return redirect(url_for('list_clients'))

    cur.close()
    conn.close()
    return render_template('client_form.html', form_action='create', sellers=sellers)

@app.route('/clients/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    if session['user_role'] == 'seller':
        cur.execute('SELECT * FROM clients WHERE id = %s AND seller_id = %s', (client_id, session['user_id']))
    else: # Admin can edit any client
        cur.execute('SELECT * FROM clients WHERE id = %s', (client_id,))
    client = cur.fetchone()

    if client is None:
        flash('Cliente no encontrado o no tiene permiso para editarlo.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_clients'))

    cur.execute('SELECT id, name FROM users WHERE role = %s', ('seller',))
    sellers = cur.fetchall()

    if request.method == 'POST':
        name = request.form['name']
        last_name = request.form.get('last_name', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        seller_id = request.form['seller_id'] if session['user_role'] == 'admin' else session['user_id']

        cur.execute('UPDATE clients SET name=%s, last_name=%s, phone=%s, address=%s, seller_id=%s WHERE id=%s',
                     (name, last_name, phone, address, seller_id, client_id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Cliente actualizado exitosamente.', 'success')
        return redirect(url_for('list_clients'))

    cur.close()
    conn.close()
    return render_template('client_form.html', form_action='edit', client=client, sellers=sellers)

# --- Sales Management ---
@app.route('/sales/new', methods=['GET', 'POST'])
@seller_required
def new_sale():
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    clients = cur.execute('SELECT id, name, last_name FROM clients WHERE seller_id = %s ORDER BY name', (session['user_id'],))
    clients = cur.fetchall()
    
    now = datetime.datetime.now()
    cur.execute('SELECT id, raffle_date FROM raffles WHERE raffle_date > %s AND results_entered = false ORDER BY raffle_date', (now,))
    raffles = cur.fetchall()

    if request.method == 'POST':
        raffle_id = request.form['raffle_id']
        
        cur.execute('SELECT id FROM raffles WHERE id = %s AND raffle_date > %s AND results_entered = false', (raffle_id, now))
        valid_raffle = cur.fetchone()
        if not valid_raffle:
            flash('El sorteo seleccionado no es válido o ya no está disponible.', 'danger')
            cur.close()
            conn.close()
            return redirect(url_for('new_sale'))

        client_id = request.form['client_id']
        seller_id = session['user_id']
        numbers = request.form.getlist('number')
        quantities = request.form.getlist('quantity')
        items = []
        total_amount = 0

        for i in range(len(numbers)):
            number = numbers[i]
            quantity_str = quantities[i]
            if number and quantity_str:
                try:
                    quantity = int(quantity_str)
                    if not (number.isdigit() and len(number) in [2, 4] and quantity > 0):
                        flash(f'Error en el ítem {i+1}: Verifique el número ({number}) y la cantidad ({quantity_str}). La cantidad debe ser un número entero positivo.', 'danger')
                        return render_template('new_sale_form.html', clients=clients, raffles=raffles)
                    
                    item_type = 'billete' if len(number) == 4 else 'chance'
                    price_per_unit = 1.0 if item_type == 'billete' else 0.25
                    sub_total = quantity * price_per_unit
                    items.append({'number': number, 'quantity': quantity, 'item_type': item_type, 'price_per_unit': price_per_unit, 'sub_total': sub_total})
                    total_amount += sub_total
                except ValueError: # Catch error if quantity_str is not an integer
                    flash(f'Error en el ítem {i+1}: La cantidad ({quantity_str}) debe ser un número entero.', 'danger')
                    return render_template('new_sale_form.html', clients=clients, raffles=raffles)
                except IndexError: # Keep existing IndexError catch
                    flash(f'Error procesando el ítem {i+1}. Verifique los datos.', 'danger')
                    return render_template('new_sale_form.html', clients=clients, raffles=raffles)

        if not items:
            flash('Debe agregar al menos un ítem a la venta.', 'danger')
            return render_template('new_sale_form.html', clients=clients, raffles=raffles)

        cur.execute('INSERT INTO invoices (raffle_id, client_id, seller_id, total_amount) VALUES (%s, %s, %s, %s) RETURNING id',
                    (raffle_id, client_id, seller_id, total_amount))
        invoice_id = cur.fetchone()['id']

        for item in items:
            cur.execute('INSERT INTO invoice_items (invoice_id, number, item_type, quantity, price_per_unit, sub_total) VALUES (%s, %s, %s, %s, %s, %s)',
                        (invoice_id, item['number'], item['item_type'], item['quantity'], item['price_per_unit'], item['sub_total']))
        
        conn.commit()
        cur.close()
        conn.close()
        flash('Venta registrada exitosamente.', 'success')
        return redirect(url_for('list_sales'))

    cur.close()
    conn.close()
    return render_template('new_sale_form.html', clients=clients, raffles=raffles)

@app.route('/sales')
@login_required
def list_sales():
    conn = get_db_connection()
    cur = get_cursor(conn)

    # Fetch the most recent raffle ID
    cur.execute('SELECT id FROM raffles ORDER BY raffle_date DESC LIMIT 1')
    most_recent_raffle = cur.fetchone()
    most_recent_raffle_id = most_recent_raffle['id'] if most_recent_raffle else 'all'

    selected_raffle_id = request.args.get('raffle_id', most_recent_raffle_id)
    selected_client_id = request.args.get('client_id', 'all')
    selected_seller_id = request.args.get('seller_id', 'all')

    query = '''
        SELECT i.id, r.raffle_date, r.results_entered, c.name as client_name, c.last_name as client_last_name, u.name as seller_name, i.total_amount
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
    '''
    params = []
    where_clauses = []

    if session['user_role'] == 'seller':
        where_clauses.append('i.seller_id = %s')
        params.append(session['user_id'])
    elif selected_seller_id != 'all':
        where_clauses.append('i.seller_id = %s')
        params.append(int(selected_seller_id))

    if selected_raffle_id != 'all':
        where_clauses.append('i.raffle_id = %s')
        params.append(int(selected_raffle_id))

    if selected_client_id != 'all':
        where_clauses.append('i.client_id = %s')
        params.append(int(selected_client_id))

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
    
    query += ' ORDER BY i.creation_date DESC'

    cur.execute(query, tuple(params))
    sales = cur.fetchall()

    cur.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC')
    raffles = cur.fetchall()
    
    clients = []
    sellers = []
    if session['user_role'] == 'admin':
        cur.execute('SELECT id, name, last_name FROM clients ORDER BY name')
        clients = cur.fetchall()
        cur.execute('SELECT id, name FROM users WHERE role = \'seller\' ORDER BY name')
        sellers = cur.fetchall()
    else: # Seller
        cur.execute('SELECT id, name, last_name FROM clients WHERE seller_id = %s ORDER BY name', (session['user_id'],))
        clients = cur.fetchall()

    cur.close()
    conn.close()
    
    return render_template('sales.html', 
                           sales=sales, 
                           now=datetime.datetime.now(),
                           raffles=raffles,
                           clients=clients,
                           sellers=sellers,
                           selected_raffle_id=selected_raffle_id,
                           selected_client_id=selected_client_id,
                           selected_seller_id=selected_seller_id
                          )


@app.route('/sales/<int:invoice_id>')
@login_required
def sale_detail(invoice_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = %s
    '''
    params = [invoice_id]
    if session['user_role'] == 'seller':
        base_query += ' AND i.seller_id = %s'
        params.append(session['user_id'])

    cur.execute(base_query, tuple(params))
    invoice = cur.fetchone()

    if invoice is None:
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('sale_detail.html', invoice=invoice, items=items)


@app.route('/sales/<int:invoice_id>/print')
@login_required
def print_invoice(invoice_id):
    conn = get_db_connection()
    cur = get_cursor(conn)

    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = %s
    '''
    params = [invoice_id]
    if session['user_role'] == 'seller':
        base_query += ' AND i.seller_id = %s'
        params.append(session['user_id'])

    cur.execute(base_query, tuple(params))
    invoice = cur.fetchone()

    if invoice is None:
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
    items = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('print_invoice.html', invoice=invoice, items=items)


@app.route('/sales/<int:invoice_id>/pdf')
@login_required
def invoice_pdf(invoice_id):
    # Generate a simple PDF invoice on the server and return it as a response
    conn = get_db_connection()
    cur = get_cursor(conn)

    # reuse sale query
    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = %s
    '''
    params = [invoice_id]
    if session['user_role'] == 'seller':
        base_query += ' AND i.seller_id = %s'
        params.append(session['user_id'])

    cur.execute(base_query, tuple(params))
    invoice = cur.fetchone()
    if invoice is None:
        cur.close()
        conn.close()
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
    items = cur.fetchall()

    # Prepare PDF in memory
    # Half-letter size in points: 5.5in x 8.5in
    half_letter = (5.5 * inch, 8.5 * inch)
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=half_letter)
    width, height = half_letter

    # Margins and column math so everything fits on the half-letter width
    left_margin = 40
    right_margin = width - 40
    usable_width = right_margin - left_margin

    y = height - 50
    p.setFont('Helvetica-Bold', 14)
    # invoice id (try dict-style access first)
    try:
        inv_id = invoice['id']
    except Exception:
        inv_id = invoice[0]
    p.drawString(left_margin, y, f'Factura #{inv_id}')
    y -= 24
    p.setFont('Helvetica', 9)
    try:
        raffle_date = invoice['raffle_date']
    except Exception:
        raffle_date = invoice[3]
    p.drawString(left_margin, y, f'Fecha Sorteo: {str(raffle_date)}')
    y -= 16
    try:
        seller_name = invoice['seller_name']
    except Exception:
        seller_name = invoice[6]
    p.drawString(left_margin, y, f'Vendedor: {seller_name}')
    y -= 16
    try:
        client_name = f"{invoice['client_name']} {invoice.get('client_last_name','') }"
    except Exception:
        client_name = f"{invoice[4]} {invoice[5]}"
    p.drawString(left_margin, y, f'Cliente: {client_name}')
    y -= 22

    # Column positions (tightened): Numero | Cantidad | Subtotal
    col_num_x = left_margin
    col_qty_right = left_margin + int(usable_width * 0.55)
    col_sub_right = right_margin

    p.setFont('Helvetica-Bold', 10)
    p.drawString(col_num_x, y, 'Numero')
    p.drawRightString(col_qty_right, y, 'Cantidad')
    p.drawRightString(col_sub_right, y, 'Subtotal')
    y -= 12
    p.line(left_margin, y, right_margin, y)
    y -= 12
    p.setFont('Helvetica', 9)

    for item in items:
        if y < 60:
            p.showPage()
            y = height - 50
            p.setFont('Helvetica-Bold', 10)
            p.drawString(col_num_x, y, 'Numero')
            p.drawRightString(col_qty_right, y, 'Cantidad')
            p.drawRightString(col_sub_right, y, 'Subtotal')
            y -= 12
            p.line(left_margin, y, right_margin, y)
            y -= 12
            p.setFont('Helvetica', 9)

        # Draw fields, assume dict-like rows (same as before)
        p.drawString(col_num_x, y, str(item['number']))
        p.drawRightString(col_qty_right, y, str(item['quantity']))
        try:
            subtotal = float(item['sub_total'])
        except Exception:
            # fallback: try different key or zero
            try:
                subtotal = float(item.get('subtotal', 0))
            except Exception:
                subtotal = 0.0
        p.drawRightString(col_sub_right, y, f"${subtotal:.2f}")
        y -= 14

    y -= 6
    p.setFont('Helvetica-Bold', 11)
    try:
        total_amount = float(invoice['total_amount'])
    except Exception:
        total_amount = float(invoice[1])
    p.drawRightString(col_sub_right, y, f"Total: ${total_amount:.2f}")

    p.showPage()
    p.save()

    buffer.seek(0)

    # Build filename: raffledate_invoiceid.pdf
    try:
        raffle_date_str = invoice['raffle_date'].strftime('%Y-%m-%d')
    except Exception:
        raffle_date_str = str(invoice['raffle_date']).split(' ')[0]
    filename = f"factura_{raffle_date_str}_{invoice_id}.pdf"

    cur.close()
    conn.close()

    return (buffer.getvalue(), 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename="{filename}"'
    })

@app.route('/sales/<int:invoice_id>/printpdf')
@login_required
def printpdf(invoice_id):
    # Return the PDF and let client handle printing / sharing
    return invoice_pdf(invoice_id)


@app.route('/factura/<int:invoice_id>')
@login_required
def factura_redirect(invoice_id):
    # Backwards-compatible route: redirect old /factura/<id> links to /sales/<id>
    return redirect(url_for('sale_detail', invoice_id=invoice_id))


@app.route('/sales/delete/<int:invoice_id>', methods=['POST'])
@seller_required
def delete_sale(invoice_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    cur.execute('''
        SELECT i.id, i.seller_id, r.raffle_date, r.results_entered
        FROM invoices i JOIN raffles r ON i.raffle_id = r.id
        WHERE i.id = %s
    ''', (invoice_id,))
    invoice = cur.fetchone()

    if invoice is None:
        flash('Factura no encontrada.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    if invoice['seller_id'] != session['user_id']:
        flash('No tiene permiso para borrar esta factura.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    raffle_datetime = invoice['raffle_date']
    if raffle_datetime < datetime.datetime.now() or invoice['results_entered']:
        flash('No se puede borrar una factura de un sorteo que ya ha pasado o cuyos ganadores ya han sido calculados.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    cur.execute('DELETE FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
    cur.execute('DELETE FROM invoices WHERE id = %s', (invoice_id,))
    conn.commit()
    cur.close()
    conn.close()

    flash('Factura borrada exitosamente.', 'success')
    return redirect(url_for('list_sales'))


@app.route('/sales/edit/<int:invoice_id>', methods=['GET', 'POST'])
@seller_required
def edit_sale(invoice_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    cur.execute('''
        SELECT i.id, i.seller_id, i.client_id, i.raffle_id, r.raffle_date, r.results_entered
        FROM invoices i JOIN raffles r ON i.raffle_id = r.id
        WHERE i.id = %s AND i.seller_id = %s
    ''', (invoice_id, session['user_id']))
    invoice = cur.fetchone()

    if invoice is None:
        flash('Factura no encontrada o sin permiso para editar.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    raffle_datetime = invoice['raffle_date']
    if raffle_datetime < datetime.datetime.now() or invoice['results_entered']:
        flash('No se puede editar una factura de un sorteo que ya ha pasado o cuyos ganadores han sido calculados.', 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('list_sales'))

    if request.method == 'POST':
        raffle_id = request.form['raffle_id']
        client_id = request.form['client_id']
        numbers = request.form.getlist('number')
        quantities = request.form.getlist('quantity')
        items = []
        total_amount = 0
        for i in range(len(numbers)):
            number = numbers[i]
            quantity_str = quantities[i]
            if number and quantity_str:
                quantity = int(quantity_str)
                item_type = 'billete' if len(number) == 4 else 'chance'
                price_per_unit = 1.0 if item_type == 'billete' else 0.25
                sub_total = quantity * price_per_unit
                items.append({'number': number, 'quantity': quantity, 'item_type': item_type, 'price_per_unit': price_per_unit, 'sub_total': sub_total})
                total_amount += sub_total

        if not items:
            flash('La factura debe tener al menos un ítem.', 'danger')
        else:
            cur.execute('DELETE FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
            cur.execute('UPDATE invoices SET raffle_id=%s, client_id=%s, total_amount=%s WHERE id=%s',
                        (raffle_id, client_id, total_amount, invoice_id))
            for item in items:
                cur.execute('INSERT INTO invoice_items (invoice_id, number, item_type, quantity, price_per_unit, sub_total) VALUES (%s, %s, %s, %s, %s, %s)',
                            (invoice_id, item['number'], item['item_type'], item['quantity'], item['price_per_unit'], item['sub_total']))
            conn.commit()
            cur.close()
            conn.close()
            flash('Factura actualizada exitosamente.', 'success')
            return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
    invoice_items = cur.fetchall()
    cur.execute('SELECT id, name, last_name FROM clients WHERE seller_id = %s ORDER BY name', (session['user_id'],))
    clients = cur.fetchall()
    now = datetime.datetime.now()
    cur.execute('SELECT id, raffle_date FROM raffles WHERE raffle_date > %s AND results_entered = false ORDER BY raffle_date', (now,))
    raffles = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('edit_sale_form.html', invoice=invoice, items=invoice_items, clients=clients, raffles=raffles)

# --- Winner Calculation and Display ---

def calculate_winners_for_raffle(raffle_id, p1, p2, p3):
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('''
        SELECT ii.id, ii.number, ii.item_type, ii.quantity, i.client_id, i.seller_id, i.id as invoice_id
        FROM invoice_items ii
        JOIN invoices i ON ii.invoice_id = i.id
        WHERE i.raffle_id = %s
    ''', (raffle_id,))
    items = cur.fetchall()

    winners = []
    p1_chance = p1[2:4]
    p2_chance = p2 if len(p2) == 2 else p2[2:4]
    p3_chance = p3 if len(p3) == 2 else p3[2:4]

    for item in items:
        num = item['number']
        if item['item_type'] == 'chance':
            if num == p1_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (1er P)', 14))
            if num == p2_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (2do P)', 3))
            if num == p3_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (3er P)', 2))
            continue
        if item['item_type'] == 'billete':
            if num == p1: winners.append((raffle_id, item, '1er Premio - Billete', 2000))
            elif len(p2) == 4 and num == p2: winners.append((raffle_id, item, '2do Premio - Billete', 600))
            elif len(p3) == 4 and num == p3: winners.append((raffle_id, item, '3er Premio - Billete', 300))
            elif num[0:3] == p1[0:3] or num[1:4] == p1[1:4]: winners.append((raffle_id, item, '3 Cifras (1er P)', 50))
            elif len(p2) == 4 and (num[0:3] == p2[0:3] or num[1:4] == p2[1:4]): winners.append((raffle_id, item, '3 Cifras (2do P)', 20))
            elif len(p3) == 4 and (num[0:3] == p3[0:3] or num[1:4] == p3[1:4]): winners.append((raffle_id, item, '3 Cifras (3er P)', 10))
            elif num[0:2] == p1[0:2] and num[3] == p1[3]: winners.append((raffle_id, item, '2 Primeras y Ultima Cifra (1er P)', 4))
            elif num[0:2] == p1[0:2] or num[2:4] == p1_chance: winners.append((raffle_id, item, '2 Primeras o 2 Ultimas Cifras (1er P)', 3))
            elif len(p2) == 4 and num[2:4] == p2_chance: winners.append((raffle_id, item, '2 Ultimas Cifras (2do P)', 2))
            elif num[3] == p1[3]: winners.append((raffle_id, item, 'Ultima Cifra (1er P)', 1))
            elif len(p3) == 4 and num[2:4] == p3_chance: winners.append((raffle_id, item, '2 Ultimas Cifras (3er P)', 1))

    cur.execute('DELETE FROM winners WHERE raffle_id = %s', (raffle_id,))
    for r_id, item, p_type, amount in winners:
        total_payout = item['quantity'] * amount
        cur.execute('''INSERT INTO winners 
                        (raffle_id, invoice_id, client_id, seller_id, winning_number, prize_type, amount_won, quantity, total_payout)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                        (r_id, item['invoice_id'], item['client_id'], item['seller_id'], item['number'], p_type, amount, item['quantity'], total_payout))

    cur.execute('UPDATE raffles SET first_prize=%s, second_prize=%s, third_prize=%s, results_entered=true WHERE id=%s', (p1, p2, p3, raffle_id))
    conn.commit()
    cur.close()
    conn.close()

@app.route('/admin/raffles/<int:raffle_id>/results', methods=['GET', 'POST'])
@admin_required
def enter_raffle_results(raffle_id):
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT * FROM raffles WHERE id = %s', (raffle_id,))
    raffle = cur.fetchone()
    cur.close()
    conn.close()

    if raffle is None:
        flash('Sorteo no encontrado.', 'danger')
        return redirect(url_for('list_raffles'))

    if raffle['results_entered']:
        flash('Los resultados para este sorteo ya fueron ingresados.', 'info')
        return redirect(url_for('list_winners', raffle_id=raffle_id))

    if request.method == 'POST':
        p1 = request.form['first_prize']
        p2 = request.form['second_prize']
        p3 = request.form['third_prize']

        if not (p1.isdigit() and len(p1) == 4 and p2.isdigit() and len(p2) in [2, 4] and p3.isdigit() and len(p3) in [2, 4]):
            flash('El 1er premio debe ser de 4 cifras. El 2do y 3ro deben ser de 2 o 4 cifras.', 'danger')
            return render_template('raffle_results_form.html', raffle=raffle)
        
        calculate_winners_for_raffle(raffle_id, p1, p2, p3)
        flash('Ganadores calculados y registrados exitosamente!', 'success')
        return redirect(url_for('list_winners', raffle_id=raffle_id))

    return render_template('raffle_results_form.html', raffle=raffle)

@app.route('/winners')
@login_required
def list_winners():
    raffle_id = request.args.get('raffle_id', type=int)
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    cur.execute('SELECT * FROM raffles WHERE results_entered = true ORDER BY raffle_date DESC')
    raffles_with_results = cur.fetchall()

    winners = []
    selected_raffle = None
    if raffle_id:
        cur.execute('SELECT * FROM raffles WHERE id = %s', (raffle_id,))
        selected_raffle = cur.fetchone()
        query = '''
            SELECT w.*, c.name as client_name, u.name as seller_name, r.raffle_date
            FROM winners w
            JOIN clients c ON w.client_id = c.id
            JOIN users u ON w.seller_id = u.id
            JOIN raffles r ON w.raffle_id = r.id
            WHERE w.raffle_id = %s
        '''
        params = [raffle_id]
        
        if session['user_role'] == 'seller':
            query += ' AND w.seller_id = %s ORDER BY c.name'
            params.append(session['user_id'])
        else: # Admin
            query += ' ORDER BY u.name, c.name'
        
        cur.execute(query, tuple(params))
        winners = cur.fetchall()

    cur.close()
    conn.close()
    
    return render_template('winners.html', winners=winners, raffles=raffles_with_results, selected_raffle=selected_raffle)

# --- Admin: Commissions ---
@app.route('/admin/commissions')
@admin_required
def commissions_report():
    conn = get_db_connection()
    cur = get_cursor(conn)
    
    cur.execute('SELECT id, name FROM users WHERE role = \'seller\'')
    sellers = cur.fetchall()
    cur.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC')
    raffles = cur.fetchall()

    selected_seller_id = request.args.get('seller_id', default='all')
    selected_raffle_id = request.args.get('raffle_id', default='all')

    query = '''
        SELECT 
            u.id as seller_id, u.name as seller_name, u.commission_percentage, 
            r.id as raffle_id, r.raffle_date, 
            COALESCE(SUM(i.total_amount), 0) as total_sales,
            (SELECT COALESCE(SUM(w.total_payout), 0) FROM winners w WHERE w.seller_id = u.id AND w.raffle_id = r.id) as total_winnings
        FROM users u
        LEFT JOIN invoices i ON u.id = i.seller_id
        LEFT JOIN raffles r ON i.raffle_id = r.id
        WHERE u.role = \'seller\'
    '''
    params = []

    if selected_seller_id != 'all':
        query += ' AND u.id = %s'
        params.append(int(selected_seller_id))
    
    if selected_raffle_id != 'all':
        query += ' AND r.id = %s'
        params.append(int(selected_raffle_id))

    query += ' GROUP BY u.id, r.id ORDER BY r.raffle_date DESC, u.name'

    cur.execute(query, tuple(params))
    report_data = cur.fetchall()
    cur.close()
    conn.close()

    processed_data = []
    for row in report_data:
        row_dict = dict(row)
        commission_amount = row_dict['total_sales'] * (row_dict['commission_percentage'] / 100.0)
        balance = row_dict['total_sales'] - commission_amount - row_dict['total_winnings']
        row_dict['commission_amount'] = commission_amount
        row_dict['balance'] = balance
        processed_data.append(row_dict)

    return render_template('commissions.html', 
                           report_data=processed_data,
                           sellers=sellers,
                           raffles=raffles,
                           selected_seller_id=selected_seller_id,
                           selected_raffle_id=selected_raffle_id)

# --- Seller: Commissions ---
@app.route('/my_commissions')
@seller_required
def my_commissions():
    conn = get_db_connection()
    cur = get_cursor(conn)
    seller_id = session['user_id']

    cur.execute('SELECT commission_percentage FROM users WHERE id = %s', (seller_id,))
    user = cur.fetchone()
    commission_percentage = user['commission_percentage'] if user else 0

    query = '''
        SELECT 
            r.id as raffle_id, r.raffle_date, 
            COALESCE(SUM(i.total_amount), 0) as total_sales,
            (SELECT COALESCE(SUM(w.total_payout), 0) FROM winners w WHERE w.seller_id = %s AND w.raffle_id = r.id) as total_winnings
        FROM raffles r
        LEFT JOIN invoices i ON r.id = i.raffle_id AND i.seller_id = %s
        WHERE r.results_entered = true
        GROUP BY r.id
        ORDER BY r.raffle_date DESC
    '''
    
    cur.execute(query, (seller_id, seller_id))
    report_data = cur.fetchall()
    cur.close()
    conn.close()

    processed_data = []
    for row in report_data:
        row_dict = dict(row)
        commission_amount = row_dict['total_sales'] * (commission_percentage / 100.0)
        balance = row_dict['total_sales'] - commission_amount - row_dict['total_winnings']
        
        row_dict['commission_amount'] = commission_amount
        row_dict['balance'] = balance
        processed_data.append(row_dict)

    return render_template('my_commissions.html', report_data=processed_data)

@app.route('/seller/winner-payments')
@seller_required
def winner_payments():
    return render_template('pagos_ganadores.html')


# --- Mobile API (seller-only) ---
def mobile_auth_required(func):
    def wrapper(*args, **kwargs):
        # Try session first
        if 'user_id' in session and session.get('user_role') == 'seller':
            g.user_id = session['user_id']
            return func(*args, **kwargs)

        # Else try Authorization header with Bearer token
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
            data = verify_jwt(token)
            if data and data.get('role') == 'seller':
                g.user_id = data.get('user_id')
                return func(*args, **kwargs)

        return jsonify({'error': 'Unauthorized'}), 401
    wrapper.__name__ = func.__name__
    return wrapper


@app.route('/api/mobile/login', methods=['POST'])
def mobile_login():
    body = request.get_json() or {}
    username = body.get('username')
    password = body.get('password')
    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    conn = get_db_connection()
    cur = get_cursor(conn)
    # SQLite vs psycopg2 placeholder handling
    try:
        cur.execute('SELECT id, username, password, role, name FROM users WHERE username = %s', (username,))
    except Exception:
        cur.execute('SELECT id, username, password, role, name FROM users WHERE username = ?', (username,))

    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return jsonify({'error': 'invalid credentials'}), 401

    # password field may be accessed differently depending on row type
    try:
        stored = user['password']
    except Exception:
        stored = user[2]

    if not check_password_hash(stored, password):
        return jsonify({'error': 'invalid credentials'}), 401

    try:
        role = user['role']
        user_id = user['id']
        name = user.get('name')
    except Exception:
        role = user[3]
        user_id = user[0]
        name = user[4] if len(user) > 4 else None

    if role != 'seller':
        return jsonify({'error': 'user is not a seller'}), 403

    token = generate_jwt({'user_id': user_id, 'username': username, 'role': role})
    return jsonify({'token': token, 'user': {'id': user_id, 'username': username, 'name': name}})


@app.route('/api/mobile/sorteos')
@mobile_auth_required
def mobile_get_sorteos():
    # reuse server-side sorteo listing but return JSON
    conn = get_db_connection()
    cur = get_cursor(conn)
    cur.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC')
    rows = cur.fetchall()
    sorteos = []
    for row in rows:
        try:
            id_val = row['id']
            date_val = row['raffle_date']
        except Exception:
            id_val = row[0]
            date_val = row[1]
        try:
            date_str = date_val.strftime('%Y-%m-%d %H:%M')
        except Exception:
            date_str = str(date_val)
        sorteos.append({'id': id_val, 'date': date_str})
    cur.close()
    conn.close()
    return jsonify(sorteos)


@app.route('/api/mobile/winner-payments')
@mobile_auth_required
def mobile_winner_payments():
    # Very similar to existing /api/winner-payments but only accessible for sellers
    sorteo_id = request.args.get('sorteo_id')
    if not sorteo_id:
        return jsonify({'error': 'sorteo_id is required'}), 400

    conn = get_db_connection()
    cur = get_cursor(conn)
    ph = '?' if isinstance(conn, sqlite3.Connection) else '%s'

    # Only return winners for this raffle and the current seller
    sql = (
        'SELECT w.client_id, c.name, c.last_name, SUM(w.total_payout) as total_payout '
        'FROM winners w JOIN clients c ON w.client_id = c.id '
        f'WHERE w.raffle_id = {ph} AND w.seller_id = {ph} '
        'GROUP BY w.client_id, c.name, c.last_name'
    )
    params = [sorteo_id, g.user_id]
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    results = []
    for row in rows:
        try:
            client_id = row['client_id']
            first_name = row.get('name')
            last_name = row.get('last_name')
            total_payout = row.get('total_payout')
        except Exception:
            client_id = row[0]
            first_name = row[1]
            last_name = row[2]
            total_payout = row[3]

        client_name = ((first_name or '') + ' ' + (last_name or '')).strip() or 'Cliente'

        # invoices
        sql_invoices = f'SELECT DISTINCT invoice_id FROM winners WHERE raffle_id = {ph} AND client_id = {ph} AND seller_id = {ph}'
        cur.execute(sql_invoices, (sorteo_id, client_id, g.user_id))
        invoice_rows = cur.fetchall()
        facturas = []
        for inv in invoice_rows:
            try:
                inv_id = inv['invoice_id']
            except Exception:
                inv_id = inv[0]
            facturas.append({'id': inv_id})

        results.append({'cliente': client_name, 'pago': total_payout, 'facturas': facturas})

    cur.close()
    conn.close()
    return jsonify(results)

@app.route('/api/sorteos')
@seller_required
def get_sorteos():
    conn = get_db_connection()
    cur = get_cursor(conn)
    # raffle_date is the column name in the schema; handle both sqlite (string) and psycopg2 (datetime)
    cur.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC')
    rows = cur.fetchall()
    sorteos = []
    for row in rows:
        # support sqlite3.Row (mapping) and psycopg2 DictRow or tuples
        try:
            date_val = row['raffle_date']
        except Exception:
            date_val = row[1]

        # Normalize to YYYY-MM-DD string regardless of type
        if date_val is None:
            date_str = ''
        else:
            # psycopg2 may return a datetime, sqlite may return a string
            try:
                # If it's a datetime-like object
                date_str = date_val.strftime('%Y-%m-%d')
            except Exception:
                # Fallback: convert to string and take date part
                date_str = str(date_val).split(' ')[0]

        try:
            id_val = row['id']
        except Exception:
            id_val = row[0]

        sorteos.append({'id': id_val, 'date': date_str})
    cur.close()
    conn.close()
    return jsonify(sorteos)

@app.route('/api/winner-payments')
@seller_required
def api_winner_payments():
    sorteo_id = request.args.get('sorteo_id')
    if not sorteo_id:
        return jsonify({'error': 'sorteo_id is required'}), 400

    conn = get_db_connection()
    cur = get_cursor(conn)
    # Choose placeholder depending on DB adapter
    ph = '?' if isinstance(conn, sqlite3.Connection) else '%s'

    # Query winners for the given raffle grouped by client
    sql_main = (
        'SELECT w.client_id, c.name, c.last_name, SUM(w.total_payout) as total_payout '
        'FROM winners w JOIN clients c ON w.client_id = c.id '
        f'WHERE w.raffle_id = {ph}'
    )
    params_main = [sorteo_id]

    # If the current user is a seller, restrict results to their own sales
    if session.get('user_role') == 'seller':
        sql_main += f' AND w.seller_id = {ph}'
        params_main.append(session.get('user_id'))

    sql_main += ' GROUP BY w.client_id, c.name, c.last_name'
    cur.execute(sql_main, tuple(params_main))
    rows = cur.fetchall()

    results = []
    for row in rows:
        # Extract fields safely for both mapping and sequence row types
        try:
            client_id = row['client_id']
            first_name = row.get('name')
            last_name = row.get('last_name')
            total_payout = row.get('total_payout')
        except Exception:
            client_id = row[0]
            first_name = row[1]
            last_name = row[2]
            total_payout = row[3]

        client_name = ((first_name or '') + ' ' + (last_name or '')).strip() or 'Cliente'

        # Fetch distinct invoice ids for that client and raffle
        sql_invoices = f'SELECT DISTINCT invoice_id FROM winners WHERE raffle_id = {ph} AND client_id = {ph}'
        params_inv = [sorteo_id, client_id]
        if session.get('user_role') == 'seller':
            sql_invoices += f' AND seller_id = {ph}'
            params_inv.append(session.get('user_id'))
        cur.execute(sql_invoices, tuple(params_inv))
        invoice_rows = cur.fetchall()
        facturas = []
        for inv in invoice_rows:
            try:
                inv_id = inv['invoice_id']
            except Exception:
                inv_id = inv[0]
            facturas.append({'id': inv_id})

        results.append({'cliente': client_name.strip(), 'pago': total_payout, 'facturas': facturas})

    cur.close()
    conn.close()
    return jsonify(results)


# --- Main execution ---
if __name__ == '__main__':
    app.run(debug=True)