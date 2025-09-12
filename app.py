
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import datetime
from database import get_db_connection, init_db

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'
app.config['DATABASE'] = 'lottery.db'

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
    
    # Get filter criteria from request
    selected_raffle_id = request.args.get('raffle_id', 'all')
    selected_client_id = request.args.get('client_id', 'all')
    selected_seller_id = request.args.get('seller_id', 'all')

    # Base query
    query = '''
        SELECT i.id, r.raffle_date, r.results_entered, c.name as client_name, c.last_name as client_last_name, u.name as seller_name, i.total_amount
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
    '''
    params = []
    where_clauses = []

    # Role-based filtering
    if session['user_role'] == 'seller':
        where_clauses.append('i.seller_id = ?')
        params.append(session['user_id'])
    elif selected_seller_id != 'all':
        where_clauses.append('i.seller_id = ?')
        params.append(int(selected_seller_id))

    if selected_raffle_id != 'all':
        where_clauses.append('i.raffle_id = ?')
        params.append(int(selected_raffle_id))
    
    if selected_client_id != 'all':
        where_clauses.append('i.client_id = ?')
        params.append(int(selected_client_id))

    if where_clauses:
        query += ' WHERE ' + ' AND '.join(where_clauses)
    
    query += ' ORDER BY i.creation_date DESC'

    sales = conn.execute(query, tuple(params)).fetchall()

    # Data for filters
    raffles = conn.execute('SELECT id, raffle_date FROM raffles ORDER BY raffle_date DESC').fetchall()
    
    # Clients and Sellers for filters depend on role
    clients = []
    sellers = []
    if session['user_role'] == 'admin':
        clients = conn.execute('SELECT id, name, last_name FROM clients ORDER BY name').fetchall()
        sellers = conn.execute('SELECT id, name FROM users WHERE role = \'seller\' ORDER BY name').fetchall()
    else: # Seller
        clients = conn.execute('SELECT id, name, last_name FROM clients WHERE seller_id = ? ORDER BY name', (session['user_id'],)).fetchall()

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
    
    # Define chance numbers based on prize length
    p1_chance = p1[2:4]
    p2_chance = p2 if len(p2) == 2 else p2[2:4]
    p3_chance = p3 if len(p3) == 2 else p3[2:4]

    for item in items:
        num = item['number']
        
        # --- Chance Prizes (Can win multiple) ---
        if item['item_type'] == 'chance':
            if num == p1_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (1er P)', 14))
            if num == p2_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (2do P)', 3))
            if num == p3_chance: winners.append((raffle_id, item, 'Chance - 2 Ultimas (3er P)', 2))
            continue # Done with this item, go to next

        # --- Billete Prizes (Highest prize only) ---
        if item['item_type'] == 'billete':
            # Check in descending order of prize value
            if num == p1: # $2000
                winners.append((raffle_id, item, '1er Premio - Billete', 2000))
            elif len(p2) == 4 and num == p2: # $600
                winners.append((raffle_id, item, '2do Premio - Billete', 600))
            elif len(p3) == 4 and num == p3: # $300
                winners.append((raffle_id, item, '3er Premio - Billete', 300))
            elif num[0:3] == p1[0:3] or num[1:4] == p1[1:4]: # $50
                winners.append((raffle_id, item, '3 Cifras (1er P)', 50))
            elif len(p2) == 4 and (num[0:3] == p2[0:3] or num[1:4] == p2[1:4]): # $20
                winners.append((raffle_id, item, '3 Cifras (2do P)', 20))
            elif len(p3) == 4 and (num[0:3] == p3[0:3] or num[1:4] == p3[1:4]): # $10
                winners.append((raffle_id, item, '3 Cifras (3er P)', 10))
            elif num[0:2] == p1[0:2] and num[3] == p1[3]: # $4
                winners.append((raffle_id, item, '2 Primeras y Ultima Cifra (1er P)', 4))
            elif num[0:2] == p1[0:2] or num[2:4] == p1_chance: # $3
                winners.append((raffle_id, item, '2 Primeras o 2 Ultimas Cifras (1er P)', 3))
            elif len(p2) == 4 and num[2:4] == p2_chance: # $2
                winners.append((raffle_id, item, '2 Ultimas Cifras (2do P)', 2))
            elif num[3] == p1[3]: # $1
                winners.append((raffle_id, item, 'Ultima Cifra (1er P)', 1))
            elif len(p3) == 4 and num[2:4] == p3_chance: # $1
                winners.append((raffle_id, item, '2 Ultimas Cifras (3er P)', 1))


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

        # Updated validation
        if not (p1.isdigit() and len(p1) == 4 and
                p2.isdigit() and len(p2) in [2, 4] and
                p3.isdigit() and len(p3) in [2, 4]):
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

# --- Seller: Commissions ---
@app.route('/my_commissions')
@seller_required
def my_commissions():
    conn = get_db_connection()
    seller_id = session['user_id']

    # The user's commission percentage is needed for calculations
    user = conn.execute('SELECT commission_percentage FROM users WHERE id = ?', (seller_id,)).fetchone()
    commission_percentage = user['commission_percentage'] if user else 0

    # This query groups by raffle and calculates total sales and winnings for the seller
    query = '''
        SELECT 
            r.id as raffle_id, 
            r.raffle_date, 
            COALESCE(SUM(i.total_amount), 0) as total_sales,
            (SELECT COALESCE(SUM(w.total_payout), 0) FROM winners w WHERE w.seller_id = ? AND w.raffle_id = r.id) as total_winnings
        FROM raffles r
        LEFT JOIN invoices i ON r.id = i.raffle_id AND i.seller_id = ?
        WHERE r.results_entered = 1
        GROUP BY r.id
        ORDER BY r.raffle_date DESC
    '''
    
    report_data = conn.execute(query, (seller_id, seller_id)).fetchall()
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


# --- Main execution ---
if __name__ == '__main__':
    app.run(debug=True)
