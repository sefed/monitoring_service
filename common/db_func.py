import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_DB = os.path.join(BASE_DIR, "news.db")


def connect_get_cursor(db=NEWS_DB):
    """Открывает соединение и возвращает (conn, cursor)."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()
    return conn, cur


def create_news_table(cursor, conn):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            title          TEXT NOT NULL,
            link           TEXT UNIQUE NOT NULL,
            published_date TEXT NOT NULL,
            category_id    INTEGER NOT NULL,
            university_id  INTEGER NOT NULL,
            content        TEXT DEFAULT 'no text',
            added_at       TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()


def create_categories_table(cursor, conn):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_categories (
            category_id INTEGER PRIMARY KEY,
            name        TEXT NOT NULL
        );
    """)
    cnt = cursor.execute("SELECT COUNT(*) FROM news_categories").fetchone()[0]
    if cnt == 0:
        cursor.executemany(
            "INSERT INTO news_categories (category_id, name) VALUES (?, ?)",
            [
                (1,  "Наука и инновации"),
                (2,  "Образование"),
                (3,  "Студенческая жизнь"),
                (4,  "Спорт"),
                (5,  "Культура и творчество"),
                (6,  "Международная деятельность"),
                (7,  "Сотрудничество и партнёрство"),
                (8,  "Объявления и события"),
                (9,  "Абитуриентам"),
                (10, "Без категории"),
            ]
        )
    conn.commit()


def create_university_tables(cursor, conn):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS universities (
            university_id INTEGER PRIMARY KEY,
            name          TEXT NOT NULL
        );
    """)
    cnt = cursor.execute("SELECT COUNT(*) FROM universities").fetchone()[0]
    if cnt == 0:
        cursor.executemany(
            "INSERT INTO universities (university_id, name) VALUES (?, ?)",
            [
                (1, "КФУ"),
                (2, "МИРЭА"),
                (3, "ВШЭ"),
                (4, "МАИ"),
                (5, "МГУ"),
                (6, "СПбГУ"),
                (7, "РЭУ"),
                (8, "МИФИ"),
            ]
        )
    conn.commit()


def get_category_id(cursor, cat_name):
    row = cursor.execute(
        "SELECT category_id FROM news_categories WHERE name = ?", (cat_name,)
    ).fetchone()
    if row:
        return row[0]
    row = cursor.execute(
        "SELECT category_id FROM news_categories WHERE name = 'Без категории'"
    ).fetchone()
    return row[0] if row else 10


def get_university_id(cursor, uni_name):
    row = cursor.execute(
        "SELECT university_id FROM universities WHERE name = ?", (uni_name,)
    ).fetchone()
    if row:
        return row[0]
    new_id = cursor.execute(
        "SELECT COALESCE(MAX(university_id), 0) + 1 FROM universities"
    ).fetchone()[0]
    cursor.execute(
        "INSERT INTO universities (university_id, name) VALUES (?, ?)",
        (new_id, uni_name)
    )
    return new_id


def get_last_link(cursor, university_name="МИРЭА"):
    row = cursor.execute("""
        SELECT n.link
        FROM news n
        JOIN universities u ON u.university_id = n.university_id
        WHERE u.name = ?
        ORDER BY n.published_date DESC
        LIMIT 1
    """, (university_name,)).fetchone()
    return row[0] if row else None


def insert_news(cursor, conn, title, link, dt, category_id,
                university_id, content="no text"):
    cursor.execute("""
        INSERT OR IGNORE INTO news
            (title, link, published_date, category_id, university_id, content)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, link, dt, category_id, university_id, content))
    conn.commit()


def print_all_rows(cursor):
    cursor.execute("SELECT * FROM news")
    for row in cursor.fetchall():
        print(row)
