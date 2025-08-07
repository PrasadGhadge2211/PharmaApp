from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from datetime import datetime, timedelta
from database import init_db, get_db_connection, get_db_cursor
import os
import sqlite3
import random
import string
from weasyprint import HTML
from io import BytesIO
import pytz
import multiprocessing


# In app.py, ensure you have:
app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Initialize database
init_db()

# Helper functions
def generate_invoice_number():
    return f"INV-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{random.randint(1000,9999)}"

LOCAL_TIMEZONE = pytz.timezone('Asia/Kolkata')
@app.template_filter('local_datetime')
def local_datetime_filter(dt):
    if isinstance(dt, str):
        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    return dt.astimezone(LOCAL_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')

@app.route('/')
def dashboard():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get today's date in UTC for comparison
        today_utc = datetime.utcnow().strftime('%Y-%m-%d')
        current_month_utc = datetime.utcnow().strftime('%Y-%m')
        expiry_threshold = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
        
        
        # Expiry notifications (next 30 days)
        cursor.execute('''
            SELECT * FROM medicines 
            WHERE expiry_date <= ? 
            ORDER BY expiry_date
        ''', (expiry_threshold,))
        expiring_meds = cursor.fetchall()
        
        # Low stock
        cursor.execute('SELECT * FROM medicines WHERE quantity < 10')
        low_stock = cursor.fetchall()
        
        # Recent sales (last 5)
        cursor.execute('''
            SELECT s.*, c.name as customer_name 
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY date DESC
            LIMIT 5
        ''')
        recent_sales = cursor.fetchall()
    
    return render_template('dashboard.html', 
                         expiring_meds=expiring_meds,
                         low_stock=low_stock,
                         recent_sales=recent_sales,
                         today=today_utc,
                         datetime=datetime,
                         now=datetime.utcnow())

# Inventory Management
@app.route('/inventory')
def inventory():
    search_query = request.args.get('search', '').strip()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if search_query:
            # Search by name, batch number, or supplier
            cursor.execute('''
                SELECT * FROM medicines 
                WHERE name LIKE ? 
                   OR batch_number LIKE ? 
                   OR supplier LIKE ?
                ORDER BY name
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        else:
            cursor.execute('SELECT * FROM medicines WHERE general = FALSE ORDER BY name')
            
        medicines = cursor.fetchall()
    
    return render_template('inventory/list.html', medicines=medicines)

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_medicine():
    if request.method == 'POST':
        try:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    INSERT INTO medicines 
                    (name, batch_number, quantity, price, cost_price, 
                     supplier, company, mfg_date, expiry_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    request.form['name'],
                    request.form['batch_number'],
                    int(request.form['quantity']),
                    float(request.form['price']),
                    float(request.form['cost_price']),
                    request.form['supplier'],
                    request.form['company'],
                    request.form['mfg_date'],
                    request.form['expiry_date']
                ))
            flash('Medicine added successfully!', 'success')
            return redirect(url_for('inventory'))
        except sqlite3.IntegrityError:
            flash('Batch number already exists!', 'danger')
        except ValueError:
            flash('Invalid number format for quantity/price!', 'danger')
        except Exception as e:
            flash(f'Error adding medicine: {str(e)}', 'danger')
    
    return render_template('inventory/add.html')

@app.route('/inventory/edit/<int:id>', methods=['GET', 'POST'])
def edit_medicine(id):
    if request.method == 'POST':
        try:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    UPDATE medicines 
                    SET name=?, batch_number=?, quantity=?, price=?, 
                        cost_price=?, supplier=?, company=?, 
                        mfg_date=?, expiry_date=?
                    WHERE id=?
                ''', (
                    request.form['name'],
                    request.form['batch_number'],
                    int(request.form['quantity']),
                    float(request.form['price']),
                    float(request.form['cost_price']),
                    request.form['supplier'],
                    request.form['company'],
                    request.form['mfg_date'],
                    request.form['expiry_date'],
                    id
                ))
            flash('Medicine updated successfully!', 'success')
            return redirect(url_for('inventory'))
        except sqlite3.IntegrityError:
            flash('Batch number already exists for another medicine!', 'danger')
        except ValueError:
            flash('Invalid number format for quantity/price!', 'danger')
        except Exception as e:
            flash(f'Error updating medicine: {str(e)}', 'danger')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM medicines WHERE id=?', (id,))
        medicine = cursor.fetchone()
    
    if not medicine:
        flash('Medicine not found!', 'danger')
        return redirect(url_for('inventory'))
    
    return render_template('inventory/edit.html', medicine=medicine)

@app.route('/inventory/delete/<int:id>', methods=['GET'])
def delete_medicine(id):
    try:
        with get_db_cursor() as cursor:
            cursor.execute('''
                DELETE FROM medicines 
                WHERE id=?
            ''', (id,))
        flash('Medicine deleted successfully!', 'success')
    except Exception as e:
        print("Error deleting medicine:", e)
        flash('Failed to delete medicine', 'error')
    
    return redirect(url_for('inventory'))

#General 
@app.route('/gen_inventory')
def gen_inventory():
    search_query = request.args.get('search', '').strip()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if search_query:
            # Search by name, batch number, or supplier
            cursor.execute('''
                SELECT * FROM medicines 
                WHERE name LIKE ? 
                   OR batch_number LIKE ? 
                   OR supplier LIKE ?
                ORDER BY name
            ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        else:
            cursor.execute('SELECT * FROM medicines WHERE general = TRUE ORDER BY name')
            
        medicines = cursor.fetchall()
    
    return render_template('general/list.html', medicines=medicines)

@app.route('/general/add', methods=['GET', 'POST'])
def gen_add():
    if request.method == 'POST':
        try:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    INSERT INTO medicines 
                    (name, batch_number, quantity, price, cost_price, 
                     supplier, company, mfg_date, expiry_date, general)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    request.form['name'],
                    request.form['batch_number'],
                    int(request.form['quantity']),
                    float(request.form['price']),
                    float(request.form['cost_price']),
                    request.form['supplier'],
                    request.form['company'],
                    request.form['mfg_date'],
                    request.form['expiry_date'],
                    1
                ))
            flash('Item added successfully!', 'success')
            return redirect(url_for('gen_inventory'))
        except sqlite3.IntegrityError:
            flash('Batch number already exists!', 'danger')
        except ValueError:
            flash('Invalid number format for quantity/price!', 'danger')
        except Exception as e:
            flash(f'Error adding medicine: {str(e)}', 'danger')
    
    return render_template('general/add.html')

@app.route('/general/edit/<int:id>', methods=['GET', 'POST'])
def edit_general(id):
    if request.method == 'POST':
        try:
            with get_db_cursor() as cursor:
                cursor.execute('''
                    UPDATE medicines 
                    SET name=?, batch_number=?, quantity=?, price=?, 
                        cost_price=?, supplier=?, company=?, 
                        mfg_date=?, expiry_date=?, general=1
                    WHERE id=?
                ''', (
                    request.form['name'],
                    request.form['batch_number'],
                    int(request.form['quantity']),
                    float(request.form['price']),
                    float(request.form['cost_price']),
                    request.form['supplier'],
                    request.form['company'],
                    request.form['mfg_date'],
                    request.form['expiry_date'],
                    id
                ))
            flash('Item updated successfully!', 'success')
            return redirect(url_for('gen_inventory'))
        except sqlite3.IntegrityError:
            flash('Batch number already exists for another medicine!', 'danger')
        except ValueError:
            flash('Invalid number format for quantity/price!', 'danger')
        except Exception as e:
            flash(f'Error updating medicine: {str(e)}', 'danger')
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM medicines WHERE id=?', (id,))
        medicine = cursor.fetchone()
    
    if not medicine:
        flash('Medicine not found!', 'danger')
        return redirect(url_for('gen_inventory'))
    
    return render_template('general/edit.html', medicine=medicine)

@app.route('/general/delete/<int:id>', methods=['GET'])
def delete_gen(id):
    try:
        with get_db_cursor() as cursor:
            cursor.execute('''
                DELETE FROM medicines 
                WHERE id=?
            ''', (id,))
        flash('Item deleted successfully!', 'success')
    except Exception as e:
        print("Error deleting medicine:", e)
        flash('Failed to delete medicine', 'error')
    
    return redirect(url_for('gen_inventory'))

# Customer Management
@app.route('/customers')
def customers():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customers ORDER BY name')
        customers = cursor.fetchall()
    return render_template('customers/list.html', customers=customers)

@app.route('/customers/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        with get_db_cursor() as cursor:
            cursor.execute('''
                INSERT INTO customers (name, phone, email, address)
                VALUES (?, ?, ?, ?)
            ''', (
                request.form['name'],
                request.form['phone'],
                request.form['email'],
                request.form['address']
            ))
        flash('Customer added successfully!', 'success')
        return redirect(url_for('customers'))
    
    return render_template('customers/add.html')

@app.route('/customers/<int:id>')
def view_customer(id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM customers WHERE id=?', (id,))
        customer = cursor.fetchone()
        
        cursor.execute('''
            SELECT * FROM sales 
            WHERE customer_id=?
            ORDER BY date DESC
        ''', (id,))
        purchases = cursor.fetchall()
    
    return render_template('customers/view.html', customer=customer, purchases=purchases)

# Sales Management Routes
@app.route('/sales')
def sales():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, c.name as customer_name,
                   datetime(s.date, 'localtime') as local_date
            FROM sales s
            LEFT JOIN customers c ON s.customer_id = c.id
            ORDER BY s.date DESC
        ''')
        sales = cursor.fetchall()
    return render_template('sales/list.html', sales=sales)

# In app.py

@app.route('/api/search_medicines')
def search_medicines():
    """API endpoint to search for available medicines."""
    query = request.args.get('query', '').strip()
    medicines_list = []

    if len(query) < 1: # Optional: require minimum query length
        return jsonify(medicines_list)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Search by name, ensure stock > 0 and not expired
            # MODIFICATION: Added batch_number to the SELECT statement
            cursor.execute('''
                SELECT id, name, batch_number, price, quantity
                FROM medicines
                WHERE name LIKE ?
                  AND quantity > 0
                  AND expiry_date > date('now')
                ORDER BY name, batch_number
                LIMIT 10
            ''', (f'%{query}%',))
            medicines = cursor.fetchall()
            # Convert Row objects to dictionaries for JSON serialization
            medicines_list = [dict(row) for row in medicines]
        return jsonify(medicines_list)
    except Exception as e:
        app.logger.error(f"Error searching medicines: {e}")
        return jsonify({"error": "Failed to search medicines"}), 500
    
@app.route('/api/search_customers')
def search_customers():
    """API endpoint to search for customers."""
    query = request.args.get('query', '').strip()
    customers_list = []

    if len(query) < 1: # Don't search on empty query
        return jsonify(customers_list)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Search by name or phone number
            cursor.execute('''
                SELECT id, name, phone
                FROM customers
                WHERE name LIKE ? OR phone LIKE ?
                ORDER BY name
                LIMIT 10
            ''', (f'%{query}%', f'%{query}%'))
            customers = cursor.fetchall()
            customers_list = [dict(row) for row in customers]
        return jsonify(customers_list)
    except Exception as e:
        app.logger.error(f"Error searching customers: {e}")
        return jsonify({"error": "Failed to search customers"}), 500

# --- Modification needed in new_sale ---
@app.route('/sales/new', methods=['GET', 'POST'])
def new_sale():
    if request.method == 'POST':
        try:
            # --- Get customer_id (modified) ---
            # Get from the hidden input field populated by JS
            customer_id_str = request.form.get('selected_customer_id')
            customer_id = int(customer_id_str) if customer_id_str else None # None for Walk-in
            # --- End customer_id modification ---

            payment_method = request.form['payment_method']
            discount = float(request.form.get('discount', 0))

            # Get item data (remains the same as previous step)
            medicine_ids = request.form.getlist('medicine_ids[]')
            quantities = request.form.getlist('quantities[]')
            prices = request.form.getlist('prices[]')

            if not medicine_ids:
                flash('No items added to the sale.', 'danger')
                # Need to pass customers=None or remove the argument if template is adjusted
                return redirect(url_for('new_sale'))


            if len(medicine_ids) != len(quantities) or len(medicine_ids) != len(prices):
                 flash('Item data mismatch. Please try again.', 'danger')
                 return redirect(url_for('new_sale'))

            calculated_subtotal = 0
            items_data = []
            for i in range(len(medicine_ids)):
                 try:
                     med_id = int(medicine_ids[i])
                     qty = int(quantities[i])
                     price = float(prices[i])
                     if qty <= 0:
                         raise ValueError("Quantity must be positive")
                     calculated_subtotal += qty * price
                     items_data.append({'id': med_id, 'qty': qty, 'price': price})
                 except (ValueError, TypeError) as e:
                     flash(f'Invalid item data detected: {e}. Please try again.', 'danger')
                     return redirect(url_for('new_sale'))

            total_amount = calculated_subtotal - discount

            if total_amount < 0:
                 flash('Total amount cannot be negative after discount.', 'danger')
                 return redirect(url_for('new_sale'))


            # --- Start Transaction ---
            with get_db_cursor() as cursor:
                # Generate invoice number
                invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{random.randint(1000,9999)}"

                # Create sale record (uses the potentially None customer_id)
                cursor.execute('''
                    INSERT INTO sales (invoice_number, customer_id, total_amount, discount, payment_method)
                    VALUES (?, ?, ?, ?, ?)
                ''', (invoice_number, customer_id, total_amount, discount, payment_method))
                sale_id = cursor.lastrowid

                # Process sale items with stock validation (remains the same)
                for item in items_data:
                    medicine_id = item['id']
                    quantity = item['qty']
                    price = item['price'] # Use price submitted by form

                    cursor.execute('SELECT name, quantity, expiry_date FROM medicines WHERE id = ?', (medicine_id,))
                    medicine = cursor.fetchone()
                    if not medicine:
                        raise Exception(f"Medicine with ID {medicine_id} not found.")
                    if quantity > medicine['quantity']:
                         raise Exception(f"Insufficient stock for {medicine['name']} (needed: {quantity}, available: {medicine['quantity']}).")
                    if datetime.strptime(medicine['expiry_date'], '%Y-%m-%d').date() < datetime.utcnow().date():
                         raise Exception(f"{medicine['name']} has expired.")

                    cursor.execute('INSERT INTO sale_items (sale_id, medicine_id, quantity, price) VALUES (?, ?, ?, ?)',
                                   (sale_id, medicine_id, quantity, price))
                    cursor.execute('UPDATE medicines SET quantity = quantity - ? WHERE id = ?', (quantity, medicine_id))

            # --- Transaction Committed ---
            flash('Sale recorded successfully!', 'success')
            return redirect(url_for('view_invoice', invoice_number=invoice_number))

        except Exception as e:
            # Transaction automatically rolled back by context manager
            flash(f'Error recording sale: {str(e)}', 'danger')
            app.logger.error(f'Sale processing error: {str(e)}', exc_info=True)
            return redirect(url_for('new_sale')) # Redirect back to the form

    # GET request - show form
    # No longer need to fetch all customers here
    return render_template('sales/new.html',
                         current_time=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))

