# parsers/parser_hse.py
import os
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db_func import (  # noqa: E402
    connect_get_cursor,
    create_news_table,
    create_categories_table,
    create_university_tables,
    get_category_id,
    get_university_id,
)

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE = "https://www.hse.ru/news/"
UNIVERSITY_NAME = "ВШЭ"
PAGES_PER_CATEGORY = 5
REQUEST_TIMEOUT = 10

MONTHS = {
    "янв": "01", "фев": "02", "мар": "03", "апр": "04",
    "май": "05", "мая": "05", "июн": "06", "июл": "07",
    "авг": "08", "сен": "09", "окт": "10", "ноя": "11", "дек": "12",
}

# пути сайта -> категории из задания
CATEGORIES = {
    "admission/":     "Абитуриентам",
    "edu/":           "Образование",
    "science/":       "Наука и инновации",
    "expertise/":     "Сотрудничество и партнёрство",
    "community/":     "Культура и творчество",
    "communication/": "Международная деятельность",
    "life/":          "Студенческая жизнь",
}


def parse_date(item):
    d = item.select_one("div.post-meta__day")
    m = item.select_one("div.post-meta__month")
    y = item.select_one("div.post-meta__year")
    if not (d and m and y):
        return None
    m_num = MONTHS.get(m.get_text(strip=True).lower()[:3])
    if not m_num:
        return None
    return f"{y.get_text(strip=True)}-{m_num}-{d.get_text(strip=True).zfill(2)} 00:00:00"


def parse_one_page(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for item in soup.select("div.post"):
        h2 = item.find("h2")
        a = h2.find("a") if h2 else None
        if not a:
            continue
        dt = parse_date(item)
        if not dt:
            continue


        content_block = item.select_one("div.post__text")
        if content_block:
            paragraphs = content_block.find_all("p")
            if paragraphs:
                content = " ".join(p.get_text(" ", strip=True) for p in paragraphs)
            else:
                content = content_block.get_text(" ", strip=True)
        else:
            content = "no text"

        out.append({
            "title": a.get_text(strip=True),
            "link": urljoin(base_url, a["href"]),
            "published_date": dt,
            "content": content,   # ← НОВОЕ
        })
    return out


def parse():
    """Функция без аргументов — как требует задание."""
    print("[parser_hse] Старт")
    conn, cur = connect_get_cursor()
    try:
        create_news_table(cur, conn)
        create_categories_table(cur, conn)
        create_university_tables(cur, conn)
        uni_id = get_university_id(cur, UNIVERSITY_NAME)

        total_new = 0

        for path, cat_name in CATEGORIES.items():
            cat_id = get_category_id(cur, cat_name)

            for page in range(1, PAGES_PER_CATEGORY + 1):
                url = BASE + path if page == 1 else BASE + path + f"page{page}.html"
                try:
                    r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                    r.raise_for_status()
                except requests.RequestException as e:
                    print(f"[parser_hse] Ошибка {url}: {e}")
                    continue

                html = r.text
                items = parse_one_page(html, url)
                if not items:
                    break  # страницы в категории кончились

                stop = False
                for it in items:
                    cur.execute("""
                        INSERT OR IGNORE INTO news
                            (title, link, published_date, category_id,
                             university_id, content)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (it["title"], it["link"], it["published_date"],
                          cat_id, uni_id, it.get("content", "no text")))
                    conn.commit()
                    if cur.rowcount == 0:
                        stop = True
                        break
                    total_new += 1
                    print(f"[parser_hse] + {it['title'][:60]}... ({cat_name})")
                    time.sleep(0.2)

                if stop:
                    break

        print(f"[parser_hse] Готово, новых: {total_new}")
    except Exception as e:
        print(f"[parser_hse] Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    parse()
