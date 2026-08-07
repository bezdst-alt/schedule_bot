import sqlite3

DB_PATH = "schedule.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            graphic_type TEXT NOT NULL,
            start_date TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            shift_type TEXT NOT NULL,
            reason TEXT DEFAULT 'РВ',
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            UNIQUE(employee_id, date, shift_type)
        )
    """)
    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_PATH)

def add_employee(name, graphic_type, start_date):
    conn = get_connection()
    try:
        conn.execute("INSERT INTO employees (name, graphic_type, start_date) VALUES (?, ?, ?)",
                     (name, graphic_type, start_date))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def remove_employee(name):
    conn = get_connection()
    conn.execute("DELETE FROM employees WHERE name = ?", (name,))
    conn.execute("DELETE FROM overrides WHERE employee_id NOT IN (SELECT id FROM employees)")
    conn.commit()
    conn.close()

def list_employees():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, graphic_type, start_date FROM employees ORDER BY name").fetchall()
    conn.close()
    return rows

def add_override(employee_id, date_str, shift_type, reason="РВ"):
    conn = get_connection()
    try:
        conn.execute("INSERT OR REPLACE INTO overrides (employee_id, date, shift_type, reason) VALUES (?, ?, ?, ?)",
                     (employee_id, date_str, shift_type, reason))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def list_overrides_for_date(date_str):
    conn = get_connection()
    rows = conn.execute("""
        SELECT o.id, e.name, o.date, o.shift_type, o.reason
        FROM overrides o
        JOIN employees e ON e.id = o.employee_id
        WHERE o.date = ?
        ORDER BY e.name
    """, (date_str,)).fetchall()
    conn.close()
    return rows

def add_recipient(telegram_id, name=""):
    conn = get_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO recipients (telegram_id, name) VALUES (?, ?)",
                     (telegram_id, name))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def remove_recipient(telegram_id):
    conn = get_connection()
    conn.execute("DELETE FROM recipients WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()

def list_recipients():
    conn = get_connection()
    rows = conn.execute("SELECT telegram_id, name FROM recipients ORDER BY name").fetchall()
    conn.close()
    return rows