# In app.py

@app.route('/sales/<invoice_number>')
def view_invoice(invoice_number):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
                SELECT s.*, c.name as customer_name,
                       c.phone as customer_phone
                FROM sales s
                LEFT JOIN customers c ON s.customer_id = c.id
                WHERE s.invoice_number = ?
            ''', (invoice_number,))
        sale = cursor.fetchone()

        if not sale:
            flash('Invoice not found. Please check the invoice number.', 'danger')
            return redirect(url_for('sales'))

        # MODIFICATION: Added m.batch_number to the SELECT statement
        cursor.execute('''
                SELECT si.*, m.name as medicine_name, m.batch_number
                FROM sale_items si
                JOIN medicines m ON si.medicine_id = m.id
                WHERE si.sale_id = ?
            ''', (sale['id'],))
        items = cursor.fetchall()

    return render_template('sales/invoice.html', sale=sale, items=items)

@app.route('/sales/print/<invoice_number>')
def print_invoice(invoice_number):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
                SELECT s.*, c.name as customer_name,
                       c.phone as customer_phone
                FROM sales s
                LEFT JOIN customers c ON s.customer_id = c.id
                WHERE s.invoice_number = ?
            ''', (invoice_number,))
        sale = cursor.fetchone()

        if not sale:
            flash('Invoice not found', 'danger')
            return redirect(url_for('sales'))

        # MODIFICATION: Added m.batch_number to the SELECT statement
        cursor.execute('''
                SELECT si.*, m.name as medicine_name, m.batch_number
                FROM sale_items si
                JOIN medicines m ON si.medicine_id = m.id
                WHERE si.sale_id = ?
            ''', (sale['id'],))
        items = cursor.fetchall()

    rendered = render_template('sales/print_invoice.html', sale=sale, items=items)

    # Generate PDF with WeasyPrint
    pdf = HTML(string=rendered).write_pdf()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=invoice_{invoice_number}.pdf'
    return response

