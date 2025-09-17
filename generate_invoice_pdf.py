from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import sqlite3
import os
from database import get_db_connection

# Connect to DB via project's helper
conn = get_db_connection()
# sqlite3 connections have row_factory set in database.get_db_connection
cur = conn.cursor()

# Get latest invoice id
if isinstance(conn, sqlite3.Connection):
    cur.execute('SELECT id FROM invoices ORDER BY creation_date DESC LIMIT 1')
else:
    cur.execute('SELECT id FROM invoices ORDER BY creation_date DESC LIMIT 1')
row = cur.fetchone()
if not row:
    print('NO_INVOICE')
    conn.close()
    raise SystemExit(1)

invoice_id = row['id'] if isinstance(row, sqlite3.Row) or hasattr(row, 'keys') else row[0]
print('Generating PDF for invoice', invoice_id)

# Fetch invoice details
if isinstance(conn, sqlite3.Connection):
    cur.execute('''
        SELECT i.id, i.total_amount, i.creation_date, r.raffle_date,
               c.name as client_name, c.last_name as client_last_name,
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = ?
    ''', (invoice_id,))
else:
    cur.execute('''
        SELECT i.id, i.total_amount, i.creation_date, r.raffle_date,
               c.name as client_name, c.last_name as client_last_name,
               u.name as seller_name
        FROM invoices i
        JOIN raffles r ON i.raffle_id = r.id
        JOIN clients c ON i.client_id = c.id
        JOIN users u ON i.seller_id = u.id
        WHERE i.id = %s
    ''', (invoice_id,))

invoice = cur.fetchone()
if not invoice:
    print('Invoice not found')
    conn.close()
    raise SystemExit(1)

# Fetch items
if isinstance(conn, sqlite3.Connection):
    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,))
else:
    cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
items = cur.fetchall()

# Prepare PDF
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

out_name = f"factura_{str(raffle_date).split(' ')[0]}_{invoice_id}.pdf"
with open(out_name, 'wb') as f:
    f.write(buffer.getvalue())

print('Saved', out_name)
conn.close()
