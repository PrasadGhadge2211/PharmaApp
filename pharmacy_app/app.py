from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId
from bson.regex import Regex
from io import BytesIO
import os
import random
import pytz
import certifi
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

FONT_PATH = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
pdfmetrics.registerFont(TTFont('DejaVuSans', FONT_PATH))

ca = certifi.where()
client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=ca)
db = client['pharmacy_db']

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
    today_utc = datetime.utcnow()
    expiry_threshold = today_utc + timedelta(days=30)

    # Convert expiry_date from MongoDB to Python datetime if stored as ISODate
    expiring_meds = []
    for med in db.medicines.find({"expiry_date": {"$lte": expiry_threshold}}).sort("expiry_date"):
        med['expiry_date'] = med['expiry_date'].strftime('%Y-%m-%d') if isinstance(med['expiry_date'], datetime) else med['expiry_date']
        expiring_meds.append(med)

    low_stock = list(db.medicines.find({"quantity": {"$lt": 10}}))

    # Prepare recent sales data
    recent_sales = []
    for sale in db.sales.find().sort("date", DESCENDING).limit(5):
        sale['invoice_number'] = sale.get('invoice_number', str(sale['_id'])[-6:])  # fallback if invoice_number not set
        sale['date'] = sale['date'] if isinstance(sale['date'], datetime) else datetime.fromtimestamp(sale['date'] / 1000)
        sale['customer_name'] = sale.get('customer_name', 'Walk-in')
        sale['total_amount'] = float(sale['total_amount'])
        recent_sales.append(sale)

    return render_template(
        'dashboard.html',
        expiring_meds=expiring_meds,
        low_stock=low_stock,
        recent_sales=recent_sales,
        datetime=datetime,
        now=today_utc
    )


