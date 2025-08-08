from flask import Flask, render_template, request, redirect, url_for, flash, make_response, jsonify
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId
from bson.regex import Regex
from io import BytesIO
import os
import random
import pytz

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

client = MongoClient(os.environ.get("MONGODB_URI", ""))
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
    for med in medicines:
        units_per_strip = med.get('units_per_strip', 1) or 1
        total_units = med.get('quantity', 0) or 0

        strips = total_units // units_per_strip
        loose_units = total_units % units_per_strip

        med['stock_display'] = f"{strips} strips & {loose_units} units"
    return render_template('inventory/list.html', medicines=medicines)

@app.route('/inventory/add', methods=['GET', 'POST'])
def add_medicine():
    if request.method == 'POST':
        try:
            add_by = request.form.get('add_by')  # "strip" or "unit"
            name = request.form['name'].strip()
            batch_number = request.form['batch_number'].strip()
            supplier = request.form.get('supplier', '').strip()
            company = request.form.get('company', '').strip()
            mfg_date = datetime.strptime(request.form['mfg_date'], '%Y-%m-%d')
            expiry_date = datetime.strptime(request.form['expiry_date'], '%Y-%m-%d')
            general = False

            # Fields that will always exist in DB
            units_per_strip = None
            price_per_strip = None
            price_per_unit = None
            total_units = 0

            if add_by == 'strip':
                # Expect strips_count, units_per_strip and price_per_strip
                strips_count = float(request.form.get('strips_count', '0') or 0)   # allow decimals like 1.5 if user enters mistakenly - but we'll convert only for storage as integer units
                units_per_strip = int(request.form.get('units_per_strip', '0') or 0)
                price_per_strip = float(request.form.get('price_per_strip', '0') or 0)

                if units_per_strip <= 0:
                    flash('Units per strip must be a positive integer.', 'danger')
                    return render_template('inventory/add.html')

                if strips_count < 0:
                    flash('Number of strips cannot be negative.', 'danger')
                    return render_template('inventory/add.html')

                # Calculate total units (allow non-integer strips like 1.5 -> multiply and round to nearest unit)
                total_units = int(round(strips_count * units_per_strip))

                # price_per_unit computed but user can override in form; prefer explicit per-unit if provided
                price_per_unit_input = request.form.get('price_per_unit', '').strip()
                if price_per_unit_input != '':
                    price_per_unit = float(price_per_unit_input)
                else:
                    # avoid division by zero (units_per_strip > 0 ensured above)
                    price_per_unit = price_per_strip / units_per_strip if price_per_strip is not None else 0.0

            else:  # add_by == 'unit' or default
                price_per_unit = float(request.form.get('price_per_unit', '0') or 0)
                units_count = int(request.form.get('quantity', '0') or 0)
                if units_count < 0:
                    flash('Quantity cannot be negative.', 'danger')
                    return render_template('inventory/add.html')
                total_units = units_count
                # price_per_strip remains None (unless user later sets it)

            # Common numeric fields: cost_price (rate) stored per unit (user provides)
            cost_price = float(request.form.get('cost_price', '0') or 0)

            # Check duplicate batch
            if db.medicines.find_one({"batch_number": batch_number}):
                flash('Batch number already exists!', 'danger')
                return render_template('inventory/add.html')

            med = {
                "name": name,
                "batch_number": batch_number,
                "quantity": total_units,
                "price_per_unit": round(float(price_per_unit or 0), 2),
                "price_per_strip": round(float(price_per_strip) if price_per_strip is not None else None, 2) if price_per_strip is not None else None,
                "units_per_strip": int(units_per_strip) if units_per_strip is not None else None,
                "cost_price_per_unit": round(float(cost_price or 0), 2),
                "supplier": supplier,
                "company": company,
                "mfg_date": mfg_date,
                "expiry_date": expiry_date,
                "general": general
            }

            db.medicines.insert_one(med)
            flash('Medicine added successfully!', 'success')
            return redirect(url_for('inventory'))

        except Exception as e:
            app.logger.exception("Error adding medicine")
            flash(f'Error: {str(e)}', 'danger')

    # GET request
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

    return render_template('general/edit.html', medicine=item)

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
                "address": request.form.get('address'),
            }
            db.customers.insert_one(customer)
            flash('Customer added successfully!', 'success')
            return redirect(url_for('customers'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    return render_template('customers/add.html')

@app.route('/customers/edit/<id>', methods=['GET', 'POST'])
def edit_customer(id):
    customer = db.customers.find_one({"_id": ObjectId(id)})
    if not customer:
        flash('Customer not found!', 'danger')
        return redirect(url_for('customers'))

    if request.method == 'POST':
        try:
            update = {
                "name": request.form['name'],
                "phone": request.form['phone'],
                "address": request.form.get('address')
            }
            db.customers.update_one({"_id": ObjectId(id)}, {"$set": update})
            flash('Customer updated successfully!', 'success')
            return redirect(url_for('customers'))
        except Exception as e:
            flash(f'Error updating: {str(e)}', 'danger')

    return render_template('customers/edit.html', customer=customer)

@app.route('/customers/view/<id>')
def view_customer(id):
    customer = db.customers.find_one({"_id": ObjectId(id)})
    if not customer:
        flash('Customer not found!', 'danger')
        return redirect(url_for('customers'))

    # Fetch sales related to this customer
    sales = list(db.sales.find({"customer_id": ObjectId(id)}).sort("date", DESCENDING))

    # Convert ObjectId to string for template usage
    for sale in sales:
        sale["_id"] = str(sale["_id"])
        sale["date"] = sale["date"].strftime('%Y-%m-%d') if isinstance(sale["date"], datetime) else sale["date"]

    return render_template('customers/view.html', customer=customer, sales=sales)


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
                "price_per_unit": 1,
                "price_per_strip": 1,
                "units_per_strip": 1,
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
            strips_list = request.form.getlist('strips[]')
            units_list = request.form.getlist('units[]')
            prices = request.form.getlist('prices[]')

            if not medicine_ids or not prices:
                return jsonify({"error": "No medicines selected"}), 400

            strips_list = [int(s or 0) for s in strips_list]
            units_list = [int(u or 0) for u in units_list]
            prices = [float(p) for p in prices]

            items = []
            total_amount = 0

            for med_id, strips, units, price in zip(medicine_ids, strips_list, units_list, prices):
                med = db.medicines.find_one({"_id": ObjectId(med_id)})
                if not med:
                    continue
                print("data:", med_id, strips, units, price)

                units_per_strip = med.get("units_per_strip", 1)
                total_units = strips * units_per_strip + units

                # Calculate total price based on units
                total_amount += strips * med.get("price_per_strip", 0) + units * med.get("price_per_unit", 0)

                # Store in items
                items.append({
                    "medicine_id": ObjectId(med_id),
                    "strips": strips,
                    "units": units,
                    "total_units": total_units,
                    "price": price
                })

                # Deduct stock in units
                db.medicines.update_one(
                    {"_id": ObjectId(med_id)},
                    {"$inc": {"quantity": -total_units}}
                )

            # Apply discount
            total_amount -= discount

            # Generate invoice number
            last_sale = db.sales.find_one(sort=[("invoice_number", -1)])
            if last_sale and "invoice_number" in last_sale:
                invoice_number = last_sale["invoice_number"] + 1
            else:
                invoice_number = 1001

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
        sale["customer_address"] = customer.get("address", "") if customer else ""
    else:
        sale["customer_name"] = "Walk-in Customer"
        sale["customer_phone"] = ""
        sale["customer_address"] = ""

    # Get medicine details with strips & units
    items_with_details = []
    for item in sale.get("items", []):
        med = db.medicines.find_one({"_id": ObjectId(item["medicine_id"])})
        if med:
            # units_per_strip = med.get("units_per_strip", 1) or 1  # avoid division by zero
            strips = item['strips']
            units = item['units']

            items_with_details.append({
                "medicine_name": med["name"],
                "batch_number": med.get("batch_number", ""),
                "quantity": f"{strips} strips & {units} units",
                "ps": med.get('price_per_strip', 0),
                "pu": med.get('price_per_unit', 0),
                "total": strips * med.get("price_per_strip", 0) + units * med.get("price_per_unit", 0),
            })

    return render_template(
        'sales/invoice.html',
        sale=sale,
        items=items_with_details,
        current_time=datetime.now()
    )
@app.route('/sales/print/<sale_id>')
def print_invoice_html(sale_id):
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
        sale["customer_address"] = customer.get("address", "") if customer else ""
    else:
        sale["customer_name"] = "Walk-in Customer"
        sale["customer_phone"] = ""
        sale["customer_address"] = ""

    # Get medicine details with strips & units
    items_with_details = []
    for item in sale.get("items", []):
        med = db.medicines.find_one({"_id": ObjectId(item["medicine_id"])})
        if med:
            # units_per_strip = med.get("units_per_strip", 1) or 1  # avoid division by zero
            strips = item['strips']
            units = item['units']

            items_with_details.append({
                "medicine_name": med["name"],
                "batch_number": med.get("batch_number", ""),
                "quantity": f"{strips} strips & {units} units",
                "ps": med.get('price_per_strip', 0),
                "pu": med.get('price_per_unit', 0),
                "total": strips * med.get("price_per_strip", 0) + units * med.get("price_per_unit", 0),
            })

    return render_template(
        'sales/invoice_print.html',
        sale=sale,
        items=items_with_details,
        current_time=datetime.now()
    )

if __name__ == '__main__':
    app.run(debug=True)
