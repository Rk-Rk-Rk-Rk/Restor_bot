"""Слой работы с SQLite: все CRUD-операции ресторанного бота."""

import sqlite3
import json
import uuid
import logging
from contextlib import contextmanager
from config import DB_NAME

logger = logging.getLogger(__name__)


#Коннект к БД
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


#Инициализация БД
def init_db():
    with get_connection() as conn:
        c = conn.cursor()

        c.execute('''
        CREATE TABLE IF NOT EXISTS tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            seats INTEGER NOT NULL,
            status TEXT DEFAULT 'free',
            neighbors TEXT DEFAULT '[]'
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            phone_number TEXT,
            role TEXT DEFAULT 'user',
            is_regular BOOLEAN DEFAULT 0
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            table_id INTEGER,
            booking_date TEXT,
            booking_time TEXT,
            people_count INTEGER,
            pre_order_sum REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(table_id) REFERENCES tables(id)
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            category TEXT
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_uuid TEXT UNIQUE,
            initiator_id INTEGER,
            booking_id INTEGER,
            status TEXT DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(booking_id) REFERENCES bookings(id)
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            item_id INTEGER,
            quantity INTEGER DEFAULT 1,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(item_id) REFERENCES menu(id)
        )''')

        c.execute('''
        CREATE TABLE IF NOT EXISTS order_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            user_id INTEGER,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(order_id) REFERENCES orders(id),
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            UNIQUE(order_id, user_id)
        )''')
        for stmt in [
            "ALTER TABLE orders ADD COLUMN booking_id INTEGER",
            "ALTER TABLE bookings ADD COLUMN booking_date TEXT",
        ]:
            try:
                c.execute(stmt)
            except sqlite3.OperationalError:
                pass

    logger.info("База данных инициализирована")

#  Меню 
def add_menu_item(name, price, description="", category="main"):
    with get_connection() as conn:
        conn.cursor().execute(
            'INSERT INTO menu (name, price, description, category) VALUES (?, ?, ?, ?)',
            (name, price, description, category))


def delete_menu_item(item_id):
    with get_connection() as conn:
        conn.cursor().execute('DELETE FROM menu WHERE id = ?', (item_id,))


def get_menu_page(page=1, per_page=5):
    with get_connection() as conn:
        c = conn.cursor()
        offset = (page - 1) * per_page
        c.execute('SELECT * FROM menu LIMIT ? OFFSET ?', (per_page, offset))
        items = [dict(row) for row in c.fetchall()]
        c.execute('SELECT count(*) FROM menu')
        total = c.fetchone()[0]
    return items, (offset + per_page) < total


def get_menu_item(item_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM menu WHERE id = ?', (item_id,))
        row = c.fetchone()
    return dict(row) if row else None


def get_all_menu_items():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM menu ORDER BY category, name')
        return [dict(row) for row in c.fetchall()]


#  Заказы
def create_order(initiator_id, booking_id=None):
    with get_connection() as conn:
        c = conn.cursor()
        link = str(uuid.uuid4())[:8]
        c.execute('INSERT INTO orders (link_uuid, initiator_id, booking_id) VALUES (?, ?, ?)',
                  (link, initiator_id, booking_id))
        order_id = c.lastrowid
    return order_id, link


def get_order_by_uuid(link_uuid):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE link_uuid = ?', (link_uuid,))
        row = c.fetchone()
    return dict(row) if row else None


def get_active_order_by_user(user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            'SELECT * FROM orders WHERE initiator_id = ? AND status="open" ORDER BY id DESC LIMIT 1',
            (user_id,))
        row = c.fetchone()
    return dict(row) if row else None


def add_to_cart(order_id, user_id, item_id):
    with get_connection() as conn:
        conn.cursor().execute(
            'INSERT INTO cart_items (order_id, user_id, item_id) VALUES (?, ?, ?)',
            (order_id, user_id, item_id))


def remove_cart_item(cart_item_id):
    """Удалить позицию из корзины по ID записи."""
    with get_connection() as conn:
        conn.cursor().execute('DELETE FROM cart_items WHERE id = ?', (cart_item_id,))


def get_cart_items(order_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT ci.id as cart_id, ci.*, m.name, m.price, u.full_name
            FROM cart_items ci
            JOIN menu m ON ci.item_id = m.id
            LEFT JOIN users u ON ci.user_id = u.user_id
            WHERE ci.order_id = ?
        ''', (order_id,))
        return [dict(row) for row in c.fetchall()]


def get_order_total(order_id):
    items = get_cart_items(order_id)
    return sum(item['price'] for item in items)


def add_order_participant(order_id, user_id):
    with get_connection() as conn:
        conn.cursor().execute(
            'INSERT OR IGNORE INTO order_participants (order_id, user_id) VALUES (?, ?)',
            (order_id, user_id))


def get_order_participants(order_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT op.*, u.full_name, u.username, u.user_id
            FROM order_participants op
            JOIN users u ON op.user_id = u.user_id
            WHERE op.order_id = ?
        ''', (order_id,))
        return [dict(row) for row in c.fetchall()]


def get_order_by_id(order_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        row = c.fetchone()
    return dict(row) if row else None


def get_order_by_booking_id(booking_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE booking_id = ? AND status="open"', (booking_id,))
        row = c.fetchone()
    return dict(row) if row else None


def close_order(order_id):
    with get_connection() as conn:
        conn.cursor().execute('UPDATE orders SET status="closed" WHERE id = ?', (order_id,))


#  Пользователи
def add_user(user_id, username, full_name, phone_number=None, role='user'):
    with get_connection() as conn:
        conn.cursor().execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name, phone_number, role)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, full_name, phone_number, role))