# Reports
@app.route('/reports/sales')
def sales_reports():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Daily sales (last 7 days)
        cursor.execute('''
            SELECT date(date) as day, SUM(total_amount) as total
            FROM sales
            GROUP BY day
            ORDER BY day DESC
            LIMIT 7
        ''')
        daily_sales = cursor.fetchall()
        
        # Monthly sales
        cursor.execute('''
            SELECT strftime("%Y-%m", date) as month, SUM(total_amount) as total
            FROM sales
            GROUP BY month
            ORDER BY month DESC
        ''')
        monthly_sales = cursor.fetchall()
        
        # Top medicines
        cursor.execute('''
            SELECT m.name, SUM(si.quantity) as total_quantity, SUM(si.quantity * si.price) as total_sales
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.id
            GROUP BY m.name
            ORDER BY total_quantity DESC
            LIMIT 10
        ''')
        top_medicines = cursor.fetchall()
        
        # Profit calculation
        cursor.execute('''
            SELECT date(date) as day, 
                   SUM((si.price - m.cost_price) * si.quantity) as profit
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.id
            JOIN sales s ON si.sale_id = s.id
            GROUP BY day
            ORDER BY day DESC
            LIMIT 7
        ''')
        profit_data = cursor.fetchall()
    
    return render_template('reports/sales.html',
                         daily_sales=daily_sales,
                         monthly_sales=monthly_sales,
                         top_medicines=top_medicines,
                         profit_data=profit_data)


