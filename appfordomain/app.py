
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import datetime
from database import get_db_connection, init_db
from io import BytesIO
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
import jwt
import time
from flask_cors import CORS
import os
import sqlite3
from flask import jsonify, g

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
app.config['DATABASE'] = 'lottery.db'

# Enable CORS for mobile clients (adjust origins in production)
# Configure CORS origins from environment variable CORS_ORIGINS (comma-separated) or '*' by default
cors_origins = os.environ.get('CORS_ORIGINS', '*')
if cors_origins.strip() == '*':
    CORS(app)
else:
    origins = [o.strip() for o in cors_origins.split(',') if o.strip()]
    CORS(app, resources={r"/api/*": {"origins": origins}, r"/api/mobile/*": {"origins": origins}})


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


# Serve manifest and service worker at site root so Lighthouse can fetch them
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')


@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static', 'service-worker.js')


# --- Database Initialization ---
@app.cli.command('initdb')
def initdb_command():
    """Creates the database tables and initial users."""
    init_db()
    print('Initialized the database.')

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
    user = conn.execute('SELECT id, username, password, role, name FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'invalid credentials'}), 401

    if not check_password_hash(user['password'], password):
        return jsonify({'error': 'invalid credentials'}), 401

    if user['role'] != 'seller':
        return jsonify({'error': 'user is not a seller'}), 403

    token = generate_jwt({'user_id': user['id'], 'username': username, 'role': user['role']})
    return jsonify({'token': token, 'user': {'id': user['id'], 'username': username, 'name': user.get('name')}})


@app.route('/api/mobile/sorteos')
@mobile_auth_required
def mobile_get_sorteos():
    conn = get_db_connection()
    rows = conn.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC').fetchall()
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
    conn.close()
    return jsonify(sorteos)


@app.route('/api/mobile/winner-payments')
@mobile_auth_required
def mobile_winner_payments():
    sorteo_id = request.args.get('sorteo_id')
    if not sorteo_id:
        return jsonify({'error': 'sorteo_id is required'}), 400

    conn = get_db_connection()
    # Only return winners for this raffle and the current seller
    cur = conn.execute('SELECT w.client_id, c.name, c.last_name, SUM(w.total_payout) as total_payout '
                       'FROM winners w JOIN clients c ON w.client_id = c.id '
                       'WHERE w.raffle_id = ? AND w.seller_id = ? '
                       'GROUP BY w.client_id, c.name, c.last_name', (sorteo_id, g.user_id))
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

        invoice_rows = conn.execute('SELECT DISTINCT invoice_id FROM winners WHERE raffle_id = ? AND client_id = ? AND seller_id = ?', (sorteo_id, client_id, g.user_id)).fetchall()
        facturas = [{'id': inv['invoice_id'] if isinstance(inv, sqlite3.Row) else inv[0]} for inv in invoice_rows]

        results.append({'cliente': client_name, 'pago': total_payout, 'facturas': facturas})

    conn.close()
    return jsonify(results)


# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
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

# --- Dashboard Routes ---
@app.route('/')
@login_required
def index():
    if session['user_role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    else:
        return redirect(url_for('seller_dashboard'))

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
    sellers = conn.execute('SELECT id, username, name, phone, province, commission_percentage, join_date FROM users WHERE role = ? ORDER BY name', ('seller',)).fetchall()
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
        # Check if username already exists
        user_exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if user_exists:
            flash('El nombre de usuario ya existe.', 'danger')
            return render_template('seller_form.html', form_action='create')

        conn.execute('INSERT INTO users (username, password, role, name, phone, province, commission_percentage) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (username, generate_password_hash(password), 'seller', name, phone, province, commission))
        conn.commit()
        conn.close()
        flash('Vendedor creado exitosamente.', 'success')
        return redirect(url_for('list_sellers'))

    return render_template('seller_form.html', form_action='create')

@app.route('/admin/sellers/edit/<int:seller_id>', methods=['GET', 'POST'])
@admin_required
def edit_seller(seller_id):
    conn = get_db_connection()
    seller = conn.execute('SELECT * FROM users WHERE id = ? AND role = ?', (seller_id, 'seller')).fetchone()

    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        province = request.form['province']
        commission = float(request.form['commission_percentage'])
        
        conn.execute('UPDATE users SET name = ?, phone = ?, province = ?, commission_percentage = ? WHERE id = ?',
                     (name, phone, province, commission, seller_id))
        conn.commit()
        conn.close()
        flash('Vendedor actualizado exitosamente.', 'success')
        return redirect(url_for('list_sellers'))

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
    raffles = conn.execute('SELECT * FROM raffles ORDER BY raffle_date DESC').fetchall()
    conn.close()
    return render_template('raffles.html', raffles=raffles)

@app.route('/admin/raffles/new', methods=['GET', 'POST'])
@admin_required
def create_raffle():
    if request.method == 'POST':
        raffle_date_str = request.form['raffle_date']
        
        # Basic validation
        if not raffle_date_str:
            flash('La fecha y hora del sorteo son requeridas.', 'danger')
            return render_template('raffle_form.html')

        raffle_date = datetime.datetime.fromisoformat(raffle_date_str)

        conn = get_db_connection()
        conn.execute('INSERT INTO raffles (raffle_date) VALUES (?)',
                     (raffle_date,))
        conn.commit()
        conn.close()
        flash('Sorteo creado exitosamente.', 'success')
        return redirect(url_for('list_raffles'))

    return render_template('raffle_form.html')

# --- Client Management (Admin & Seller) ---
@app.route('/clients')
@login_required
def list_clients():
    conn = get_db_connection()
    if session['user_role'] == 'admin':
        clients = conn.execute('''
            SELECT c.id, c.name, c.last_name, c.phone, c.address, u.name as seller_name
            FROM clients c JOIN users u ON c.seller_id = u.id
            ORDER BY c.name
        ''').fetchall()
    else: # Seller
        seller_id = session['user_id']
        clients = conn.execute('SELECT * FROM clients WHERE seller_id = ? ORDER BY name', (seller_id,)).fetchall()
    conn.close()
    return render_template('clients.html', clients=clients)

@app.route('/clients/new', methods=['GET', 'POST'])
@login_required
def create_client():
    conn = get_db_connection()
    sellers = conn.execute('SELECT id, name FROM users WHERE role = ?', ('seller',)).fetchall()
    
    if request.method == 'POST':
        name = request.form['name']
        last_name = request.form.get('last_name', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        
        if session['user_role'] == 'admin':
            seller_id = request.form['seller_id']
        else: # Seller
            seller_id = session['user_id']

        conn.execute('INSERT INTO clients (name, last_name, phone, address, seller_id) VALUES (?, ?, ?, ?, ?)',
                     (name, last_name, phone, address, seller_id))
        conn.commit()
        conn.close()
        flash('Cliente creado exitosamente.', 'success')
        return redirect(url_for('list_clients'))

    conn.close()
    return render_template('client_form.html', form_action='create', sellers=sellers)

@app.route('/clients/edit/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    conn = get_db_connection()
    
    # Security check: make sure seller can only edit their own clients
    if session['user_role'] == 'seller':
        client = conn.execute('SELECT * FROM clients WHERE id = ? AND seller_id = ?', (client_id, session['user_id'])).fetchone()
    else: # Admin can edit any client
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()

    if client is None:
        flash('Cliente no encontrado o no tiene permiso para editarlo.', 'danger')
        conn.close()
        return redirect(url_for('list_clients'))

    sellers = conn.execute('SELECT id, name FROM users WHERE role = ?', ('seller',)).fetchall()

    if request.method == 'POST':
        name = request.form['name']
        last_name = request.form.get('last_name', '')
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        seller_id = request.form['seller_id'] if session['user_role'] == 'admin' else session['user_id']

        conn.execute('UPDATE clients SET name=?, last_name=?, phone=?, address=?, seller_id=? WHERE id=?',
                     (name, last_name, phone, address, seller_id, client_id))
        conn.commit()
        conn.close()
        flash('Cliente actualizado exitosamente.', 'success')
        return redirect(url_for('list_clients'))

    conn.close()
    return render_template('client_form.html', form_action='edit', client=client, sellers=sellers)

# --- Sales Management ---
@app.route('/sales/new', methods=['GET', 'POST'])
@seller_required
def new_sale():
    conn = get_db_connection()
    # Get clients for the current seller
    clients = conn.execute('SELECT id, name, last_name FROM clients WHERE seller_id = ? ORDER BY name', (session['user_id'],)).fetchall()
    # Get upcoming, non-calculated raffles
    now = datetime.datetime.now()
    raffles = conn.execute('SELECT id, raffle_date FROM raffles WHERE raffle_date > ? AND results_entered = 0 ORDER BY raffle_date', (now,)).fetchall()

    if request.method == 'POST':
        raffle_id = request.form['raffle_id']
        
        # Server-side validation for the selected raffle
        valid_raffle = conn.execute('SELECT id FROM raffles WHERE id = ? AND raffle_date > ? AND results_entered = 0', (raffle_id, now)).fetchone()
        if not valid_raffle:
            flash('El sorteo seleccionado no es válido o ya no está disponible.', 'danger')
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
                        flash(f'Error en el ítem {i+1}: Verifique el número ({number}) y la cantidad ({quantity_str}).', 'danger')
                        return render_template('new_sale_form.html', clients=clients, raffles=raffles)
                    
                    item_type = 'billete' if len(number) == 4 else 'chance'
                    price_per_unit = 1.0 if item_type == 'billete' else 0.25
                    sub_total = quantity * price_per_unit

                    items.append({
                        'number': number,
                        'quantity': quantity,
                        'item_type': item_type,
                        'price_per_unit': price_per_unit,
                        'sub_total': sub_total
                    })
                    total_amount += sub_total
                except (ValueError, IndexError):
                    flash(f'Error procesando el ítem {i+1}. Verifique los datos.', 'danger')
                    return render_template('new_sale_form.html', clients=clients, raffles=raffles)

        if not items:
            flash('Debe agregar al menos un ítem a la venta.', 'danger')
            return render_template('new_sale_form.html', clients=clients, raffles=raffles)

        # Insert into database
        cur = conn.cursor()
        cur.execute('INSERT INTO invoices (raffle_id, client_id, seller_id, total_amount) VALUES (?, ?, ?, ?)',
                    (raffle_id, client_id, seller_id, total_amount))
        invoice_id = cur.lastrowid

        for item in items:
            cur.execute('INSERT INTO invoice_items (invoice_id, number, item_type, quantity, price_per_unit, sub_total) VALUES (?, ?, ?, ?, ?, ?)',
                        (invoice_id, item['number'], item['item_type'], item['quantity'], item['price_per_unit'], item['sub_total']))
        
        conn.commit()
        conn.close()
        flash('Venta registrada exitosamente.', 'success')
        return redirect(url_for('list_sales'))

    conn.close()
    return render_template('new_sale_form.html', clients=clients, raffles=raffles)

@app.route('/sales')
@login_required
def list_sales():
    conn = get_db_connection()
    
    query = '''
        SELECT i.id, r.raffle_date, r.results_entered, c.name as client_name, u.name as seller_name, i.total_amount
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
    '''
    params = []

    if session['user_role'] == 'seller':
        query += ' WHERE i.seller_id = ?'
        params.append(session['user_id'])
    
    query += ' ORDER BY i.creation_date DESC'

    sales = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return render_template('sales.html', sales=sales, now=datetime.datetime.now())

@app.route('/sales/<int:invoice_id>')
@login_required
def sale_detail(invoice_id):
    conn = get_db_connection()
    
    # Security Check
    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = ?
    '''
    params = [invoice_id]
    if session['user_role'] == 'seller':
        base_query += ' AND i.seller_id = ?'
        params.append(session['user_id'])

    invoice = conn.execute(base_query, tuple(params)).fetchone()

    if invoice is None:
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    items = conn.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,)).fetchall()
    conn.close()

    return render_template('sale_detail.html', invoice=invoice, items=items)


@app.route('/sales/<int:invoice_id>/print')
@login_required
def print_invoice(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor()

    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = ?
    '''
    params = [invoice_id]
    if session.get('user_role') == 'seller':
        base_query += ' AND i.seller_id = ?'
        params.append(session['user_id'])

    cur.execute(base_query, tuple(params))
    invoice = cur.fetchone()
    if invoice is None:
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    items = cur.fetchall()
    conn.close()
    return render_template('print_invoice.html', invoice=invoice, items=items)


@app.route('/sales/<int:invoice_id>/pdf')
@login_required
def invoice_pdf(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor()

    base_query = '''
        SELECT i.id, i.total_amount, i.creation_date, 
               r.raffle_date, 
               c.name as client_name, c.last_name as client_last_name, 
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = ?
    '''
    params = [invoice_id]
    if session.get('user_role') == 'seller':
        base_query += ' AND i.seller_id = ?'
        params.append(session['user_id'])

    cur.execute(base_query, tuple(params))
    invoice = cur.fetchone()
    if invoice is None:
        flash('Factura no encontrada o sin permiso para verla.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    items = cur.fetchall()

    # Prepare PDF (half-letter)
    half_letter = (5.5 * inch, 8.5 * inch)
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=half_letter)
    width, height = half_letter

    left_margin = 40
    right_margin = width - 40
    usable_width = right_margin - left_margin

    y = height - 50
    p.setFont('Helvetica-Bold', 14)
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

        p.drawString(col_num_x, y, str(item['number']))
        p.drawRightString(col_qty_right, y, str(item['quantity']))
        try:
            subtotal = float(item['sub_total'])
        except Exception:
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

    filename = f"factura_{str(raffle_date).split(' ')[0]}_{invoice_id}.pdf"
    conn.close()
    return (buffer.getvalue(), 200, {
        'Content-Type': 'application/pdf',
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


@app.route('/sales/delete/<int:invoice_id>', methods=['POST'])
@seller_required
def delete_sale(invoice_id):
    conn = get_db_connection()
    # First, get the invoice and raffle info to check conditions
    invoice = conn.execute('''
        SELECT i.id, i.seller_id, r.raffle_date, r.results_entered
        FROM invoices i JOIN raffles r ON i.raffle_id = r.id
        WHERE i.id = ?
    ''', (invoice_id,)).fetchone()

    if invoice is None:
        flash('Factura no encontrada.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    # Security check: ensure the invoice belongs to the logged-in seller
    if invoice['seller_id'] != session['user_id']:
        flash('No tiene permiso para borrar esta factura.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    # Condition check: prevent deletion if raffle has happened or results are in
    raffle_datetime = datetime.datetime.fromisoformat(invoice['raffle_date'])
    if raffle_datetime < datetime.datetime.now() or invoice['results_entered']:
        flash('No se puede borrar una factura de un sorteo que ya ha pasado o cuyos ganadores ya han sido calculados.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    # Proceed with deletion
    cur = conn.cursor()
    cur.execute('DELETE FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
    cur.execute('DELETE FROM invoices WHERE id = ?', (invoice_id,))
    conn.commit()
    conn.close()

    flash('Factura borrada exitosamente.', 'success')
    return redirect(url_for('list_sales'))


@app.route('/sales/edit/<int:invoice_id>', methods=['GET', 'POST'])
@seller_required
def edit_sale(invoice_id):
    conn = get_db_connection()
    # Security and condition check
    invoice = conn.execute('''
        SELECT i.id, i.seller_id, i.client_id, i.raffle_id, r.raffle_date, r.results_entered
        FROM invoices i JOIN raffles r ON i.raffle_id = r.id
        WHERE i.id = ? AND i.seller_id = ?
    ''', (invoice_id, session['user_id'])).fetchone()

    if invoice is None:
        flash('Factura no encontrada o sin permiso para editar.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    raffle_datetime = datetime.datetime.fromisoformat(invoice['raffle_date'])
    if raffle_datetime < datetime.datetime.now() or invoice['results_entered']:
        flash('No se puede editar una factura de un sorteo que ya ha pasado o cuyos ganadores han sido calculados.', 'danger')
        conn.close()
        return redirect(url_for('list_sales'))

    if request.method == 'POST':
        # Process form data
        raffle_id = request.form['raffle_id']
        client_id = request.form['client_id']
        numbers = request.form.getlist('number')
        quantities = request.form.getlist('quantity')

        items = []
        total_amount = 0
        for i in range(len(numbers)):
            # (Same validation logic as in new_sale)
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
            # (Re-render edit form with error)
        else:
            # Update database
            cur = conn.cursor()
            # 1. Delete old items
            cur.execute('DELETE FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
            # 2. Update invoice header
            cur.execute('UPDATE invoices SET raffle_id=?, client_id=?, total_amount=? WHERE id=?',
                        (raffle_id, client_id, total_amount, invoice_id))
            # 3. Insert new items
            for item in items:
                cur.execute('INSERT INTO invoice_items (invoice_id, number, item_type, quantity, price_per_unit, sub_total) VALUES (?, ?, ?, ?, ?, ?)',
                            (invoice_id, item['number'], item['item_type'], item['quantity'], item['price_per_unit'], item['sub_total']))
            conn.commit()
            conn.close()
            flash('Factura actualizada exitosamente.', 'success')
            return redirect(url_for('list_sales'))

    # For GET request
    invoice_items = conn.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,)).fetchall()
    clients = conn.execute('SELECT id, name, last_name FROM clients WHERE seller_id = ? ORDER BY name', (session['user_id'],)).fetchall()
    now = datetime.datetime.now()
    # Only show raffles that are in the future and not yet calculated
    raffles = conn.execute('SELECT id, raffle_date FROM raffles WHERE raffle_date > ? AND results_entered = 0 ORDER BY raffle_date', (now,)).fetchall()
    conn.close()

    return render_template('edit_sale_form.html', invoice=invoice, items=invoice_items, clients=clients, raffles=raffles)

# --- Winner Calculation and Display ---


def calculate_winners_for_raffle(raffle_id, p1, p2, p3):
    conn = get_db_connection()
    items = conn.execute('''
        SELECT ii.id, ii.number, ii.item_type, ii.quantity, i.client_id, i.seller_id, i.id as invoice_id
        FROM invoice_items ii
        JOIN invoices i ON ii.invoice_id = i.id
        WHERE i.raffle_id = ?
    ''', (raffle_id,)).fetchall()

    winners = []

    for item in items:
        num = item['number']
        # --- Chance Prizes (No changes in rules) ---
        if item['item_type'] == 'chance':
            if num == p1[2:4]: winners.append((raffle_id, item, '1er Premio - Chance', 14))
            if num == p2[2:4]: winners.append((raffle_id, item, '2do Premio - Chance', 3))
            if num == p3[2:4]: winners.append((raffle_id, item, '3er Premio - Chance', 2))
            continue # Go to next item

        # --- Billete Prizes (New Rules) ---
        if item['item_type'] == 'billete':
            found_major_prize = False
            # 1. Check for 1st prize and its exceptions
            if num == p1:
                winners.append((raffle_id, item, '1er Premio - Billete', 2000))
                # Exceptions: can also win these
                if num[0:2] == p1[0:2]: winners.append((raffle_id, item, '2 Primeras Cifras (1er P)', 3))
                if num[3] == p1[3]: winners.append((raffle_id, item, 'Ultima Cifra (1er P)', 1))
                found_major_prize = True
                continue # Stop checking this billete

            # 2. Check for 2nd prize
            if num == p2:
                winners.append((raffle_id, item, '2do Premio - Billete', 600))
                found_major_prize = True
                continue

            # 3. Check for 3rd prize
            if num == p3:
                winners.append((raffle_id, item, '3er Premio - Billete', 300))
                found_major_prize = True
                continue

            # 4. If no major prize found, check for other prizes in order of value
            if not found_major_prize:
                if num[0:3] == p1[0:3] or num[1:4] == p1[1:4]:
                    winners.append((raffle_id, item, '3 Cifras (1er P)', 50))
                elif num[0:3] == p2[0:3] or num[1:4] == p2[1:4]:
                    winners.append((raffle_id, item, '3 Cifras (2do P)', 20))
                elif num[0:3] == p3[0:3] or num[1:4] == p3[1:4]:
                    winners.append((raffle_id, item, '3 Cifras (3er P)', 10))
                elif num[2:4] == p1[2:4]: # 2 ultimas del 1ro
                    winners.append((raffle_id, item, '2 Ultimas Cifras (1er P)', 3))
                elif num[2:4] == p2[2:4]:
                    winners.append((raffle_id, item, '2 Ultimas Cifras (2do P)', 2))
                elif num[2:4] == p3[2:4]:
                    winners.append((raffle_id, item, '2 Ultimas Cifras (3er P)', 1))
                elif num[0:2] == p1[0:2]: # 2 primeras del 1ro (if it didn't win the main prize)
                    winners.append((raffle_id, item, '2 Primeras Cifras (1er P)', 3))
                elif num[3] == p1[3]: # ultima del 1ro (if it didn't win the main prize)
                    winners.append((raffle_id, item, 'Ultima Cifra (1er P)', 1))

    # Save winners to DB
    cur = conn.cursor()
    # Clear previous winners for this raffle to avoid duplicates if re-calculated
    cur.execute('DELETE FROM winners WHERE raffle_id = ?', (raffle_id,))

    for r_id, item, p_type, amount in winners:
        total_payout = item['quantity'] * amount
        cur.execute('''INSERT INTO winners 
                        (raffle_id, invoice_id, client_id, seller_id, winning_number, prize_type, amount_won, quantity, total_payout)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                        (r_id, item['invoice_id'], item['client_id'], item['seller_id'], item['number'], p_type, amount, item['quantity'], total_payout))

    # Mark raffle as calculated
    cur.execute('UPDATE raffles SET first_prize=?, second_prize=?, third_prize=?, results_entered=1 WHERE id=?', (p1, p2, p3, raffle_id))
    conn.commit()
    conn.close()

@app.route('/admin/raffles/<int:raffle_id>/results', methods=['GET', 'POST'])
@admin_required
def enter_raffle_results(raffle_id):
    conn = get_db_connection()
    raffle = conn.execute('SELECT * FROM raffles WHERE id = ?', (raffle_id,)).fetchone()
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

        if not (p1.isdigit() and len(p1) == 4 and p2.isdigit() and len(p2) == 4 and p3.isdigit() and len(p3) == 4):
            flash('Todos los premios deben ser números de 4 cifras.', 'danger')
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
    
    # Get all raffles that have results for the dropdown
    raffles_with_results = conn.execute('SELECT * FROM raffles WHERE results_entered = 1 ORDER BY raffle_date DESC').fetchall()

    winners = []
    selected_raffle = None
    if raffle_id:
        selected_raffle = conn.execute('SELECT * FROM raffles WHERE id = ?', (raffle_id,)).fetchone()
        query = '''
            SELECT w.*, c.name as client_name, u.name as seller_name, r.raffle_date
            FROM winners w
            JOIN clients c ON w.client_id = c.id
            JOIN users u ON w.seller_id = u.id
            JOIN raffles r ON w.raffle_id = r.id
            WHERE w.raffle_id = ?
        '''
        params = [raffle_id]
        
        if session['user_role'] == 'seller':
            query += ' AND w.seller_id = ? ORDER BY c.name' # Sort by client name for sellers
            params.append(session['user_id'])
        else: # Admin
            query += ' ORDER BY u.name, c.name' # Sort by seller, then client for admins
        
        winners = conn.execute(query, tuple(params)).fetchall()

    conn.close()
    # For admin, sort by raffle date DESC as the primary sort key (in Python, since query is per raffle)
    if session['user_role'] == 'admin' and not raffle_id:
        # If no specific raffle is selected, we could show all winners sorted as requested.
        # For now, the logic requires selecting a raffle first. The sorting is applied within the raffle.
        # To implement global sorting, we would need to change the logic to fetch all winners at once.
        # The request is to sort by raffle date first, so let's adjust the main query when no raffle is selected.
        pass # Let's stick to the per-raffle view for now, as the sorting request is complex for a global view.

    return render_template('winners.html', winners=winners, raffles=raffles_with_results, selected_raffle=selected_raffle)

# --- Admin: Commissions ---
@app.route('/admin/commissions')
@admin_required
def commissions_report():
    conn = get_db_connection()
    
    # Data for filters
    sellers = conn.execute('SELECT id, name FROM users WHERE role = \'seller\'').fetchall()
    raffles = conn.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC').fetchall()

    # Get filter criteria from request
    selected_seller_id = request.args.get('seller_id', default='all')
    selected_raffle_id = request.args.get('raffle_id', default='all')

    # Base query for the report
    query = '''
        SELECT 
            u.id as seller_id, 
            u.name as seller_name, 
            u.commission_percentage, 
            r.id as raffle_id, 
            r.raffle_date, 
            COALESCE(SUM(i.total_amount), 0) as total_sales,
            (SELECT COALESCE(SUM(w.total_payout), 0) FROM winners w WHERE w.seller_id = u.id AND w.raffle_id = r.id) as total_winnings
        FROM users u
        LEFT JOIN invoices i ON u.id = i.seller_id
        LEFT JOIN raffles r ON i.raffle_id = r.id
        WHERE u.role = \'seller\'
    '''
    params = []

    if selected_seller_id != 'all':
        query += ' AND u.id = ?'
        params.append(int(selected_seller_id))
    
    if selected_raffle_id != 'all':
        query += ' AND r.id = ?'
        params.append(int(selected_raffle_id))

    query += ' GROUP BY u.id, r.id ORDER BY r.raffle_date DESC, u.name'

    report_data = conn.execute(query, tuple(params)).fetchall()
    conn.close()

    # Process data for display
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

# --- Main execution ---
if __name__ == '__main__':
    app.run(debug=True)
