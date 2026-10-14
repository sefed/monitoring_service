import importlib.util
import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def setup_logging(log_file: str) -> None:
    """Настраивает логирование в файл и в консоль."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )



def load_config(path: str = CONFIG_PATH) -> dict:
    """Читает config.json и делает относительные пути абсолютными."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Конфиг не найден: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # делаем пути абсолютными относительно корня проекта
    for key in ("news_db", "users_db", "output_file", "parsers_dir", "log_file"):
        if key in config and not os.path.isabs(config[key]):
            config[key] = os.path.join(BASE_DIR, config[key])

    return config



def run_all_parsers(parsers_dir: str) -> int:
    """
    Динамически импортирует все *.py из parsers_dir (кроме __init__.py)
    и вызывает в каждом функцию parse() без аргументов.

    Возвращает количество успешно выполненных парсеров.
    """
    if not os.path.isdir(parsers_dir):
        logging.error(f"Папка парсеров не найдена: {parsers_dir}")
        return 0

    # нужно, чтобы парсеры могли делать "from common.db_func import ..."
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)

    ran = 0
    files = sorted(f for f in os.listdir(parsers_dir)
                   if f.endswith(".py") and f != "__init__.py")

    if not files:
        logging.warning(f"В папке {parsers_dir} нет парсеров")
        return 0

    for filename in files:
        filepath = os.path.join(parsers_dir, filename)
        module_name = filename[:-3]

        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                logging.error(f"Не удалось создать spec для {filename}")
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logging.error(f"Ошибка импорта {filename}: {e}")
            logging.debug(traceback.format_exc())
            continue

        parse_func = getattr(module, "parse", None)
        if not callable(parse_func):
            logging.warning(f"В {filename} нет функции parse() — пропускаю")
            continue

        logging.info(f"Запуск парсера: {filename}")
        try:
            parse_func()
            ran += 1
            logging.info(f"Парсер {filename} завершён успешно")
        except Exception as e:
            logging.error(f"Ошибка в {filename}: {e}")
            logging.debug(traceback.format_exc())

    return ran



def init_users_db(path: str) -> None:
    """Создаёт таблицы users и user_categories, если их нет."""
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id    INTEGER PRIMARY KEY,
            name  TEXT NOT NULL,
            email TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_categories (
            user_id     INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()



def write_send_list(output_file: str, distribution: dict) -> None:
    """
    distribution: {user_id: [news_id, ...]}
    Каждая строка файла: "<user_id>: <news_id1>, <news_id2>, ..."
    """
    with open(output_file, "w", encoding="utf-8") as f:
        for user_id in sorted(distribution.keys()):
            news_ids = distribution[user_id]
            line = f"{user_id}: " + ", ".join(str(n) for n in news_ids)
            f.write(line + "\n")
    logging.info(f"Записан {output_file}: строк — {len(distribution)}")


def build_send_list(news_db: str, users_db: str,
                    output_file: str, last_cycle_iso: str) -> str:
    """
    Формирует send_list.txt.

    last_cycle_iso — время предыдущего цикла в формате '%Y-%m-%d %H:%M:%S'.
    Берём только новости, у которых added_at > last_cycle_iso.
    Возвращает время этого цикла (для следующего запуска).
    """
    this_cycle_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    news_conn = sqlite3.connect(news_db)
    users_conn = sqlite3.connect(users_db)

    try:
        # 1. Новые новости за интервал
        news_cur = news_conn.cursor()
        news_cur.execute("""
            SELECT id, category_id
            FROM news
            WHERE added_at > ?
        """, (last_cycle_iso,))
        new_news = news_cur.fetchall()
        # {category_id: [news_id, ...]}
        by_category = {}
        for news_id, cat_id in new_news:
            by_category.setdefault(cat_id, []).append(news_id)

        logging.info(f"Новых новостей за интервал: {len(new_news)}")

        # 2. Пользователи и их интересы
        users_cur = users_conn.cursor()
        users_cur.execute("SELECT id FROM users")
        user_ids = [row[0] for row in users_cur.fetchall()]

        distribution = {}
        for user_id in user_ids:
            users_cur.execute("""
                SELECT category_id FROM user_categories WHERE user_id = ?
            """, (user_id,))
            user_cats = [row[0] for row in users_cur.fetchall()]

            news_for_user = []
            for cat in user_cats:
                news_for_user.extend(by_category.get(cat, []))

            # сортировка для стабильного вывода
            news_for_user = sorted(set(news_for_user))
            distribution[user_id] = news_for_user

        # 3. Запись в файл
        write_send_list(output_file, distribution)

    finally:
        news_conn.close()
        users_conn.close()

    return this_cycle_iso



def run_one_cycle(config: dict, last_cycle_iso: str) -> str:
    logging.info("=" * 60)
    logging.info("СТАРТ ЦИКЛА")
    logging.info("=" * 60)

    ran = run_all_parsers(config["parsers_dir"])
    logging.info(f"Успешно выполнено парсеров: {ran}")

    new_time = build_send_list(
        news_db=config["news_db"],
        users_db=config["users_db"],
        output_file=config["output_file"],
        last_cycle_iso=last_cycle_iso,
    )

    logging.info("ЦИКЛ ЗАВЕРШЁН")
    return new_time



def main():
    try:
        config = load_config()
    except Exception as e:
        print(f"Не удалось загрузить config.json: {e}")
        sys.exit(1)

    setup_logging(config.get("log_file", os.path.join(BASE_DIR, "monitor.log")))

    # создаём users.db, если её нет
    init_users_db(config["users_db"])

    interval_sec = int(config["interval_minutes"]) * 60
    logging.info(f"Интервал: {config['interval_minutes']} мин")

    # отправная точка — время старта. Всё, что добавят парсеры дальше,
    # считается "новым" для следующего цикла.
    last_cycle_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        while True:
            last_cycle_iso = run_one_cycle(config, last_cycle_iso)
            logging.info(f"Пауза {config['interval_minutes']} мин...")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        logging.info("Остановлено пользователем (Ctrl+C)")
    finally:
        logging.info("Завершение работы")


if __name__ == "__main__":
    main()