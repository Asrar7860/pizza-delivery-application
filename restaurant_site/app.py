import uuid
from datetime import datetime, timedelta
import pytz

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a secure key before production

# Database settings
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///restaurant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# MODELS
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_group_id = db.Column(db.String(36), nullable=False, index=True)
    customer_username = db.Column(db.String(150), nullable=False)
    customer_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(150), nullable=False)
    item = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Pending')
    cancelled = db.Column(db.Boolean, default=False)
    cancellation_reason = db.Column(db.Text)
    estimated_time = db.Column(db.String(50))  # Admin can set estimated time string
    order_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # UTC time

# Menu items (in-memory for demo)
menu = [
    {"id": 1, "name": "Margherita Pizza", "price": 300},
    {"id": 2, "name": "Pasta Alfredo", "price": 250},
    {"id": 3, "name": "Paneer Tikka", "price": 220},
    {"id": 4, "name": "Cheese and Corn", "price": 265},
    {"id": 5, "name": "Chicken Tikka", "price": 350},
    {"id": 6, "name": "Double Cheese Margherita", "price": 400},
]

# Static admin credentials for demo
admin_users = {"admin": "admin123"}

def initialize_cart():
    if 'cart' not in session:
        session['cart'] = {}

# ROUTES

@app.route('/')
def landing():
    return render_template('landing.html')

# Customer Signup
@app.route('/customer/signup', methods=['GET', 'POST'])
def customer_signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
            return redirect(url_for('customer_signup'))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Signup successful! Please login.")
        return redirect(url_for('customer_login'))
    return render_template('customer_signup.html')

# Customer Login
@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['customer_logged_in'] = True
            session['customer_username'] = username
            flash(f"Welcome back, {username}!")
            return redirect(url_for('index'))
        flash("Invalid username or password.")
        return redirect(url_for('customer_login'))
    return render_template('customer_login.html')

# Customer Logout
@app.route('/customer/logout')
def customer_logout():
    session.pop('customer_logged_in', None)
    session.pop('customer_username', None)
    flash("Logged out successfully.")
    return redirect(url_for('customer_login'))

# Admin Login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if admin_users.get(username) == password:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash("Admin logged in.")
            return redirect(url_for('view_orders'))
        flash("Invalid admin credentials.")
        return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

# Admin Logout
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash("Admin logged out.")
    return redirect(url_for('admin_login'))

# Menu display
@app.route('/menu')
def index():
    if not session.get('customer_logged_in'):
        flash("Please login to access the menu.")
        return redirect(url_for('customer_login'))
    return render_template('menu.html', menu=menu)