@app.route('/check_times')
def check_times():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get database times
        cursor.execute('''
            SELECT 
                datetime('now') as db_utc,
                datetime('now', 'localtime') as db_local,
                time('now') as db_time,
                date('now') as db_date,
                strftime('%s', 'now') as unix_timestamp
        ''')
        db_times = cursor.fetchone()
        
        # Get most recent sale time
        cursor.execute('SELECT date FROM sales ORDER BY date DESC LIMIT 1')
        last_sale = cursor.fetchone()
        
        # Get Python times
        py_utc = datetime.utcnow()
        py_local = datetime.now()
        
        return render_template('time_check.html',
            db_utc=db_times['db_utc'],
            db_local=db_times['db_local'],
            db_time=db_times['db_time'],
            db_date=db_times['db_date'],
            unix_timestamp=db_times['unix_timestamp'],
            last_sale=last_sale['date'] if last_sale else 'No sales yet',
            py_utc=py_utc.strftime('%Y-%m-%d %H:%M:%S'),
            py_local=py_local.strftime('%Y-%m-%d %H:%M:%S'),
            py_utc_raw=str(py_utc),
            py_local_raw=str(py_local),
            timezone=str(LOCAL_TIMEZONE)
        )
if __name__ == '__main__':
    multiprocessing.freeze_support()
    app.run(debug=False)