@app.route('/inventory')
def inventory():
    search_query = request.args.get('search', '').strip()
    query = {"general": False}
    if search_query:
        query["$or"] = [
            {"name": {"$regex": search_query, "$options": "i"}},
            {"batch_number": {"$regex": search_query, "$options": "i"}},
            {"supplier": {"$regex": search_query, "$options": "i"}}
        ]
    medicines = list(db.medicines.find(query).sort("name", 1))
    for med in medicines:
        if isinstance(med.get('mfg_date'), datetime):
            med['mfg_date'] = med['mfg_date'].strftime('%Y-%m-%d')
        if isinstance(med.get('expiry_date'), datetime):
            med['expiry_date'] = med['expiry_date'].strftime('%Y-%m-%d')
    return render_template('inventory/list.html', medicines=medicines)

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_medicine():
    if request.method == 'POST':
        try:
            med = {
                "name": request.form['name'],
                "batch_number": request.form['batch_number'],
                "quantity": int(request.form['quantity']),
                "price": float(request.form['price']),
                "cost_price": float(request.form['cost_price']),
                "supplier": request.form['supplier'],
                "company": request.form['company'],
                "mfg_date": datetime.strptime(request.form['mfg_date'], '%Y-%m-%d'),
                "expiry_date": datetime.strptime(request.form['expiry_date'], '%Y-%m-%d'),
                "general": False
            }
            if db.medicines.find_one({"batch_number": med["batch_number"]}):
                flash('Batch number already exists!', 'danger')
            else:
                db.medicines.insert_one(med)
                flash('Medicine added successfully!', 'success')
                return redirect(url_for('inventory'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    return render_template('inventory/add.html')

@app.route('/inventory/edit/<id>', methods=['GET', 'POST'])
def edit_medicine(id):
    medicine = db.medicines.find_one({"_id": ObjectId(id)})
    if not medicine:
        flash('Medicine not found!', 'danger')
        return redirect(url_for('inventory'))
    if request.method == 'POST':
        try:
            update = {
                "name": request.form['name'],
                "batch_number": request.form['batch_number'],
                "quantity": int(request.form['quantity']),
                "price": float(request.form['price']),
                "cost_price": float(request.form['cost_price']),
                "supplier": request.form['supplier'],
                "company": request.form['company'],
                "mfg_date": datetime.strptime(request.form['mfg_date'], '%Y-%m-%d'),
                "expiry_date": datetime.strptime(request.form['expiry_date'], '%Y-%m-%d')
            }
            db.medicines.update_one({"_id": ObjectId(id)}, {"$set": update})
            flash('Medicine updated successfully!', 'success')
            return redirect(url_for('inventory'))
        except Exception as e:
            flash(f'Error updating: {str(e)}', 'danger')
    return render_template('inventory/edit.html', medicine=medicine)

@app.route('/inventory/delete/<id>')
def delete_medicine(id):
    try:
        db.medicines.delete_one({"_id": ObjectId(id)})
        flash('Medicine deleted.', 'success')
    except Exception as e:
        flash(f'Failed to delete: {str(e)}', 'danger')
    return redirect(url_for('inventory'))

# General Inventory
@app.route('/general')
def general_inventory():
    search_query = request.args.get('search', '').strip()
    query = {'general': True}

    if search_query:
        query = {
            '$and': [
                {'general': True},
                {
                    '$or': [
                        {'name': {'$regex': search_query, '$options': 'i'}},
                        {'batch_number': {'$regex': search_query, '$options': 'i'}},
                        {'supplier': {'$regex': search_query, '$options': 'i'}}
                    ]
                }
            ]
        }

    medicines = list(db.medicines.find(query).sort('name', 1))

    # Format MongoDB date fields for template display
    for med in medicines:
        if isinstance(med.get('mfg_date'), datetime):
            med['mfg_date'] = med['mfg_date'].strftime('%Y-%m-%d')
        if isinstance(med.get('expiry_date'), datetime):
            med['expiry_date'] = med['expiry_date'].strftime('%Y-%m-%d')

    return render_template('general/list.html', medicines=medicines)

@app.route('/general/add', methods=['GET', 'POST'])
def add_general():
    if request.method == 'POST':
        try:
            item = {
                "name": request.form['name'],
                "batch_number": request.form['batch_number'],
                "quantity": int(request.form['quantity']),
                "price": float(request.form['price']),
                "supplier": request.form['supplier'],
                "company": request.form['company'],
                "mfg_date": datetime.strptime(request.form['mfg_date'], '%Y-%m-%d'),
                "expiry_date": datetime.strptime(request.form['expiry_date'], '%Y-%m-%d'),
                "general": True
            }
            db.medicines.insert_one(item)
            flash('Item added.', 'success')
            return redirect(url_for('general_inventory'))
        except Exception as e:
            flash(f'Error adding item: {str(e)}', 'danger')
    return render_template('general/add.html')

@app.route('/general/edit/<id>', methods=['GET', 'POST'])
def edit_general(id):
    item = db.medicines.find_one({"_id": ObjectId(id)})
    if not item:
        flash('Item not found!', 'danger')
        return redirect(url_for('general_inventory'))

    if request.method == 'POST':
        try:
            update = {
                "name": request.form['name'],
                "batch_number": request.form['batch_number'],
                "quantity": int(request.form['quantity']),
                "price": float(request.form['price']),
                "supplier": request.form['supplier'],
                "company": request.form['company'],
                "mfg_date": datetime.strptime(request.form['mfg_date'], '%Y-%m-%d'),
                "expiry_date": datetime.strptime(request.form['expiry_date'], '%Y-%m-%d')
            }
            db.medicines.update_one({"_id": ObjectId(id)}, {"$set": update})
            flash('Item updated successfully!', 'success')
            return redirect(url_for('general_inventory'))
        except Exception as e:
            flash(f'Error updating: {str(e)}', 'danger')

    return render_template('general/edit.html', item=item)

@app.route('/general/delete/<id>')
def delete_general(id):
    try:
        db.medicines.delete_one({"_id": ObjectId(id)})
        flash('Item deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting item: {str(e)}', 'danger')
    return redirect(url_for('general_inventory'))

# Customers
@app.route('/customers')
def customers():
    all_customers = list(db.customers.find().sort("name"))
    return render_template('customers/list.html', customers=all_customers)

@app.route('/customers/add', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        try:
            customer = {
                "name": request.form['name'],
                "phone": request.form['phone'],
                "email": request.form['email']
            }
            db.customers.insert_one(customer)
            flash('Customer added successfully!', 'success')
            return redirect(url_for('customers'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    return render_template('customers/add.html')

@app.route('/customers/delete/<id>')
def delete_customer(id):
    try:
        db.customers.delete_one({"_id": ObjectId(id)})
        flash('Customer deleted.', 'success')
    except Exception as e:
        flash(f'Failed to delete: {str(e)}', 'danger')
    return redirect(url_for('customers'))

@app.route('/api/search_medicines')
def search_medicines():
    """API endpoint to search for available medicines."""
    query = request.args.get('query', '').strip()
    medicines_list = []

    if len(query) < 1:  # Optional: require minimum query length
        return jsonify(medicines_list)

    try:
        # Search by name, ensure stock > 0 and not expired
        medicines = db.medicines.find(
            {
                "name": {"$regex": query, "$options": "i"},
                "quantity": {"$gt": 0},
                "expiry_date": {"$gt": datetime.now()}
            },
            {
                "_id": 1,
                "name": 1,
                "batch_number": 1,
                "price": 1,
                "quantity": 1
            }
        ).sort([("name", 1), ("batch_number", 1)]).limit(10)

        # Convert ObjectId to string for JSON serialization
        for med in medicines:
            med["_id"] = str(med["_id"])
            medicines_list.append(med)

        return jsonify(medicines_list)
    except Exception as e:
        app.logger.error(f"Error searching medicines: {e}")
        return jsonify({"error": "Failed to search medicines"}), 500

@app.route('/api/search_customers')
def search_customers():
    """API endpoint to search for customers."""
    query = request.args.get('query', '').strip()
    customers_list = []

    if len(query) < 1:  # Don't search on empty query
        return jsonify(customers_list)

    try:
        customers = db.customers.find(
            {
                "$or": [
                    {"name": {"$regex": query, "$options": "i"}},
                    {"phone": {"$regex": query, "$options": "i"}}
                ]
            },
            {
                "_id": 1,
                "name": 1,
                "phone": 1
            }
        ).sort("name", 1).limit(10)

        for cust in customers:
            cust["_id"] = str(cust["_id"])
            customers_list.append(cust)

        return jsonify(customers_list)
    except Exception as e:
        app.logger.error(f"Error searching customers: {e}")
        return jsonify({"error": "Failed to search customers"}), 500
    

@app.route('/sales')
def sales():
    sales_list = []
    for s in db.sales.find().sort("date", -1):
        # Attach customer name (if exists)
        if s.get("customer_id"):
            customer = db.customers.find_one({"_id": ObjectId(s["customer_id"])})
            s["customer_name"] = customer["name"] if customer else "Walk-in Customer"
            s["customer_phone"] = customer.get("phone", "") if customer else ""
        else:
            s["customer_name"] = "Walk-in Customer"
            s["customer_phone"] = ""

        # Convert ObjectId to string for template usage
        s["_id"] = str(s["_id"])
        sales_list.append(s)

    return render_template('sales/list.html', sales=sales_list)

# Sales
@app.route('/sales/new', methods=['GET', 'POST'])
def new_sale():
    customers = list(db.customers.find())
    medicines = list(db.medicines.find({"quantity": {"$gt": 0}}))

    if request.method == 'POST':
        try:
            customer_id = request.form.get('customer_id')
            payment_method = request.form.get('payment_method')
            discount = float(request.form.get('discount', 0) or 0)

            medicine_ids = request.form.getlist('medicine_ids[]')
            quantities = request.form.getlist('quantities[]')
            prices = request.form.getlist('prices[]')

            if not medicine_ids or not quantities or not prices:
                return jsonify({"error": "No medicines selected"}), 400

            # Convert values to correct types
            quantities = [int(q) for q in quantities]
            prices = [float(p) for p in prices]

            # Build sale items list
            items = []
            total_amount = 0
            for med_id, qty, price in zip(medicine_ids, quantities, prices):
                total_amount += qty * price
                items.append({
                    "medicine_id": ObjectId(med_id),
                    "quantity": qty,
                    "price": price
                })

                # Update medicine stock
                db.medicines.update_one(
                    {"_id": ObjectId(med_id)},
                    {"$inc": {"quantity": -qty}}
                )

            # Apply discount
            total_amount -= discount

            # Generate invoice number
            last_sale = db.sales.find_one(sort=[("invoice_number", -1)])
            if last_sale and "invoice_number" in last_sale:
                invoice_number = last_sale["invoice_number"] + 1
            else:
                invoice_number = 1001  # starting point

            # Insert sale record
            sale_doc = {
                "invoice_number": invoice_number,
                "customer_id": ObjectId(customer_id) if customer_id else None,
                "payment_method": payment_method,
                "discount": discount,
                "total_amount": total_amount,
                "items": items,
                "date": datetime.utcnow()
            }
            db.sales.insert_one(sale_doc)

            flash(f"Sale recorded successfully! Invoice #{invoice_number}", "success")
            return redirect(url_for('sales'))

        except Exception as e:
            app.logger.error(f"Error processing sale: {e}")
            return jsonify({"error": "Failed to process sale"}), 500

    return render_template('sales/new.html', customers=customers, medicines=medicines)

@app.route('/sales/<sale_id>')
def view_invoice(sale_id):
    try:
        sale = db.sales.find_one({"_id": ObjectId(sale_id)})
    except:
        flash("Invalid sale ID.", "danger")
        return redirect(url_for('sales'))

    if not sale:
        flash('Invoice not found.', 'danger')
        return redirect(url_for('sales'))

    # Attach customer info
    if sale.get("customer_id"):
        customer = db.customers.find_one({"_id": ObjectId(sale["customer_id"])})
        sale["customer_name"] = customer["name"] if customer else "Walk-in Customer"
        sale["customer_phone"] = customer.get("phone", "") if customer else ""
    else:
        sale["customer_name"] = "Walk-in Customer"
        sale["customer_phone"] = ""

    # Get medicine details
    items_with_details = []
    for item in sale.get("items", []):
        med = db.medicines.find_one({"_id": ObjectId(item["medicine_id"])})
        if med:
            items_with_details.append({
                "medicine_name": med["name"],
                "batch_number": med.get("batch_number", ""),
                "quantity": item["quantity"],
                "price": item["price"]
            })

    return render_template('sales/invoice.html', sale=sale, items=items_with_details)


@app.route('/sales/print/<sale_id>')
def print_invoice(sale_id):
    sale = db.sales.find_one({"_id": ObjectId(sale_id)})
    if not sale:
        flash('Invoice not found', 'danger')
        return redirect(url_for('sales'))

    # Customer info
    customer = None
    if sale.get('customer_id'):
        customer = db.customers.find_one({"_id": ObjectId(sale['customer_id'])})

    # Shop details (From:)
    shop_info = [
        "Sanskar Medical and Gen.St",
        "Shop No.35, Pratibha Sa",
        "Ghadge Nagar, Nashik Road, Nashik",
        "Phone: 94229 90414 / 80070 74991",
        "DL.NO: 20-433500 / 21-433501",
        "GSTIN: "
    ]

    # Customer details (To:)
    customer_name = customer['name'] if customer else "Walk-in Customer"
    customer_lines = [customer_name]
    if customer and customer.get("phone"):
        customer_lines.append(f"Phone: {customer['phone']}")

    # Items table
    items_data = [["#", "Item", "Batch No.", "Qty", "Unit Price (₹)", "Total (₹)"]]
    subtotal = 0
    for idx, item in enumerate(sale.get("items", []), start=1):
        med = db.medicines.find_one({"_id": ObjectId(item["medicine_id"])})
        name = med["name"] if med else "Unknown"
        batch = med.get("batch_number", "") if med else ""
        qty = item.get("quantity", 0)
        price = item.get("price", 0)
        total = qty * price
        subtotal += total
        items_data.append([idx, name, batch, qty, f"₹{price:.2f}", f"₹{total:.2f}"])

    discount = sale.get("discount", 0)
    total_amount = subtotal - discount

    # PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=20, bottomMargin=20)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title_style = ParagraphStyle('title', parent=styles['Title'], alignment=1, fontSize=16, fontName='DejaVuSans')
    elements.append(Paragraph(f"Invoice #{sale.get('invoice_number', '')}", title_style))
    elements.append(Spacer(1, 0.2 * inch))

    # From / To
    from_to_data = [
        [
            Paragraph("<b>From:</b><br/>" + "<br/>".join(shop_info), ParagraphStyle('shop', fontName='DejaVuSans', fontSize=10)),
            Paragraph("<b>To:</b><br/>" + "<br/>".join(customer_lines), ParagraphStyle('cust', fontName='DejaVuSans', fontSize=10))
        ]
    ]
    from_to_table = Table(from_to_data, colWidths=[3.5 * inch, 3.5 * inch])
    from_to_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    elements.append(from_to_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Invoice details
    details_data = [
        ["Invoice #:", sale.get('invoice_number', '')],
        ["Date:", sale.get('date', datetime.utcnow()).strftime('%Y-%m-%d %H:%M:%S')],
        ["Payment Method:", sale.get('payment_method', 'Cash')]
    ]
    details_table = Table(details_data, colWidths=[1.5 * inch, 5.5 * inch])
    details_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans')
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Items table
    table = Table(items_data, colWidths=[0.5*inch, 2.3*inch, 1.3*inch, 0.6*inch, 1.1*inch, 1.1*inch])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (3, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.3 * inch))

    # Totals
    totals_data = [
        ["Subtotal:", f"₹{subtotal:.2f}"],
        ["Discount:", f"₹{discount:.2f}"],
        ["Total Amount:", f"₹{total_amount:.2f}"]
    ]
    totals_table = Table(totals_data, colWidths=[5.9*inch, 1.1*inch])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
        ('FONTSIZE', (0, 0), (-1, -1), 10)
    ]))
    elements.append(totals_table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'inline; filename=invoice_{sale_id}.pdf'
    return response

if __name__ == '__main__':
    app.run(debug=True)
