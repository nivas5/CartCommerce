CREATE TABLE IF NOT EXISTS admin_sc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anime TEXT,
    email TEXT UNIQUE,
    apassword TEXT,
    profile_image TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    description TEXT,
    category TEXT,
    price NUMERIC,
    image TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT UNIQUE,
    password TEXT,
    profile_image TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    payment_id TEXT NOT NULL,
    razorpay_order_id TEXT,
    total_amount NUMERIC NOT NULL,
    status TEXT DEFAULT 'Paid',
    payment_status TEXT DEFAULT 'Success',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    product_id INTEGER,
    product_name TEXT NOT NULL,
    product_price NUMERIC NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    product_image TEXT,
    subtotal NUMERIC NOT NULL
);