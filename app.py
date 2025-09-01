from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Ensure upload folder exists
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def init_db():
    with sqlite3.connect('desi_etsy.db') as con:
        cur = con.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS artisans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT,
                password TEXT,
                verified INTEGER DEFAULT 0
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artisan_id INTEGER,
                name TEXT,
                description TEXT,
                price REAL,
                category TEXT,
                image TEXT,
                approved INTEGER DEFAULT 0
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                quantity INTEGER
            )
        ''')

init_db()

@app.route('/')
def index():
    category = request.args.get('category')
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    if category:
        cur.execute("SELECT * FROM products WHERE approved=1 AND category=?", (category,))
    else:
        cur.execute("SELECT * FROM products WHERE approved=1")
    products = cur.fetchall()
    con.close()
    return render_template('index.html', products=products)

@app.route('/artisan/register', methods=['GET', 'POST'])
def artisan_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        with sqlite3.connect('desi_etsy.db') as con:
            cur = con.cursor()
            cur.execute("INSERT INTO artisans (name, email, password) VALUES (?, ?, ?)",
                        (name, email, password))
            con.commit()
        flash('Registration successful! Please wait for admin verification.', 'success')
        return redirect(url_for('index'))
    return render_template('artisan_register.html')

@app.route('/artisan/login', methods=['GET', 'POST'])
def artisan_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        con = sqlite3.connect('desi_etsy.db')
        cur = con.cursor()
        cur.execute("SELECT * FROM artisans WHERE email=? AND password=?", (email, password))
        artisan = cur.fetchone()
        con.close()
        if artisan:
            if artisan[4] == 1:
                session['artisan_id'] = artisan[0]
                return redirect(url_for('artisan_dashboard'))
            else:
                flash('Your account is not yet verified by admin.', 'warning')
        else:
            flash('Invalid credentials', 'danger')
    return render_template('artisan_register.html')

@app.route('/artisan/dashboard')
def artisan_dashboard():
    if 'artisan_id' not in session:
        return redirect(url_for('artisan_login'))
    artisan_id = session['artisan_id']
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    cur.execute("SELECT * FROM products WHERE artisan_id = ?", (artisan_id,))
    products = cur.fetchall()
    con.close()
    return render_template('artisan_dashboard.html', products=products)

@app.route('/artisan/add_product', methods=['GET', 'POST'])
def add_product():
    if 'artisan_id' not in session:
        return redirect(url_for('artisan_login'))
    if request.method == 'POST':
        name = request.form['name']
        desc = request.form['description']
        price = request.form['price']
        category = request.form['category']
        artisan_id = session['artisan_id']
        image = request.files['image']
        filename = None
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        with sqlite3.connect('desi_etsy.db') as con:
            cur = con.cursor()
            cur.execute('''
                INSERT INTO products (artisan_id, name, description, price, category, image)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (artisan_id, name, desc, price, category, filename))
            con.commit()
        flash('Product added! Awaiting admin approval.', 'success')
        return redirect(url_for('artisan_dashboard'))
    return render_template('add_product.html')

@app.route('/cart/add/<int:product_id>')
def cart_add(product_id):
    with sqlite3.connect('desi_etsy.db') as con:
        cur = con.cursor()
        cur.execute("INSERT INTO cart (product_id, quantity) VALUES (?, ?)", (product_id, 1))
        con.commit()
    flash('Added to cart!', 'success')
    return redirect(url_for('index'))

@app.route('/cart/remove/<int:product_id>')
def remove_from_cart(product_id):
    with sqlite3.connect('desi_etsy.db') as con:
        con.execute("DELETE FROM cart WHERE product_id=?", (product_id,))
        con.commit()
    flash('Item removed from cart.', 'success')
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    cur.execute('''
        SELECT cart.product_id, products.name, products.price, cart.quantity, 
               (products.price * cart.quantity) as subtotal, products.image
        FROM cart
        JOIN products ON cart.product_id = products.id
    ''')
    items = cur.fetchall()
    total = sum(item[4] for item in items)
    con.close()
    return render_template('cart.html', items=items, total=total)

@app.route('/checkout')
def checkout():
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    cur.execute('''
        SELECT p.id, p.name, p.price, c.quantity 
        FROM cart c 
        JOIN products p ON c.product_id = p.id
    ''')
    items = cur.fetchall()
    total = sum(item[2] * item[3] for item in items)
    con.close()
    return render_template('checkout.html', items=items, total=total)

@app.route('/confirm_payment', methods=['POST'])
def confirm_payment():
    email = request.form['email']
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    cur.execute('''
        SELECT p.name, p.price, c.quantity 
        FROM cart c 
        JOIN products p ON c.product_id = p.id
    ''')
    items = cur.fetchall()
    details = ""
    total = 0
    for item in items:
        subtotal = item[1] * item[2]
        details += f"{item[0]} (Qty: {item[2]}) - ₹{subtotal}\n"
        total += subtotal
    send_email(
        subject="Desi Etsy Order Confirmation",
        body=f"Your payment is confirmed.\n\nOrder Details:\n{details}\nTotal: ₹{total}",
        to=email
    )
    con.execute("DELETE FROM cart")
    con.commit()
    con.close()
    flash('Payment confirmed! Order details sent via email.', 'success')
    return redirect(url_for('index'))

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'admin@123':
            session['admin'] = True
            flash('Admin logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))
    con = sqlite3.connect('desi_etsy.db')
    cur = con.cursor()
    cur.execute("SELECT * FROM artisans WHERE verified=0")
    artisans = cur.fetchall()
    cur.execute("SELECT * FROM products WHERE approved=0")
    products = cur.fetchall()
    con.close()
    return render_template('admin_dashboard.html', artisans=artisans, products=products)

@app.route('/admin/verify_artisan/<int:artisan_id>')
def verify_artisan(artisan_id):
    with sqlite3.connect('desi_etsy.db') as con:
        con.execute("UPDATE artisans SET verified=1 WHERE id=?", (artisan_id,))
        con.commit()
    flash('Artisan verified!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_product/<int:product_id>')
def approve_product(product_id):
    with sqlite3.connect('desi_etsy.db') as con:
        con.execute("UPDATE products SET approved=1 WHERE id=?", (product_id,))
        con.commit()
    flash('Product approved!', 'success')
    return redirect(url_for('admin_dashboard'))

def send_email(subject, body, to):
    from_email = "ruthishkumar.2353045@srec.ac.in"
    password = "nwctnwpvpkyjvtfy"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print("Email failed:", e)

if __name__ == '__main__':
    app.run(debug=True)