def get_user(user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
    return dict(row) if row else None


def get_all_users():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users')
        return [dict(row) for row in c.fetchall()]


def update_user_phone(user_id, phone):
    with get_connection() as conn:
        conn.cursor().execute('UPDATE users SET phone_number = ? WHERE user_id = ?', (phone, user_id))


def set_user_role(user_id, role):
    with get_connection() as conn:
        conn.cursor().execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))


def delete_user(user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('DELETE FROM bookings WHERE user_id = ?', (user_id,))
        c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))

#  Столы
def get_all_tables():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM tables')
        rows = c.fetchall()

    tables_dict = {}
    for row in rows:
        tables_dict[row['id']] = {
            "name": row['name'],
            "seats": row['seats'],
            "status": row['status'],
            "neighbors": json.loads(row['neighbors']),
        }
    return tables_dict


def add_table(name, seats, neighbors_list=None):
    if neighbors_list is None:
        neighbors_list = []
    with get_connection() as conn:
        conn.cursor().execute(
            'INSERT INTO tables (name, seats, neighbors) VALUES (?, ?, ?)',
            (name, seats, json.dumps(neighbors_list)))


def delete_table(t_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('DELETE FROM bookings WHERE table_id=?', (t_id,))
        c.execute('DELETE FROM tables WHERE id=?', (t_id,))


def reset_all_tables():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('UPDATE tables SET status="free"')
        c.execute('UPDATE bookings SET status="cancelled" WHERE status="active"')


#  Брони
def add_booking(user_id, table_id, booking_date, booking_time, people_count, pre_order_sum=0):
    with get_connection() as conn:
        conn.cursor().execute('''
            INSERT INTO bookings (user_id, table_id, booking_date, booking_time, people_count, pre_order_sum)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, table_id, booking_date, booking_time, people_count, pre_order_sum))


def get_active_booking(user_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT b.*, t.name as table_name
            FROM bookings b
            JOIN tables t ON b.table_id = t.id
            WHERE b.user_id = ? AND b.status = 'active'
            ORDER BY b.id DESC LIMIT 1
        ''', (user_id,))
        row = c.fetchone()
    return dict(row) if row else None


def get_all_bookings_full():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT b.id, b.booking_date, b.booking_time, b.people_count, b.status,
                   b.pre_order_sum,
                   u.full_name as user_name, u.phone_number,
                   t.name as table_name
            FROM bookings b
            LEFT JOIN users u ON b.user_id = u.user_id
            LEFT JOIN tables t ON b.table_id = t.id
            ORDER BY b.created_at DESC
        ''')
        return [dict(row) for row in c.fetchall()]


def delete_booking(booking_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM bookings WHERE id=?', (booking_id,))


def cancel_booking(user_id):
    booking = get_active_booking(user_id)
    if not booking:
        return False
    with get_connection() as conn:
        conn.cursor().execute('UPDATE bookings SET status="cancelled" WHERE id = ?', (booking['id'],))
    return True


def get_table_bookings(table_id, booking_date=None):
    with get_connection() as conn:
        c = conn.cursor()
        if booking_date:
            c.execute(
                'SELECT booking_time FROM bookings WHERE table_id = ? AND booking_date = ? AND status = "active"',
                (table_id, booking_date))
        else:
            c.execute(
                'SELECT booking_time FROM bookings WHERE table_id = ? AND status = "active"',
                (table_id,))
        return [row['booking_time'] for row in c.fetchall()]


def get_user_bookings_history(user_id, limit=10):
    """История броней пользователя."""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT b.*, t.name as table_name
            FROM bookings b
            JOIN tables t ON b.table_id = t.id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        return [dict(row) for row in c.fetchall()]


#  Статистика
def get_stats():
    with get_connection() as conn:
        c = conn.cursor()

        c.execute('SELECT count(*) FROM users')
        users_count = c.fetchone()[0]

        c.execute('SELECT count(*) FROM bookings WHERE status = "active"')
        active_bookings = c.fetchone()[0]

        c.execute('SELECT count(*) FROM bookings')
        total_bookings = c.fetchone()[0]

        c.execute('SELECT count(*) FROM orders WHERE status = "open"')
        open_orders = c.fetchone()[0]

        c.execute('SELECT count(*) FROM orders WHERE status = "closed"')
        closed_orders = c.fetchone()[0]

        c.execute('SELECT COALESCE(SUM(pre_order_sum), 0) FROM bookings WHERE status = "active"')
        preorder_sum = c.fetchone()[0]

        c.execute('SELECT count(*) FROM menu')
        menu_count = c.fetchone()[0]

        c.execute('SELECT count(*) FROM tables')
        tables_count = c.fetchone()[0]

    return {
        "users": users_count,
        "active_bookings": active_bookings,
        "total_bookings": total_bookings,
        "open_orders": open_orders,
        "closed_orders": closed_orders,
        "preorder_sum": preorder_sum,
        "menu_count": menu_count,
        "tables_count": tables_count,
    }
