
import os
import sys
import sqlite3
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from collections import defaultdict
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



BASE_URL = 'https://media.kpfвапu.ru/news/'
CATEGORY = {
    "Наука и инновации":            ["Новости науки", "Новости институтов"],
    "Образование":                  ["Новости образования", "Новости клиники", "Новости лицеев"],
    "Студенческая жизнь":           ["Студенческая жизнь"],
    "Спорт":                        [],
    "Культура и творчество":        [],
    "Международная деятельность":   ["Международное сотрудничество"],
    "Сотрудничество и партнёрство": ["Выпускнику"],
    "Объявления и события":         ["Новости ректора", "Акции, мероприятия"],
    "Абитуриентам":                 ["Абитуриенту"],
    "Без категории":                [],
}
all_category = ["Наука и инновации", "Образование", "Студенческая жизнь", "Спорт",
                "Культура и творчество", "Международная деятельность",
                "Сотрудничество и партнёрство", "Объявления и события",
                "Абитуриентам", "Без категории"]

SERVICE_KEYS = {"Главные новости"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, '..', 'news.db')
MAX_PAGES = 5
INTERVAL = 30
REQUEST_TIMEOUT = 10

CATEGORY_ID = {name: i for i, name in enumerate(all_category, start=1)}
DEFAULT_CATEGORY_ID = CATEGORY_ID["Без категории"]

DEFAULT_UNIVERSITY = "КФУ"
DEFAULT_UNIVERSITY_ID = 1


def init_db(name_bd=DB_NAME):
    """Создаёт таблицы (если их нет) и возвращает connection и cursor."""
    connection = sqlite3.connect(name_bd)
    cursor = connection.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_categories (
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS universities (
            university_id INTEGER NOT NULL,
            name TEXT NOT NULL
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            published_date TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            university_id INTEGER NOT NULL,
            added_at TEXT DEFAULT (datetime('now')),
            content TEXT DEFAULT 'no text'
        );
    ''')

    # добавляем content, если его нет
    cursor.execute("PRAGMA table_info(news)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'content' not in columns:
        cursor.execute("ALTER TABLE news ADD COLUMN content TEXT DEFAULT 'no text'")
        print("[MIGRATION] Добавлен столбец content в news")

    for name in all_category:
        cursor.execute('SELECT 1 FROM news_categories WHERE category_id = ?', (CATEGORY_ID[name],))
        if cursor.fetchone() is None:
            cursor.execute(
                'INSERT INTO news_categories (category_id, name) VALUES (?, ?)',
                (CATEGORY_ID[name], name)
            )

    cursor.execute('SELECT 1 FROM universities WHERE university_id = ?', (DEFAULT_UNIVERSITY_ID,))
    if cursor.fetchone() is None:
        cursor.execute(
            'INSERT INTO universities (university_id, name) VALUES (?, ?)',
            (DEFAULT_UNIVERSITY_ID, DEFAULT_UNIVERSITY)
        )

    connection.commit()
    return connection, cursor


def get_key_to_category():
    mapping = {}
    for cat, keys in CATEGORY.items():
        cat_id = CATEGORY_ID[cat]
        for k in keys:
            mapping[k] = cat_id
    return mapping


def get_university_id(cursor, name=DEFAULT_UNIVERSITY):
    cursor.execute('SELECT university_id FROM universities WHERE name = ?', (name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    # явно передаём university_id = MAX + 1
    row = cursor.execute(
        'SELECT COALESCE(MAX(university_id), 0) + 1 FROM universities'
    ).fetchone()
    new_id = row[0]

    cursor.execute(
        'INSERT INTO universities (university_id, name) VALUES (?, ?)',
        (new_id, name)
    )
    return new_id


def fetch_html(url):
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Ошибка запроса {url}: {e}")
        return None


def parse_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    for block in soup.select('.newsItem'):
        link_tag = block.select_one('.boldLink')
        date_tag = block.select_one('.newsItem-date')
        if not link_tag or not date_tag:
            continue

        content_tag = block.select_one('.newsItem-text')
        content = content_tag.get_text(' ', strip=True) if content_tag else 'no text'

        raw_date = date_tag.text.strip()
        try:
            dt = datetime.strptime(raw_date, '%d.%m.%Y')
            published_date = dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            published_date = raw_date

        items.append({
            'title': link_tag.text.strip(),
            'link': 'https://media.kpfu.ru' + link_tag.get('href', ''),
            'published_date': published_date,
            'content': content,
        })
    return items


def category_url(url):
    html = fetch_html(url)
    if html is None:
        return DEFAULT_CATEGORY_ID
    soup = BeautifulSoup(html, 'html.parser')
    block = soup.select_one('.newsCart-cat')
    if not block:
        return DEFAULT_CATEGORY_ID

    text = block.get_text()
    key_to_category = get_key_to_category()

    for key, cat_id in key_to_category.items():
        if key in text:
            return cat_id
    return DEFAULT_CATEGORY_ID


def get_next_page_url(html):
    soup = BeautifulSoup(html, 'html.parser')
    next_btn = soup.select_one('.pager__item.pager__item--next a')
    if not next_btn:
        return None
    return BASE_URL + next_btn.get('href', '')


def save_news(cursor, item):
    """INSERT OR IGNORE — если link уже есть, строка не вставится."""
    category_id = category_url(item['link'])
    university_id = get_university_id(cursor, DEFAULT_UNIVERSITY)
    content = item.get('content', 'no text')

    cursor.execute(
        '''INSERT OR IGNORE INTO news
           (title, link, published_date, category_id, university_id, content)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (item['title'], item['link'], item['published_date'],
         category_id, university_id, content)
    )

    if cursor.rowcount == 0:
        return False   # дубликат

    print('Найдена новая новость:', item['link'], item['title'],
          item['published_date'], '| cat_id =', category_id,
          '| uni_id =', university_id)
    return True


def parse_all_pages(cursor, max_pages=MAX_PAGES):
    page = 1
    monthly_count = defaultdict(int)
    current_url = BASE_URL
    total_new = 0

    while page <= max_pages:
        html = fetch_html(current_url)
        if html is None:
            break

        items = parse_page(html)
        if not items:
            print(f"Страница {page} пуста, завершаем.")
            break

        duplicate_found = False
        for item in items:
            if not save_news(cursor, item):
                duplicate_found = True
                break
            total_new += 1
            time.sleep(0.3)

        if duplicate_found:
            print("Найден дубликат, завершаем.")
            break

        next_url = get_next_page_url(html)
        if not next_url:
            print("Кнопка 'Следующая' не найдена, завершаем.")
            break

        current_url = next_url
        print(f"--> Переход на страницу {page + 1}: {current_url}")
        page += 1

    return page, total_new, monthly_count


def print_report(page, total_new, monthly_count):
    print(f"Обработано страниц: {page}, новых новостей: {total_new}")


def parse():
    """Функция БЕЗ аргументов, как требует задание."""
    print("[parser_kfu] Старт")
    connection, cursor = init_db()
    try:
        page, total_new, monthly_count = parse_all_pages(cursor)
        connection.commit()
        print_report(page, total_new, monthly_count)
    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        connection.rollback()
    finally:
        connection.close()
    print("[parser_kfu] Готово")


if __name__ == '__main__':
    parse()