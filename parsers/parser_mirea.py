# parsers/parser_mirea.py
import os
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# --- sys.path, чтобы common.db_func импортировался ---
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.db_func import (  # noqa: E402
    connect_get_cursor,
    create_news_table,
    create_categories_table,
    create_university_tables,
    get_category_id,
    get_university_id,
    get_last_link,
    insert_news,
    print_all_rows,
)

UNIVERSITY_NAME = "МИРЭА"
REQUEST_TIMEOUT = 10


def normalise_category(input_cat):
    if not input_cat:
        return "Без категории"

    key = input_cat.strip().lower()

    mapping = {
        # Наука и инновации
        "пиш": "Наука и инновации",
        "иии": "Наука и инновации",
        "идеи будущего": "Наука и инновации",
        "химбиотех": "Наука и инновации",
        # Образование
        "математический праздник": "Образование",
        "яндекс лицей": "Образование",
        "мпош": "Образование",
        "мош": "Образование",
        "омо": "Образование",
        "оммо": "Образование",
        "охо": "Образование",
        "всош": "Образование",
        "вош": "Образование",
        "математическая вертикаль": "Образование",
        "предпрофессиональная": "Образование",
        "профориентация": "Образование",
        "многопрофильная инженерная олимпиада «звезда»": "Образование",
        "многопрофильная олимпиада рту мирэа": "Образование",
        "олимпиады": "Образование",
        "конкурсы": "Образование",
        "прикладной конкурс «золотая дюжина»": "Образование",
        "технокалейдоскоп": "Образование",
        "шаг в будущее": "Образование",
        "лига инженеров": "Образование",
        "нто": "Образование",
        # Студенческая жизнь
        "вектор успеха": "Студенческая жизнь",
        "математические бои": "Студенческая жизнь",
        "химические бои": "Студенческая жизнь",
        "химический праздник": "Студенческая жизнь",
        "ученик года": "Студенческая жизнь",
        "интеллектуальные игры": "Студенческая жизнь",
        "киберспорт": "Студенческая жизнь",
        "кибербиатлон": "Студенческая жизнь",
        "ит-вертикаль": "Студенческая жизнь",
        "достижения": "Студенческая жизнь",
        # Объявления и события
        "дод": "Объявления и события",
        "дни открытых дверей": "Объявления и события",
        # Абитуриентам
        "приемная комиссия": "Абитуриентам",
        "приёмная кампания": "Абитуриентам",
        "абитуриентам": "Абитуриентам",
        "навигатор поступления": "Абитуриентам",
        "детский технопарк": "Абитуриентам",
        "фрязино": "Абитуриентам",
        # Сотрудничество
        "партнеры": "Сотрудничество и партнёрство",
        "сотрудничество со школами": "Сотрудничество и партнёрство",
    }

    return mapping.get(key, "Без категории")


def update_db(conn, cur, page, meta, last_link, uni_id):
    try:
        response = requests.get(page, headers=meta, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[parser_mirea] Ошибка запроса {page}: {e}")
        return False

    soup = BeautifulSoup(response.text, "html.parser")
    cards = soup.select(".article-body")

    for card in cards:
        # категория
        ul = card.select_one("ul")
        if ul:
            cats = [x.get_text(strip=True) for x in ul.select("a")]
            cat = normalise_category(cats[0]) if cats else "Без категории"
        else:
            cat = "Без категории"

        a_tag = card.find("a")
        title_tag = card.select_one(".article-header")
        time_tag = card.find("time")
        if not (a_tag and title_tag and time_tag):
            continue

        href = "https://priem.mirea.ru/" + a_tag.get("href", "")

        if href == last_link:
            print("[parser_mirea] Дошли до последней известной — стоп")
            return "Completed"

        dt_iso = time_tag.get("datetime")
        try:
            dt = datetime.fromisoformat(dt_iso).replace(tzinfo=None)
        except (TypeError, ValueError):
            dt = datetime.now()

        intro = card.select_one(".article-introtext")
        content = intro.get_text(strip=True) if intro else "no text"

        cat_id = get_category_id(cur, cat)
        insert_news(cur, conn, title_tag.get_text(strip=True), href,
                    dt, cat_id, uni_id, content)
        print("[parser_mirea] +", href)
        time.sleep(0.3)

    return True


def parse():
    """Функция без аргументов — как требует задание."""
    print("[parser_mirea] Старт")
    conn, cur = connect_get_cursor()
    try:
        create_news_table(cur, conn)
        create_categories_table(cur, conn)
        create_university_tables(cur, conn)

        uni_id = get_university_id(cur, UNIVERSITY_NAME)
        last = get_last_link(cur, UNIVERSITY_NAME)
        print("[parser_mirea] Последняя известная:", last)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept-Language": "ru-RU,ru;q=0.9",
        }

        first = requests.get("https://priem.mirea.ru/news?start=0",
                             headers=headers, timeout=REQUEST_TIMEOUT)
        first.raise_for_status()

        soup = BeautifulSoup(first.text, "html.parser")
        counter = soup.select_one(".com-content-category-blog__counter")
        if not counter:
            print("[parser_mirea] Не найден счётчик страниц")
            return

        try:
            num_of_pages = int(counter.get_text(strip=True).split()[-1])
        except (ValueError, IndexError):
            num_of_pages = 1

        for i in range(num_of_pages):
            url = f"https://priem.mirea.ru/news?start={i * 9}"
            status = update_db(conn, cur, url, headers, last, uni_id)
            if status == "Completed":
                break

        print_all_rows(cur)
    except Exception as e:
        print(f"[parser_mirea] Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    parse()