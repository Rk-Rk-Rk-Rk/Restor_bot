import sqlite3
import json

DB_NAME = "restaurant.db"

def init_db():
    """Создает таблицы, если их нет"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        seats INTEGER NOT NULL,
        status TEXT DEFAULT 'free',
        neighbors TEXT DEFAULT '[]' 
    )
    ''')
    conn.commit()
    conn.close()

# === ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ ===

def add_table(name, seats, neighbors_list=[]):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Сохраняем список соседей как JSON-строку "[1, 2]"
    neighbors_json = json.dumps(neighbors_list)
    cursor.execute('INSERT INTO tables (name, seats, neighbors) VALUES (?, ?, ?)', 
                   (name, seats, neighbors_json))
    conn.commit()
    conn.close()

def delete_table(table_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tables WHERE id = ?', (table_id,))
    conn.commit()
    conn.close()

def get_all_tables():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Чтобы обращаться по именам колонок
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tables')
    rows = cursor.fetchall()
    conn.close()
    
    # Превращаем результат БД в удобный словарь Python
    tables_dict = {}
    for row in rows:
        tables_dict[row['id']] = {
            "name": row['name'],
            "seats": row['seats'],
            "status": row['status'],
            "neighbors": json.loads(row['neighbors']) # Превращаем строку "[]" обратно в список
        }
    return tables_dict

def update_status(table_id, status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE tables SET status = ? WHERE id = ?', (status, table_id))
    conn.commit()
    conn.close()

def update_neighbors(table_id, neighbors_list):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    neighbors_json = json.dumps(neighbors_list)
    cursor.execute('UPDATE tables SET neighbors = ? WHERE id = ?', (neighbors_json, table_id))
    conn.commit()
    conn.close()