# Add item to cart
@app.route('/add_to_cart/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    if not session.get('customer_logged_in'):
        flash("Please login to add items.")
        return redirect(url_for('customer_login'))
    initialize_cart()
    cart = session['cart']
    try:
        qty = int(request.form.get('quantity', 1))
        if qty < 1:
            raise ValueError()
    except:
        flash("Quantity must be a positive integer.")
        return redirect(url_for('index'))
    item = next((i for i in menu if i['id'] == item_id), None)
    if not item:
        flash("Invalid menu item.")
        return redirect(url_for('index'))
    cart[str(item_id)] = cart.get(str(item_id), 0) + qty
    session['cart'] = cart
    flash(f"Added {qty} x {item['name']} to cart.")
    return redirect(url_for('index'))

# View and update cart
@app.route('/cart', methods=['GET', 'POST'])
def view_cart():
    if not session.get('customer_logged_in'):
        flash("Please login to view cart.")
        return redirect(url_for('customer_login'))
    initialize_cart()
    cart = session['cart']
    cart_items = []
    total_price = 0
    for id_str, qty in cart.items():
        item_id = int(id_str)
        item = next((i for i in menu if i['id'] == item_id), None)
        if item:
            subtotal = item['price'] * qty
            total_price += subtotal
            cart_items.append({
                'id': item_id, 'name': item['name'], 'price': item['price'], 'quantity': qty, 'subtotal': subtotal
            })
    if request.method == 'POST':
        updated_cart = {}
        for item in cart_items:
            try:
                new_qty = int(request.form.get(f"qty_{item['id']}", 0))
                if new_qty > 0:
                    updated_cart[str(item['id'])] = new_qty
            except:
                continue
        session['cart'] = updated_cart
        flash("Cart updated.")
        return redirect(url_for('view_cart'))
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

# Place order
@app.route('/order', methods=['GET', 'POST'])
def order():
    if not session.get('customer_logged_in'):
        flash("Please login to place order.")
        return redirect(url_for('customer_login'))
    cart = session.get('cart', {})
    if not cart:
        flash("Your cart is empty.")
        return redirect(url_for('index'))
    if request.method == 'POST':
        order_group_id = str(uuid.uuid4())
        customer_username = session['customer_username']
        name = request.form.get('name', '').strip()
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        if not all([name, address, phone, email]):
            flash("Please fill all required fields.")
            return redirect(url_for('order'))
        total_price = 0
        for id_str, qty in cart.items():
            item_id = int(id_str)
            item = next((i for i in menu if i['id'] == item_id), None)
            if not item:
                continue
            line_total = item['price'] * qty
            total_price += line_total
            new_order = Order(
                order_group_id=order_group_id,
                customer_username=customer_username,
                customer_name=name,
                address=address,
                phone=phone,
                email=email,
                item=item['name'],
                quantity=qty,
                total=line_total,
                status='Pending',
                cancelled=False,
                cancellation_reason=None,
                estimated_time=None,
                order_time=datetime.utcnow()
            )
            db.session.add(new_order)
        db.session.commit()
        session.pop('cart', None)
        session['receipt'] = {
            'order_group_id': order_group_id,
            'customer_name': name,
            'address': address,
            'phone': phone,
            'email': email,
            'items': [
                {'name': next(i for i in menu if i['id'] == int(item_id)).get('name'),
                 'quantity': qty,
                 'unit_price': next(i for i in menu if i['id'] == int(item_id)).get('price'),
                 'subtotal': next(i for i in menu if i['id'] == int(item_id)).get('price') * qty}
                for item_id, qty in cart.items()
            ],
            'total_price': total_price,
        }
        return redirect(url_for('receipt'))
    # GET: show order form and cart items
    initialize_cart()
    cart = session['cart']
    cart_items = []
    total_price = 0
    for id_str, qty in cart.items():
        item_id = int(id_str)
        item = next((i for i in menu if i['id'] == item_id), None)
        if item:
            subtotal = item['price'] * qty
            total_price += subtotal
            cart_items.append({'id': item_id, 'name': item['name'], 'price': item['price'], 'quantity': qty, 'subtotal': subtotal})
    return render_template('order.html', menu=menu, cart_items=cart_items, total_price=total_price)

# Receipt
@app.route('/receipt')
def receipt():
    receipt = session.get('receipt')
    if not receipt:
        flash("Receipt not found.")
        return redirect(url_for('index'))
    orders = Order.query.filter_by(order_group_id=receipt['order_group_id']).all()
    if not orders:
        flash("Order data not found.")
        return redirect(url_for('index'))
    utc = pytz.utc
    ist = pytz.timezone('Asia/Kolkata')
    earliest_order_time = min(o.order_time for o in orders)
    try:
        utc_time = utc.localize(earliest_order_time)
    except:
        utc_time = earliest_order_time
    local_order_time = utc_time.astimezone(ist)
    estimated_delivery_time = local_order_time + timedelta(minutes=50)
    order = orders[0]
    return render_template('receipt.html', receipt=receipt, order_row=order, estimated_delivery_time=estimated_delivery_time)

# Track Order
@app.route('/track_order', methods=['GET', 'POST'])
def track_order():
    orders = []
    show_cancel = False
    order_id = None
    if request.method == 'POST':
        order_id = request.form.get('order_id', '').strip()
        email = request.form.get('email', '').strip()
        if order_id and email:
            orders = Order.query.filter_by(order_group_id=order_id, email=email).all()
            if orders:
                show_cancel = not all(o.cancelled or o.status == 'Delivered' for o in orders)
            else:
                flash("No orders found.")
        else:
            flash("Please enter both Order ID and Email.")
    return render_template('track_order.html', orders=orders, show_cancel=show_cancel, order_id=order_id)

# Cancel Order
@app.route('/cancel_order/<int:order_id>/<order_group_id>', methods=['GET', 'POST'])
def cancel_order(order_id, order_group_id):
    if not session.get('customer_logged_in'):
        flash("Please login to cancel orders.")
        return redirect(url_for('customer_login'))
    orders = Order.query.filter_by(order_group_id=order_group_id, customer_username=session['customer_username']).all()
    if not orders or all(o.cancelled or o.status == 'Delivered' for o in orders):
        flash("Order can't be cancelled.")
        return redirect(url_for('track_order'))
    reasons = [
        "Ordered by mistake",
        "Expected delivery time is too long",
        "Found a better price elsewhere",
        "Changed my mind",
        "Items unavailable",
        "Duplicate order",
        "Other (please specify)"
    ]
    if request.method == 'POST':
        selected_reason = request.form.get('reason')
        other_reason = request.form.get('other_reason', '').strip()
        final_reason = other_reason if selected_reason == "Other (please specify)" else selected_reason
        if not final_reason:
            flash("Please provide a valid cancellation reason.")
            return render_template('cancel_order.html', order=orders[0], reasons=reasons)
        for o in orders:
            o.cancelled = True
            o.cancellation_reason = final_reason
            o.status = 'Cancelled'
        db.session.commit()
        flash("Order cancelled successfully.")
        return redirect(url_for('track_order'))
    return render_template('cancel_order.html', order=orders[0], reasons=reasons)

# Admin: View Orders
@app.route('/orders')
def view_orders():
    if not session.get('admin_logged_in'):
        flash("Admin login required.")
        return redirect(url_for('admin_login'))
    orders = Order.query.order_by(Order.order_time.desc()).all()
    return render_template('orders.html', orders=orders)

# Admin: Update order status
@app.route('/admin/orders/update/<int:order_id>', methods=['GET', 'POST'])
def admin_update_order_status(order_id):
    if not session.get('admin_logged_in'):
        flash("Admin login required.")
        return redirect(url_for('admin_login'))
    order = Order.query.get_or_404(order_id)
    statuses = ['Pending', 'Preparing', 'Out for Delivery', 'Delivered', 'Cancelled']
    if request.method == 'POST':
        status = request.form.get('status')
        if status in statuses:
            order.status = status
            db.session.commit()
            flash(f"Order #{order.id} status updated to {status}.")
            return redirect(url_for('view_orders'))
        else:
            flash("Invalid status selected.")
    return render_template('admin_update_order.html', order=order, statuses=statuses)

# Admin: Update estimated time
@app.route('/admin/orders/update_time/<int:order_id>', methods=['GET', 'POST'])
def admin_update_order_time(order_id):
    if not session.get('admin_logged_in'):
        flash("Admin login required.")
        return redirect(url_for('admin_login'))
    order = Order.query.get_or_404(order_id)
    if request.method == 'POST':
        est_time = request.form.get('estimated_time', '').strip()
        order.estimated_time = est_time
        db.session.commit()
        flash(f"Estimated time updated for order #{order.id}")
        return redirect(url_for('view_orders'))
    return render_template('admin_update_order_time.html', order=order)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
