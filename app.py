from flask import Flask, request, render_template, redirect, session, flash, url_for, send_file
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import sqlite3
import razorpay
import config
import random
import bcrypt
import os
import io
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

app = Flask(__name__)

app.secret_key = config.secret_key

# ------------------- MAIL CONFIGURATION -------------------
app.config['MAIL_SERVER'] = config.MAIL_SERVER
app.config['MAIL_PORT'] = config.MAIL_PORT
app.config['MAIL_USE_TLS'] = config.MAIL_USE_TLS
app.config['MAIL_USERNAME'] = config.MAIL_USERNAME
app.config['MAIL_PASSWORD'] = config.MAIL_PASSWORD

# ------------------- IMAGE UPLOAD PATHS -------------------
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'product_images')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ADMIN_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'admin_profiles')
app.config['ADMIN_UPLOAD_FOLDER'] = ADMIN_UPLOAD_FOLDER
os.makedirs(app.config['ADMIN_UPLOAD_FOLDER'], exist_ok=True)

USER_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'user_profiles')
app.config['USER_UPLOAD_FOLDER'] = USER_UPLOAD_FOLDER
os.makedirs(app.config['USER_UPLOAD_FOLDER'], exist_ok=True)

# ------------------- RAZORPAY CLIENT (DAY 12) -------------------
razorpay_client = razorpay.Client(
    auth=(
        getattr(config, 'RAZORPAY_KEY_ID', 'rzp_test_TLeM6Ox9b7K9Dp'),
        getattr(config, 'RAZORPAY_KEY_SECRET', 'dU4b4haEuqjJU1pc61pvF0UE')
    )
)

mail = Mail(app)



# ------------------- DATABASE CONNECTION & INIT -------------------
def get_connection():
    conn = sqlite3.connect("smartcart.db")
    conn.row_factory = sqlite3.Row
    return conn

# Alias for backward compatibility
get_db_connection = get_connection

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        with open("schema.sql", "r", encoding="utf-8") as file:
            schema = file.read()

        cursor.executescript(schema)

        conn.commit()
        cursor.close()
        conn.close()

        print("SQLite database initialized successfully.")

    except Exception as e:
        print(f"Database initialization warning: {e}")

init_db()


