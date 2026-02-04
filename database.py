import sqlite3
import json
from config import DB_NAME

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # база столов
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        seats INTEGER NOT NULL,
        status TEXT DEFAULT 'free',
        neighbors TEXT DEFAULT '[]'
    )
    ''')

    # база пользователей
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        phone_number TEXT,
        role TEXT DEFAULT 'user',
        is_regular BOOLEAN DEFAULT 0
    )
    ''')
    
    # база бронирований
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        table_id INTEGER,
        booking_time TEXT,
        people_count INTEGER,
        pre_order_sum REAL DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(table_id) REFERENCES tables(id)
    )
    ''')

    # база меню
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        category TEXT
    )
    ''')

    # база заказов (совместных)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        link_uuid TEXT UNIQUE,
        initiator_id INTEGER,
        booking_id INTEGER,
        status TEXT DEFAULT 'open',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(booking_id) REFERENCES bookings(id)
    )
    ''')
    
    # Миграция (если столбец не существует - грубый хак для dev)
    try:
        cursor.execute("ALTER TABLE orders ADD COLUMN booking_id INTEGER")
    except:
        pass
    
    
    # База корзины
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cart_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        item_id INTEGER,
        quantity INTEGER DEFAULT 1,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(item_id) REFERENCES menu(id)
    )
    ''')

    # База участников заказа
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS order_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        user_id INTEGER,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        UNIQUE(order_id, user_id)
    )
    ''')

    conn.commit()
    conn.close()


# Меню
def add_menu_item(name, price, description="", category="main"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO menu (name, price, description, category) VALUES (?, ?, ?, ?)', 
                   (name, price, description, category))
    conn.commit()
    conn.close()

def delete_menu_item(item_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM menu WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()

def get_menu_page(page=1, per_page=5):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    offset = (page - 1) * per_page
    cursor.execute('SELECT * FROM menu LIMIT ? OFFSET ?', (per_page, offset))
    items = [dict(row) for row in cursor.fetchall()]
    cursor.execute('SELECT count(*) FROM menu')
    total_count = cursor.fetchone()[0]
    has_next = (offset + per_page) < total_count
    
    conn.close()
    return items, has_next

def get_menu_item(item_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM menu WHERE id = ?', (item_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


import uuid


def create_order(initiator_id, booking_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    link_uuid = str(uuid.uuid4())[:8] 
    cursor.execute('INSERT INTO orders (link_uuid, initiator_id, booking_id) VALUES (?, ?, ?)', (link_uuid, initiator_id, booking_id))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id, link_uuid

def get_order_by_uuid(link_uuid):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE link_uuid = ?', (link_uuid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_active_order_by_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE initiator_id = ? AND status="open" ORDER BY id DESC LIMIT 1', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def add_to_cart(order_id, user_id, item_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cart_items (order_id, user_id, item_id) VALUES (?, ?, ?)', (order_id, user_id, item_id))
    conn.commit()
    conn.close()

def get_cart_items(order_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ci.*, m.name, m.price, u.full_name 
        FROM cart_items ci
        JOIN menu m ON ci.item_id = m.id
        LEFT JOIN users u ON ci.user_id = u.user_id
        WHERE ci.order_id = ?
    ''', (order_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_order_total(order_id):
    items = get_cart_items(order_id)
    return sum(item['price'] for item in items)


def add_order_participant(order_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO order_participants (order_id, user_id) VALUES (?, ?)', (order_id, user_id))
    conn.commit()
    conn.close()

def get_order_participants(order_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT op.*, u.full_name, u.username, u.user_id 
        FROM order_participants op
        JOIN users u ON op.user_id = u.user_id
        WHERE op.order_id = ?
    ''', (order_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_order_by_id(order_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_order_by_booking_id(booking_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE booking_id = ? AND status="open"', (booking_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def close_order(order_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET status="closed" WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()


def add_user(user_id, username, full_name, phone_number=None, role='user'):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, full_name, phone_number, role)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, full_name, phone_number, role))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_users():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_user_phone(user_id, phone):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET phone_number = ? WHERE user_id = ?', (phone, user_id))
    conn.commit()
    conn.close()

def set_user_role(user_id, role):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON') 
    cursor.execute('DELETE FROM bookings WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Столы
def get_all_tables():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tables')
    rows = cursor.fetchall()
    conn.close()
    
    tables_dict = {}
    for row in rows:
        tables_dict[row['id']] = {
            "name": row['name'],
            "seats": row['seats'],
            "status": row['status'],
            "neighbors": json.loads(row['neighbors'])
        }
    return tables_dict

def add_table(name, seats, neighbors_list=[]):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    neighbors_json = json.dumps(neighbors_list)
    cursor.execute('INSERT INTO tables (name, seats, neighbors) VALUES (?, ?, ?)', (name, seats, neighbors_json))
    conn.commit()
    conn.close()

def delete_table(t_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('PRAGMA foreign_keys = ON')
    cursor.execute('DELETE FROM bookings WHERE table_id=?', (t_id,))
    cursor.execute('DELETE FROM tables WHERE id=?', (t_id,))
    conn.commit()
    conn.close()

def reset_all_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE tables SET status="free"')
    cursor.execute('UPDATE bookings SET status="cancelled" WHERE status="active"')
    conn.commit()
    conn.close()

#Брони
def add_booking(user_id, table_id, booking_time, people_count, pre_order_sum=0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Создаем бронь
    cursor.execute('''
        INSERT INTO bookings (user_id, table_id, booking_time, people_count, pre_order_sum)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, table_id, booking_time, people_count, pre_order_sum))
    
    # Обновляем статус стола
    cursor.execute('UPDATE tables SET status="busy" WHERE id = ?', (table_id,))
    
    conn.commit()
    conn.close()

def get_active_booking(user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.*, t.name as table_name 
        FROM bookings b
        JOIN tables t ON b.table_id = t.id
        WHERE b.user_id = ? AND b.status = 'active'
        ORDER BY b.id DESC LIMIT 1
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_bookings_full():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.id, b.booking_time, b.people_count, b.status,
               u.full_name as user_name, u.phone_number,
               t.name as table_name
        FROM bookings b
        LEFT JOIN users u ON b.user_id = u.user_id
        LEFT JOIN tables t ON b.table_id = t.id
        ORDER BY b.created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
#Удаление брони 
def delete_booking(booking_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Если стол пользователем уже зщанят стол
    cursor.execute('SELECT table_id FROM bookings WHERE id=?', (booking_id,))
    row = cursor.fetchone()
    if row:
        t_id = row[0]
        cursor.execute('UPDATE tables SET status="free" WHERE id=?', (t_id,))
    
    cursor.execute('DELETE FROM bookings WHERE id=?', (booking_id,))
    conn.commit()
    conn.close()
# Отмена брони
def cancel_booking(user_id):
    booking = get_active_booking(user_id)
    if booking:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('UPDATE bookings SET status="cancelled" WHERE id = ?', (booking['id'],))
        cursor.execute('UPDATE tables SET status="free" WHERE id = ?', (booking['table_id'],))
        conn.commit()
        conn.close()
        return True
    return False
