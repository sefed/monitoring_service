import sqlite3

conn = sqlite3.connect("users.db")
cur = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT
    );
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS user_categories (
        user_id INTEGER NOT NULL, category_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
""")

# Пользователи
cur.executemany("INSERT OR IGNORE INTO users (id, name, email) VALUES (?, ?, ?)", [
    (1, "Иван",   "ivan@example.com"),
    (2, "Мария",  "maria@example.com"),
    (3, "Пётр",   "petr@example.com"),
    (4, "Анна",   "anna@example.com"),
    (5, "Сергей", "sergey@example.com"),
])

# Интересы (2-4 категории на пользователя)
cur.executemany("INSERT INTO user_categories (user_id, category_id) VALUES (?, ?)", [
    (1, 1), (1, 2), (1, 8),          # Иван: Наука, Образование, Объявления
    (2, 3), (2, 5), (2, 9),          # Мария: Студ. жизнь, Культура, Абитуриентам
    (3, 4), (3, 6),                   # Пётр: Спорт, Международка
    (4, 7), (4, 2), (4, 1),          # Анна: Сотрудничество, Образование, Наука
    (5, 9), (5, 8),                   # Сергей: Абитуриентам, Объявления
])

conn.commit()
conn.close()
print("users.db заполнена тестовыми пользователями")