# ------------------- INVOICE PDF GENERATOR (REPORTLAB) -------------------
def generate_invoice_pdf(order, items, user):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()

    brand_style = ParagraphStyle(
        'BrandTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e40af')
    )
    right_text = ParagraphStyle(
        'RightText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        alignment=2,
        textColor=colors.HexColor('#475569')
    )
    body_style = ParagraphStyle(
        'InvoiceBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    elements = []

    created_at = order.get('created_at')
    if isinstance(created_at, (datetime.datetime, datetime.date)):
        date_str = created_at.strftime('%d %b %Y, %I:%M %p')
    else:
        date_str = str(created_at or datetime.datetime.now().strftime('%d %b %Y, %I:%M %p'))

    # Header
    header_data = [
        [
            Paragraph('<b>CartCommerce</b><br/><font size="8" color="#64748b">Your Trusted Online Store<br/>Support: support@cartcommerce.com</font>', brand_style),
            Paragraph(f'<b>TAX INVOICE</b><br/><font size="8" color="#475569"><b>Invoice #:</b> INV-{order.get("order_id", "N/A")}<br/><b>Date:</b> {date_str}</font>', right_text)
        ]
    ]
    header_table = Table(header_data, colWidths=[3.5 * inch, 3.5 * inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceBefore=8, spaceAfter=14))

    # Customer & Payment Info
    user_name = user.get('name', 'Customer') if user else 'Customer'
    user_email = user.get('email', 'N/A') if user else 'N/A'
    payment_id = order.get('payment_id', 'N/A')
    order_id = order.get('order_id', 'N/A')
    status = order.get('status', 'Paid')
    payment_status = order.get('payment_status', 'Success')

    info_data = [
        [
            Paragraph(f'<b>Customer Details:</b><br/><b>Name:</b> {user_name}<br/><b>Email:</b> {user_email}', body_style),
            Paragraph(f'<b>Payment Details:</b><br/><b>Order ID:</b> {order_id}<br/><b>Payment ID:</b> {payment_id}<br/><b>Status:</b> <font color="#16a34a"><b>{status} ({payment_status})</b></font>', body_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[3.5 * inch, 3.5 * inch])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 14))

    # Items Table
    item_rows = [
        [
            Paragraph('<b>#</b>', table_header_style),
            Paragraph('<b>Product Name</b>', table_header_style),
            Paragraph('<b>Unit Price</b>', table_header_style),
            Paragraph('<b>Qty</b>', table_header_style),
            Paragraph('<b>Total Amount</b>', table_header_style)
        ]
    ]

    calc_subtotal = 0.0
    for idx, itm in enumerate(items, start=1):
        p_name = itm.get('product_name', 'Item')
        p_price = float(itm.get('product_price', 0))
        p_qty = int(itm.get('quantity', 1))
        p_sub = float(itm.get('subtotal', p_price * p_qty))
        calc_subtotal += p_sub

        item_rows.append([
            str(idx),
            Paragraph(p_name, body_style),
            f"INR {p_price:,.2f}",
            str(p_qty),
            f"INR {p_sub:,.2f}"
        ])

    items_table = Table(item_rows, colWidths=[0.4 * inch, 3.4 * inch, 1.2 * inch, 0.6 * inch, 1.4 * inch])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 10))

    # Summary Table
    total_amount = float(order.get('total_amount', calc_subtotal))
    summary_data = [
        ['', 'Subtotal:', f"INR {calc_subtotal:,.2f}"],
        ['', 'Shipping & Handling:', 'FREE'],
        ['', 'Taxes (GST Included):', 'INR 0.00'],
        ['', 'Grand Total:', f"INR {total_amount:,.2f}"]
    ]
    summary_table = Table(summary_data, colWidths=[3.6 * inch, 1.8 * inch, 1.6 * inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('FONTNAME', (1, 0), (2, -2), 'Helvetica'),
        ('FONTSIZE', (1, 0), (2, -2), 9),
        ('TEXTCOLOR', (1, 0), (2, -2), colors.HexColor('#475569')),
        ('FONTNAME', (1, 3), (2, 3), 'Helvetica-Bold'),
        ('FONTSIZE', (1, 3), (2, 3), 11),
        ('TEXTCOLOR', (1, 3), (2, 3), colors.HexColor('#1e40af')),
        ('LINEABOVE', (1, 3), (2, 3), 1.5, colors.HexColor('#1e40af')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 24))

    # Footer
    footer_text = Paragraph(
        '<para align="center"><font size="8" color="#94a3b8">Thank you for shopping with <b>CartCommerce</b>!<br/>This is an electronically generated tax invoice and requires no physical signature.<br/>For any support, please contact us at support@cartcommerce.com</font></para>',
        body_style
    )
    elements.append(footer_text)

    doc.build(elements)
    return buffer.getvalue()


# =================================================================
# ROUTE 1: STOREFRONT HOME (SHOW PRODUCTS, DEALS & OFFERS)
# =================================================================
@app.route('/')
def index():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = cursor.fetchall()

        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search:
            query += " AND (name LIKE %s OR description LIKE %s)"
            params.extend(["%" + search + "%", "%" + search + "%"])

        if category_filter:
            query += " AND category = %s"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"
        cursor.execute(query, params)
        products = cursor.fetchall()

        cursor.close()
        conn.close()
    except Exception:
        categories = []
        products = []

    return render_template(
        'index.html',
        products=products,
        categories=categories,
        search=search,
        selected_category=category_filter,
        is_logged_in=('user_id' in session)
    )




# =================================================================
# ROUTE 2: ADMIN SIGNUP
# =================================================================
@app.route('/admin_signup', methods=['GET', 'POST'])
@app.route('/admin-signup', methods=['GET', 'POST'])
def admin_signup():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        return render_template('admin/admin_signup.html')

    adname = request.form.get('myname', '').strip()
    ademail = request.form.get('myemail', '').strip()

    if not adname or not ademail:
        flash("Please enter both name and email.", "danger")
        return redirect("/admin_signup")

    try:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id FROM admin_sc WHERE email=%s", (ademail,))
        result = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect("/admin_signup")

    if result:
        flash(f"An account with email '{ademail}' already exists.", "danger")
        return redirect("/admin_signup")

    # Store registration details in session
    session['sadname'] = adname
    session['sademail'] = ademail

    # Generate 6-digit OTP
    otp = random.randint(100000, 999999)
    session['sotp'] = otp

    # Send OTP Email
    try:
        message = Message(
            subject="CartCommerce Admin OTP",
            sender=config.MAIL_USERNAME,
            recipients=[ademail]
        )
        message.body = f"Hello {adname},\n\nYour CartCommerce Admin Sign-up OTP is: {otp}\n\nDo not share this code with anyone."
        mail.send(message)
    except Exception as e:
        flash(f"Failed to send OTP email: {str(e)}", "danger")
        return redirect("/admin_signup")

    flash("OTP has been successfully sent to your email!", "success")
    return redirect("/verify_otp")


# =================================================================
# ROUTE 3: VERIFY OTP & REGISTER
# =================================================================
@app.route("/verify_otp", methods=['GET', 'POST'])
@app.route("/verify-otp", methods=['GET', 'POST'])
def verify_otp():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        if 'sotp' not in session or 'sademail' not in session:
            flash("Please sign up first to receive an OTP.", "danger")
            return redirect('/admin_signup')
        return render_template("admin/verify_otp.html", email=session.get('sademail'))

    # Ensure required session data is present
    if 'sotp' not in session or 'sadname' not in session or 'sademail' not in session:
        flash("Session expired or invalid. Please sign up again.", "danger")
        return redirect('/admin_signup')

    # User submitted OTP + Password
    user_otp = request.form.get('myotp', '').strip()
    password = request.form.get('mypswrd', '').strip()

    if not user_otp or not password:
        flash("Please enter both OTP and password.", "danger")
        return redirect('/verify_otp')

    # Compare OTP
    if str(session.get('sotp')) != str(user_otp):
        flash("Invalid OTP. Please try again!", "danger")
        return redirect('/verify_otp')

    # Hash password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Insert admin into database
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admin_sc (anime, email, apassword) VALUES (%s, %s, %s)",
            (session['sadname'], session['sademail'], hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Registration failed: {str(e)}", "danger")
        return redirect('/verify_otp')

    # Clear temporary session data
    session.pop('sotp', None)
    session.pop('sadname', None)
    session.pop('sademail', None)

    flash("Admin registered successfully! Please log in.", "success")
    return redirect('/admin-login')


# =================================================================
# ROUTE 4: ADMIN LOGIN
# =================================================================
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        return render_template("admin/admin_login.html")

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not email or not password:
        flash("Please enter both email and password.", "danger")
        return redirect('/admin-login')

    # Step 1: Check if admin exists
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM admin_sc WHERE email=%s", (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/admin-login')

    if admin is None:
        flash("Email not found! Please register first.", "danger")
        return redirect('/admin-login')

    # Step 2: Compare entered password with hashed password
    try:
        stored_hashed_password = admin['apassword'].encode('utf-8')
        if not bcrypt.checkpw(password.encode('utf-8'), stored_hashed_password):
            flash("Incorrect password! Try again.", "danger")
            return redirect('/admin-login')
    except Exception:
        flash("Authentication error. Please reset your password.", "danger")
        return redirect('/admin-login')

    # Step 3: Login success → Create session
    session['admin_id'] = admin['id']
    session['admin_name'] = admin.get('anime') or 'Admin'
    session['admin_email'] = admin['email']

    flash(f"Welcome back, {session['admin_name']}!", "success")
    return redirect('/admin-dashboard')


# =================================================================
# ROUTE 4.1: ADMIN FORGOT PASSWORD & RESET PASSWORD
# =================================================================
@app.route('/admin/forgot-password', methods=['GET', 'POST'])
@app.route('/admin-forgot-password', methods=['GET', 'POST'])
def admin_forgot_password():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        return render_template('admin/admin_forgot_password.html')

    email = request.form.get('email', '').strip()
    if not email:
        flash("Please enter your admin email address.", "danger")
        return redirect('/admin/forgot-password')

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, anime, email FROM admin_sc WHERE email = %s", (email,))
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/admin/forgot-password')

    if not admin:
        flash(f"No administrator account found with email '{email}'.", "danger")
        return redirect('/admin/forgot-password')

    # Generate 6-digit OTP
    otp = random.randint(100000, 999999)
    session['admin_reset_otp'] = otp
    session['admin_reset_email'] = email
    session.modified = True

    admin_name = admin.get('anime') or 'Admin'

    # Send OTP Email
    try:
        message = Message(
            subject="CartCommerce Admin Password Reset OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        message.body = f"Hello {admin_name},\n\nYour CartCommerce Admin password reset OTP is: {otp}\n\nDo not share this OTP with anyone. If you did not request a password reset, please secure your account immediately."
        mail.send(message)
    except Exception as e:
        flash(f"Failed to send reset OTP email: {str(e)}", "danger")
        return redirect('/admin/forgot-password')

    flash("A 6-digit password reset OTP has been sent to your email.", "success")
    return redirect('/admin/reset-password')


@app.route('/admin/reset-password', methods=['GET', 'POST'])
@app.route('/admin-reset-password', methods=['GET', 'POST'])
def admin_reset_password():
    if 'admin_id' in session:
        return redirect('/admin-dashboard')

    if request.method == 'GET':
        if 'admin_reset_otp' not in session or 'admin_reset_email' not in session:
            flash("Please request a password reset OTP first.", "danger")
            return redirect('/admin/forgot-password')
        return render_template('admin/admin_reset_password.html', email=session.get('admin_reset_email'))

    if 'admin_reset_otp' not in session or 'admin_reset_email' not in session:
        flash("Reset session expired. Please request a new OTP.", "danger")
        return redirect('/admin/forgot-password')

    otp = request.form.get('otp', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not otp or not new_password or not confirm_password:
        flash("Please fill in all fields.", "danger")
        return redirect('/admin/reset-password')

    if str(session.get('admin_reset_otp')) != str(otp):
        flash("Invalid OTP code. Please try again!", "danger")
        return redirect('/admin/reset-password')

    if len(new_password) < 6:
        flash("Password must be at least 6 characters long.", "danger")
        return redirect('/admin/reset-password')

    if new_password != confirm_password:
        flash("Passwords do not match. Please re-enter.", "danger")
        return redirect('/admin/reset-password')

    try:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE admin_sc SET apassword = %s WHERE email = %s", (hashed_password, session['admin_reset_email']))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Failed to reset password: {str(e)}", "danger")
        return redirect('/admin/reset-password')

    session.pop('admin_reset_otp', None)
    session.pop('admin_reset_email', None)
    session.modified = True

    flash("Admin password has been reset successfully! Please log in.", "success")
    return redirect('/admin-login')


# =================================================================
# ROUTE 5: ADMIN DASHBOARD (PROTECTED)
# =================================================================
@app.route('/admin-dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        flash("Please login to access dashboard!", "danger")
        return redirect('/admin-login')

    stats = {'total_products': 0, 'total_categories': 0}

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total FROM products")
        row = cursor.fetchone()
        stats['total_products'] = row['total'] if row else 0

        cursor.execute("SELECT COUNT(DISTINCT category) AS total FROM products WHERE category IS NOT NULL AND category != ''")
        row = cursor.fetchone()
        stats['total_categories'] = row['total'] if row else 0

        cursor.close()
        conn.close()
    except Exception:
        pass

    return render_template(
        "admin/dashboard.html",
        admin_name=session.get('admin_name', 'Admin'),
        stats=stats
    )


# =================================================================
# ROUTE 6: ADMIN LOGOUT
# =================================================================
@app.route('/admin-logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_name', None)
    session.pop('admin_email', None)

    flash("Logged out successfully.", "success")
    return redirect('/admin-login')


# =================================================================
# ROUTE 7: ADD PRODUCT (GET & POST)
# =================================================================
@app.route('/admin/add-item', methods=['GET', 'POST'])
def add_item():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    if request.method == 'GET':
        return render_template("admin/add_item.html")

    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    price_str = request.form.get('price', '').strip()
    image_file = request.files.get('image')

    # Validation
    if not name or not description or not category or not price_str:
        flash("Please fill all required fields!", "danger")
        return redirect('/admin/add-item')

    try:
        price = float(price_str)
        if price < 0:
            raise ValueError("Price cannot be negative")
    except ValueError:
        flash("Invalid price. Please enter a valid number.", "danger")
        return redirect('/admin/add-item')

    if not image_file or image_file.filename == "":
        flash("Please upload a product image!", "danger")
        return redirect('/admin/add-item')

    filename = secure_filename(image_file.filename)
    if not filename:
        flash("Invalid file name. Please choose another image.", "danger")
        return redirect('/admin/add-item')

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO products (name, description, category, price, image) VALUES (%s, %s, %s, %s, %s)",
            (name, description, category, price, filename)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error while adding product: {str(e)}", "danger")
        return redirect('/admin/add-item')

    flash("Product added successfully!", "success")
    return redirect('/admin/item-list')


# =================================================================
# ROUTE 8: VIEW ALL PRODUCTS (GRID/CATALOG VIEW)
# =================================================================
@app.route('/admin/view-items', methods=['GET'])
def view_items():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products ORDER BY product_id DESC")
        products = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        products = []
        flash(f"Database error: {str(e)}", "danger")

    return render_template("admin/view_items.html", products=products)


# =================================================================
# ROUTE 9: VIEW SINGLE PRODUCT DETAILS
# =================================================================
@app.route('/admin/view-item/<int:item_id>', methods=['GET'])
def view_item(item_id):
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/admin/item-list')

    if not product:
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    return render_template("admin/view_single_item.html", product=product)


# =================================================================
# ROUTE 10: UPDATE PRODUCT (GET & POST)
# =================================================================
@app.route('/admin/update-item/<int:item_id>', methods=['GET', 'POST'])
def update_item(item_id):
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'GET':
        cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()

        if not product:
            flash("Product not found!", "danger")
            return redirect('/admin/item-list')

        return render_template("admin/update_item.html", product=product)

    # POST: Update product data
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', '').strip()
    price_str = request.form.get('price', '').strip()
    new_image = request.files.get('image')

    if not name or not description or not category or not price_str:
        cursor.close()
        conn.close()
        flash("Please fill all required fields!", "danger")
        return redirect(f'/admin/update-item/{item_id}')

    try:
        price = float(price_str)
        if price < 0:
            raise ValueError("Price cannot be negative")
    except ValueError:
        cursor.close()
        conn.close()
        flash("Invalid price. Please enter a valid number.", "danger")
        return redirect(f'/admin/update-item/{item_id}')

    # Fetch existing product
    cursor.execute("SELECT * FROM products WHERE product_id = %s", (item_id,))
    product = cursor.fetchone()

    if not product:
        cursor.close()
        conn.close()
        flash("Product not found!", "danger")
        return redirect('/admin/item-list')

    old_image_name = product.get('image')
    final_image_name = old_image_name

    # If new image uploaded -> save & replace
    if new_image and new_image.filename != "":
        new_filename = secure_filename(new_image.filename)
        if new_filename:
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            new_image_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            new_image.save(new_image_path)

            # Safely remove old image file
            if old_image_name and old_image_name != new_filename:
                old_image_path = os.path.join(app.config['UPLOAD_FOLDER'], old_image_name)
                if os.path.isfile(old_image_path):
                    try:
                        os.remove(old_image_path)
                    except Exception:
                        pass

            final_image_name = new_filename

    # Update database
    cursor.execute("""
        UPDATE products
        SET name=%s, description=%s, category=%s, price=%s, image=%s
        WHERE product_id=%s
    """, (name, description, category, price, final_image_name, item_id))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Product updated successfully!", "success")
    return redirect('/admin/item-list')


# =================================================================
# ROUTE 11: PRODUCT LIST WITH UNIFIED SEARCH + CATEGORY FILTER
# =================================================================
@app.route('/admin/item-list')
def item_list():
    if 'admin_id' not in session:
        flash("Please login!", "danger")
        return redirect('/admin-login')

    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch categories for dropdown filter
        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = cursor.fetchall()

        # 2. Build dynamic filter query
        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search:
            query += " AND (name LIKE %s OR description LIKE %s)"
            params.extend(["%" + search + "%", "%" + search + "%"])

        if category_filter:
            query += " AND category = %s"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"
        cursor.execute(query, params)
        products = cursor.fetchall()

        cursor.close()
        conn.close()
    except Exception as e:
        categories = []
        products = []
        flash(f"Database error: {str(e)}", "danger")

    return render_template(
        "admin/item_list.html",
        products=products,
        categories=categories,
        search=search,
        selected_category=category_filter
    )


# =================================================================
# ROUTE 12: DELETE PRODUCT (DELETE DB ROW + DELETE IMAGE FILE)
# =================================================================
@app.route('/admin/delete-item/<int:item_id>')
def delete_item(item_id):
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Fetch product to get image filename
        cursor.execute("SELECT image FROM products WHERE product_id=%s", (item_id,))
        product = cursor.fetchone()

        if not product:
            cursor.close()
            conn.close()
            flash("Product not found!", "danger")
            return redirect('/admin/item-list')

        image_name = product.get('image')

        # 2. Delete product from database
        cursor.execute("DELETE FROM products WHERE product_id=%s", (item_id,))
        conn.commit()

        # 3. Safely delete image file from filesystem
        if image_name:
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_name)
            if os.path.isfile(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass

        cursor.close()
        conn.close()
        flash("Product deleted successfully!", "success")
    except Exception as e:
        flash(f"Failed to delete product: {str(e)}", "danger")

    return redirect('/admin/item-list')


# =================================================================
# DAY 8: ADMIN PROFILE MANAGEMENT (VIEW & UPDATE WITH IMAGE)
# =================================================================
@app.route('/admin/profile', methods=['GET'])
def admin_profile():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id AS admin_id, anime AS name, email, apassword AS password, profile_image FROM admin_sc WHERE id = %s",
            (admin_id,)
        )
        admin = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        admin = None

    if not admin:
        flash("Admin account not found!", "danger")
        return redirect('/admin-login')

    return render_template("admin/admin_profile.html", admin=admin)


@app.route('/admin/profile', methods=['POST'])
def admin_profile_update():
    if 'admin_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/admin-login')

    admin_id = session['admin_id']

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    new_password = request.form.get('password', '').strip()
    new_image = request.files.get('profile_image')

    if not name or not email:
        flash("Name and email are required!", "danger")
        return redirect('/admin/profile')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT id AS admin_id, anime AS name, email, apassword AS password, profile_image FROM admin_sc WHERE id = %s",
            (admin_id,)
        )
        admin = cursor.fetchone()

        if not admin:
            cursor.close()
            conn.close()
            flash("Admin account not found!", "danger")
            return redirect('/admin-login')

        old_image_name = admin.get('profile_image')

        # Update password only if entered
        if new_password:
            hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        else:
            hashed_password = admin['password']

        # Process new profile image if uploaded
        final_image_name = old_image_name
        if new_image and new_image.filename != "":
            new_filename = secure_filename(new_image.filename)
            if new_filename:
                os.makedirs(app.config['ADMIN_UPLOAD_FOLDER'], exist_ok=True)
                image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], new_filename)
                new_image.save(image_path)

                # Delete old image if it exists and differs
                if old_image_name and old_image_name != new_filename:
                    old_image_path = os.path.join(app.config['ADMIN_UPLOAD_FOLDER'], old_image_name)
                    if os.path.isfile(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except Exception:
                            pass

                final_image_name = new_filename

        # Update database
        cursor.execute("""
            UPDATE admin_sc
            SET anime=%s, email=%s, apassword=%s, profile_image=%s
            WHERE id=%s
        """, (name, email, hashed_password, final_image_name, admin_id))

        conn.commit()
        cursor.close()
        conn.close()

        # Update session name and email for UI consistency
        session['admin_name'] = name
        session['admin_email'] = email

        flash("Profile updated successfully!", "success")
    except Exception as e:
        flash(f"Failed to update profile: {str(e)}", "danger")

    return redirect('/admin/profile')


# =================================================================
# DAY 9: USER REGISTRATION (WITH EMAIL OTP), LOGIN, DASHBOARD & LOGOUT
# =================================================================
@app.route('/user-register', methods=['GET', 'POST'])
@app.route('/user_register', methods=['GET', 'POST'])
@app.route('/user-signup', methods=['GET', 'POST'])
@app.route('/user_signup', methods=['GET', 'POST'])
def user_register():
    if 'user_id' in session:
        return redirect('/user-dashboard')

    if request.method == 'GET':
        return render_template("user/user_register.html")

    name = (request.form.get('myname') or request.form.get('name') or '').strip()
    email = (request.form.get('myemail') or request.form.get('email') or '').strip()

    if not name or not email:
        flash("Please enter both name and email.", "danger")
        return redirect('/user-register')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
        existing_user = cursor.fetchone()

        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/user-register')

    if existing_user:
        flash(f"An account with email '{email}' already exists. Please login.", "danger")
        return redirect('/user-login')

    # Store registration details in session
    session['user_reg_name'] = name
    session['user_reg_email'] = email

    # Generate 6-digit OTP
    otp = random.randint(100000, 999999)
    session['user_reg_otp'] = otp
    session.modified = True

    # Send OTP Email
    try:
        message = Message(
            subject="CartCommerce User Registration OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        message.body = f"Hello {name},\n\nYour CartCommerce Customer Sign-up OTP is: {otp}\n\nDo not share this code with anyone."
        mail.send(message)
    except Exception as e:
        flash(f"Failed to send OTP email: {str(e)}", "danger")
        return redirect('/user-register')

    flash("OTP has been successfully sent to your email!", "success")
    return redirect('/user-verify-otp')


@app.route('/user-verify-otp', methods=['GET', 'POST'])
@app.route('/user_verify_otp', methods=['GET', 'POST'])
def user_verify_otp():
    if 'user_id' in session:
        return redirect('/user-dashboard')

    if request.method == 'GET':
        if 'user_reg_otp' not in session or 'user_reg_email' not in session:
            flash("Please sign up first to receive an OTP.", "danger")
            return redirect('/user-register')
        return render_template("user/user_verify_otp.html", email=session.get('user_reg_email'))

    # Ensure required session data is present
    if 'user_reg_otp' not in session or 'user_reg_name' not in session or 'user_reg_email' not in session:
        flash("Session expired or invalid. Please sign up again.", "danger")
        return redirect('/user-register')

    user_otp = (request.form.get('myotp') or request.form.get('otp') or '').strip()
    password = (request.form.get('mypswrd') or request.form.get('password') or '').strip()

    if not user_otp or not password:
        flash("Please enter both OTP and password.", "danger")
        return redirect('/user-verify-otp')

    # Compare OTP
    if str(session.get('user_reg_otp')) != str(user_otp):
        flash("Invalid OTP. Please try again!", "danger")
        return redirect('/user-verify-otp')

    # Hash password using bcrypt
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Insert user into database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (session['user_reg_name'], session['user_reg_email'], hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Registration failed: {str(e)}", "danger")
        return redirect('/user-verify-otp')

    # Clear temporary session data
    session.pop('user_reg_otp', None)
    session.pop('user_reg_name', None)
    session.pop('user_reg_email', None)
    session.modified = True

    flash("Registration successful! Please log in.", "success")
    return redirect('/user-login')



@app.route('/user-login', methods=['GET', 'POST'])
def user_login():
    if 'user_id' in session:
        return redirect('/user-dashboard')

    if request.method == 'GET':
        return render_template("user/user_login.html")

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not email or not password:
        flash("Please enter both email and password.", "danger")
        return redirect('/user-login')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if not user:
            flash("Email not found! Please register.", "danger")
            return redirect('/user-login')

        stored_password = user['password']
        if isinstance(stored_password, str):
            stored_password = stored_password.encode('utf-8')

        if not bcrypt.checkpw(password.encode('utf-8'), stored_password):
            flash("Incorrect password!", "danger")
            return redirect('/user-login')

        # Create user session
        session['user_id'] = user['user_id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']

        flash(f"Welcome back, {user['name']}!", "success")
        return redirect('/user-dashboard')
    except Exception as e:
        flash(f"Login error: {str(e)}", "danger")
        return redirect('/user-login')


# =================================================================
# ROUTE 9.1: USER FORGOT PASSWORD & RESET PASSWORD
# =================================================================
@app.route('/user/forgot-password', methods=['GET', 'POST'])
@app.route('/user-forgot-password', methods=['GET', 'POST'])
def user_forgot_password():
    if 'user_id' in session:
        return redirect('/user-dashboard')

    if request.method == 'GET':
        return render_template('user/user_forgot_password.html')

    email = request.form.get('email', '').strip()
    if not email:
        flash("Please enter your registered customer email.", "danger")
        return redirect('/user/forgot-password')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, name, email FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/user/forgot-password')

    if not user:
        flash(f"No customer account found with email '{email}'.", "danger")
        return redirect('/user/forgot-password')

    # Generate 6-digit OTP
    otp = random.randint(100000, 999999)
    session['user_reset_otp'] = otp
    session['user_reset_email'] = email
    session.modified = True

    user_name = user.get('name') or 'Customer'

    # Send OTP Email
    try:
        message = Message(
            subject="CartCommerce Customer Password Reset OTP",
            sender=config.MAIL_USERNAME,
            recipients=[email]
        )
        message.body = f"Hello {user_name},\n\nYour CartCommerce password reset OTP is: {otp}\n\nDo not share this OTP with anyone. If you did not request a password reset, you can safely ignore this email."
        mail.send(message)
    except Exception as e:
        flash(f"Failed to send reset OTP email: {str(e)}", "danger")
        return redirect('/user/forgot-password')

    flash("A 6-digit password reset OTP has been sent to your email.", "success")
    return redirect('/user/reset-password')


@app.route('/user/reset-password', methods=['GET', 'POST'])
@app.route('/user-reset-password', methods=['GET', 'POST'])
def user_reset_password():
    if 'user_id' in session:
        return redirect('/user-dashboard')

    if request.method == 'GET':
        if 'user_reset_otp' not in session or 'user_reset_email' not in session:
            flash("Please request a password reset OTP first.", "danger")
            return redirect('/user/forgot-password')
        return render_template('user/user_reset_password.html', email=session.get('user_reset_email'))

    if 'user_reset_otp' not in session or 'user_reset_email' not in session:
        flash("Reset session expired. Please request a new OTP.", "danger")
        return redirect('/user/forgot-password')

    otp = request.form.get('otp', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()

    if not otp or not new_password or not confirm_password:
        flash("Please fill in all fields.", "danger")
        return redirect('/user/reset-password')

    if str(session.get('user_reset_otp')) != str(otp):
        flash("Invalid OTP code. Please try again!", "danger")
        return redirect('/user/reset-password')

    if len(new_password) < 6:
        flash("Password must be at least 6 characters long.", "danger")
        return redirect('/user/reset-password')

    if new_password != confirm_password:
        flash("Passwords do not match. Please re-enter.", "danger")
        return redirect('/user/reset-password')

    try:
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_password, session['user_reset_email']))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Failed to reset password: {str(e)}", "danger")
        return redirect('/user/reset-password')

    session.pop('user_reset_otp', None)
    session.pop('user_reset_email', None)
    session.modified = True

    flash("Password reset successfully! Please sign in with your new password.", "success")
    return redirect('/user-login')


@app.route('/user-dashboard')
def user_dashboard():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = cursor.fetchall()

        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search:
            query += " AND (name LIKE %s OR description LIKE %s)"
            params.extend(["%" + search + "%", "%" + search + "%"])

        if category_filter:
            query += " AND category = %s"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"
        cursor.execute(query, params)
        products = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS total_orders, COALESCE(SUM(total_amount), 0) AS total_spent FROM orders WHERE user_id = %s", (user_id,))
        order_stats = cursor.fetchone() or {'total_orders': 0, 'total_spent': 0}

        cursor.execute("SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC LIMIT 3", (user_id,))
        recent_orders = cursor.fetchall()

        cursor.close()
        conn.close()
    except Exception:
        categories = []
        products = []
        order_stats = {'total_orders': 0, 'total_spent': 0}
        recent_orders = []

    return render_template(
        "user/user_home.html",
        user_name=session.get('user_name', 'Customer'),
        products=products,
        categories=categories,
        order_stats=order_stats,
        recent_orders=recent_orders,
        search=search,
        selected_category=category_filter
    )


@app.route('/user-logout')
def user_logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('user_email', None)

    flash("Logged out successfully!", "success")
    return redirect('/user-login')


# =================================================================
# ROUTE: USER PROFILE (VIEW & EDIT PROFILE, CHANGE PASSWORD)
# =================================================================
@app.route('/user/profile', methods=['GET', 'POST'])
@app.route('/user-profile', methods=['GET', 'POST'])
def user_profile():
    if 'user_id' not in session:
        flash("Please login to view your profile!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']

    if request.method == 'GET':
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT user_id, name, email, profile_image FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()
        except Exception as e:
            flash(f"Error fetching profile: {str(e)}", "danger")
            user = {'name': session.get('user_name', 'Customer'), 'email': session.get('user_email', ''), 'profile_image': None}

        return render_template("user/user_profile.html", user=user)

    # Handle POST update
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    new_image = request.files.get('profile_image')

    if not name or not email:
        flash("Name and email cannot be empty.", "danger")
        return redirect('/user/profile')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT user_id, profile_image FROM users WHERE user_id = %s", (user_id,))
        current_user = cursor.fetchone()
        old_image_name = current_user.get('profile_image') if current_user else None

        # Check if email is used by another user
        cursor.execute("SELECT user_id FROM users WHERE email = %s AND user_id != %s", (email, user_id))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash(f"The email '{email}' is already in use by another account.", "danger")
            return redirect('/user/profile')

        final_image_name = old_image_name
        if new_image and new_image.filename != "":
            new_filename = secure_filename(f"user_{user_id}_{new_image.filename}")
            if new_filename:
                os.makedirs(app.config['USER_UPLOAD_FOLDER'], exist_ok=True)
                image_path = os.path.join(app.config['USER_UPLOAD_FOLDER'], new_filename)
                new_image.save(image_path)

                if old_image_name and old_image_name != new_filename:
                    old_image_path = os.path.join(app.config['USER_UPLOAD_FOLDER'], old_image_name)
                    if os.path.isfile(old_image_path):
                        try:
                            os.remove(old_image_path)
                        except Exception:
                            pass
                final_image_name = new_filename

        if password:
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor.execute(
                "UPDATE users SET name = %s, email = %s, password = %s, profile_image = %s WHERE user_id = %s",
                (name, email, hashed, final_image_name, user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET name = %s, email = %s, profile_image = %s WHERE user_id = %s",
                (name, email, final_image_name, user_id)
            )

        conn.commit()
        cursor.close()
        conn.close()

        session['user_name'] = name
        session['user_email'] = email
        flash("Profile updated successfully!", "success")
        return redirect('/user/profile')
    except Exception as e:
        flash(f"Failed to update profile: {str(e)}", "danger")
        return redirect('/user/profile')


# =================================================================
# DAY 10: USER PRODUCT CATALOG & DETAILS
# =================================================================
@app.route('/user/products')
def user_products():
    if 'user_id' not in session:
        flash("Please login to view products!", "danger")
        return redirect('/user-login')

    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch categories for filter dropdown
        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
        categories = cursor.fetchall()

        # Build dynamic query
        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if search:
            query += " AND (name LIKE %s OR description LIKE %s)"
            params.extend(["%" + search + "%", "%" + search + "%"])

        if category_filter:
            query += " AND category = %s"
            params.append(category_filter)

        query += " ORDER BY product_id DESC"
        cursor.execute(query, params)
        products = cursor.fetchall()

        cursor.close()
        conn.close()
    except Exception as e:
        categories = []
        products = []
        flash(f"Error loading products: {str(e)}", "danger")

    return render_template(
        "user/user_products.html",
        products=products,
        categories=categories
    )


@app.route('/user/product/<int:product_id>')
def user_product_details(product_id):
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE product_id = %s", (product_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        product = None

    if not product:
        flash("Product not found!", "danger")
        return redirect('/user/products')

    return render_template("user/product_details.html", product=product)


# =================================================================
# DAY 11 & 11.1: USER CART SYSTEM & AMAZON-STYLE AJAX
# =================================================================
@app.route('/user/add-to-cart/<int:product_id>')
def add_to_cart(product_id):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception:
        product = None

    if not product:
        flash("Product not found.", "danger")
        return redirect(request.referrer or '/user/products')

    pid = str(product_id)

    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart
    session.modified = True

    flash("Item added to cart!", "success")
    return redirect(request.referrer or '/user/products')


@app.route('/user/add-to-cart-ajax/<int:product_id>', methods=['GET', 'POST'])
def add_to_cart_ajax(product_id):
    if 'user_id' not in session:
        return {"error": "not_logged_in", "status": "unauthorized"}, 401

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM products WHERE product_id=%s", (product_id,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception:
        product = None

    if not product:
        return {"error": "Product not found", "status": "not_found"}, 404

    pid = str(product_id)

    if pid in cart:
        cart[pid]['quantity'] += 1
    else:
        cart[pid] = {
            'name': product['name'],
            'price': float(product['price']),
            'image': product['image'],
            'quantity': 1
        }

    session['cart'] = cart
    session.modified = True

    return {
        "status": "success",
        "message": "Item added to cart!",
        "cart_count": len(cart)
    }


@app.route('/user/cart')
def view_cart():
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    grand_total = sum(float(item['price']) * int(item['quantity']) for item in cart.values())

    return render_template("user/cart.html", cart=cart, grand_total=grand_total)


@app.route('/user/cart/increase/<pid>')
def increase_quantity(pid):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    pid_str = str(pid)

    if pid_str in cart:
        cart[pid_str]['quantity'] += 1
        session['cart'] = cart
        session.modified = True

    return redirect('/user/cart')


@app.route('/user/cart/decrease/<pid>')
def decrease_quantity(pid):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    pid_str = str(pid)

    if pid_str in cart:
        cart[pid_str]['quantity'] -= 1
        if cart[pid_str]['quantity'] <= 0:
            cart.pop(pid_str)
        session['cart'] = cart
        session.modified = True

    return redirect('/user/cart')


@app.route('/user/cart/remove/<pid>')
def remove_from_cart(pid):
    if 'user_id' not in session:
        flash("Please login first!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    pid_str = str(pid)

    if pid_str in cart:
        cart.pop(pid_str)
        session['cart'] = cart
        session.modified = True
        flash("Item removed from cart!", "success")

    return redirect('/user/cart')


# =================================================================
# DAY 12: RAZORPAY PAYMENT GATEWAY INTEGRATION (SELECTED ITEMS SUPPORT)
# =================================================================
@app.route('/user/pay', methods=['GET', 'POST'])
def user_pay():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty!", "danger")
        return redirect('/user/products')

    # Determine selected items from POST form or GET query param
    selected_pids = None
    if request.method == 'POST':
        selected_pids = request.form.getlist('selected_items')
    else:
        selected_query = request.args.get('selected')
        if selected_query:
            selected_pids = [s.strip() for s in selected_query.split(',') if s.strip()]

    # If specific items were selected, filter cart to those items
    if selected_pids:
        checkout_items = {str(pid): cart[str(pid)] for pid in selected_pids if str(pid) in cart}
    else:
        # Default: checkout all cart items
        checkout_items = cart

    if not checkout_items:
        flash("Please select at least one item to buy!", "warning")
        return redirect('/user/cart')

    # Store checkout items in session so payment_success bills only selected products
    session['checkout_items'] = checkout_items
    session.modified = True

    total_amount = sum(float(item['price']) * int(item['quantity']) for item in checkout_items.values())
    razorpay_amount = int(round(total_amount * 100))  # Convert to paise

    try:
        razorpay_order = razorpay_client.order.create({
            "amount": razorpay_amount,
            "currency": "INR",
            "payment_capture": "1"
        })
        order_id = razorpay_order['id']
    except Exception as e:
        # Fallback simulated order ID for local/offline testing if Razorpay API fails
        order_id = f"order_test_{random.randint(100000, 999999)}"

    session['razorpay_order_id'] = order_id
    session.modified = True

    return render_template(
        "user/payment.html",
        amount=total_amount,
        key_id=getattr(config, 'RAZORPAY_KEY_ID', 'rzp_test_TLeM6Ox9b7K9Dp'),
        order_id=order_id
    )


@app.route('/payment-success')
def payment_success():
    if 'user_id' not in session:
        flash("Please login!", "danger")
        return redirect('/user-login')

    payment_id = request.args.get('payment_id') or request.args.get('razorpay_payment_id')
    order_id = request.args.get('order_id') or request.args.get('razorpay_order_id') or session.get('razorpay_order_id')

    if not payment_id or not order_id:
        flash("Payment details missing or payment cancelled!", "danger")
        return redirect('/user/cart')

    user_id = session['user_id']
    checkout_items = session.get('checkout_items') or session.get('cart', {})

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check if order was already recorded (avoids duplicates on page reload)
        cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        order = cursor.fetchone()

        if not order and checkout_items:
            total_amount = sum(float(item['price']) * int(item['quantity']) for item in checkout_items.values())
            cursor.execute("""
                INSERT INTO orders (order_id, user_id, payment_id, razorpay_order_id, total_amount, status, payment_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (order_id, user_id, payment_id, order_id, total_amount, 'Paid', 'Success'))

            for pid, item in checkout_items.items():
                p_id = int(pid) if str(pid).isdigit() else None
                p_name = item.get('name', 'Product')
                p_price = float(item.get('price', 0))
                p_qty = int(item.get('quantity', 1))
                p_img = item.get('image', '')
                p_subtotal = p_price * p_qty

                cursor.execute("""
                    INSERT INTO order_items (order_id, product_id, product_name, product_price, quantity, product_image, subtotal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (order_id, p_id, p_name, p_price, p_qty, p_img, p_subtotal))

            conn.commit()

            # Remove only purchased items from cart; unselected items remain in cart
            current_cart = session.get('cart', {})
            for pid in checkout_items.keys():
                current_cart.pop(str(pid), None)
            session['cart'] = current_cart
            session.pop('checkout_items', None)
            session.pop('razorpay_order_id', None)
            session.modified = True

            # Refetch the newly created order
            cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            order = cursor.fetchone()

        # Fetch items belonging to this order
        cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cursor.fetchall()

        # Fetch user details
        cursor.execute("SELECT user_id, name, email FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Error recording order: {str(e)}", "danger")
        order = None
        items = []
        user = None

    if not order:
        flash("Order record not found.", "warning")
        return redirect('/user-dashboard')

    return render_template(
        "user/payment_success.html",
        order=order,
        items=items,
        user=user,
        payment_id=payment_id,
        order_id=order_id
    )


# =================================================================
# DAY 13: USER ORDERS HISTORY & ORDER DETAILS
# =================================================================
@app.route('/user/orders')
def user_orders():
    if 'user_id' not in session:
        flash("Please login to view your orders!", "danger")
        return redirect('/user-login')

    user_id = session['user_id']
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM orders 
            WHERE user_id = %s 
            ORDER BY created_at DESC, id DESC
        """, (user_id,))
        orders = cursor.fetchall()

        # Fetch items for each order
        for ord_data in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (ord_data['order_id'],))
            fetched_items = cursor.fetchall()
            ord_data['items'] = fetched_items
            ord_data['order_items'] = fetched_items

        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Error fetching orders: {str(e)}", "danger")
        orders = []

    return render_template("user/orders.html", orders=orders)


# =================================================================
# DAY 14: INVOICE VIEWER & PDF DOWNLOAD
# =================================================================
@app.route('/user/order/<order_id>/invoice')
@app.route('/user/order/<order_id>/invoice/view')
def order_invoice(order_id):
    if 'user_id' not in session and 'admin_id' not in session:
        flash("Please login to access invoice!", "danger")
        return redirect('/user-login')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        order = cursor.fetchone()

        if not order:
            cursor.close()
            conn.close()
            flash("Invoice not found!", "danger")
            return redirect('/user-dashboard')

        # Customer privacy check: Only order owner or admin can view
        if 'user_id' in session and order['user_id'] != session['user_id']:
            cursor.close()
            conn.close()
            flash("Access denied: You cannot view this invoice.", "danger")
            return redirect('/user-dashboard')

        cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cursor.fetchall()

        cursor.execute("SELECT user_id, name, email FROM users WHERE user_id = %s", (order['user_id'],))
        user = cursor.fetchone()

        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/user-dashboard')

    # If PDF download requested via query param ?download=1
    if request.args.get('download') == '1':
        pdf_bytes = generate_invoice_pdf(order, items, user)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"Invoice_{order_id}.pdf"
        )

    # If inline PDF viewer requested via query param ?pdf=1
    if request.args.get('pdf') == '1':
        pdf_bytes = generate_invoice_pdf(order, items, user)
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"Invoice_{order_id}.pdf"
        )

    # Clean HTML Invoice View
    return render_template(
        "user/invoice_view.html",
        order=order,
        items=items,
        user=user
    )


@app.route('/user/order/<order_id>/invoice/download')
def order_invoice_download(order_id):
    if 'user_id' not in session and 'admin_id' not in session:
        flash("Please login to download invoice!", "danger")
        return redirect('/user-login')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        order = cursor.fetchone()

        if not order:
            cursor.close()
            conn.close()
            flash("Invoice not found!", "danger")
            return redirect('/user-dashboard')

        if 'user_id' in session and order['user_id'] != session['user_id']:
            cursor.close()
            conn.close()
            flash("Access denied: You cannot download this invoice.", "danger")
            return redirect('/user-dashboard')

        cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order_id,))
        items = cursor.fetchall()

        cursor.execute("SELECT user_id, name, email FROM users WHERE user_id = %s", (order['user_id'],))
        user = cursor.fetchone()

        cursor.close()
        conn.close()
    except Exception as e:
        flash(f"Database error: {str(e)}", "danger")
        return redirect('/user-dashboard')

    pdf_bytes = generate_invoice_pdf(order, items, user)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Invoice_{order_id}.pdf"
    )


if __name__ == '__main__':
    app.run(debug=True)