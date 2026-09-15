#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Расписание студенческой группы СПбГУ (факультет ПМ-ПУ).

Скачивает Excel-файл с сайта timetable.spbu.ru, фильтрует занятия
по правилам из config.json, выводит расписание в консоль в виде
двухколоночной таблицы (пн–ср / чт–сб) и сохраняет PNG-картинку
с цветными плашками для дней недели и времени.
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime, timedelta, date
from pathlib import Path

import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont

CONFIG_FILE = "config.json"
BASE_URL = "https://timetable.spbu.ru/StudentGroupEvents/ExcelWeek"
CACHE_DIR = Path("cache")

# Соответствие времени начала пары → её номер.
# Номера привязаны к слотам, поэтому при пропуске пары нумерация «перескакивает».
SLOT_NUMBERS = {
    "09:30": "1",
    "10:20": "1-2",   # двойная пара (четверг, 10:20–12:50)
    "11:15": "2",
    "13:30": "3",     # отклонение (пятница, 13:30–15:05)
    "13:40": "3",
    "15:25": "4",
    "17:10": "5",
}

DAY_NAMES = {"Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"}
TIME_RE = re.compile(r"^\s+\S+\)\s+\d{2}:\d{2}")


# ----------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------

def get_monday(d: date = None) -> date:
    """Возвращает дату понедельника недели, в которую входит d (или сегодня)."""
    if d is None:
        d = date.today()
    return d - timedelta(days=d.weekday())


def load_config(path: str = CONFIG_FILE) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Файл конфигурации не найден: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def download_schedule(group_id: int, monday: date) -> Path:
    """Скачивает Excel-файл с расписанием (русская версия)."""
    CACHE_DIR.mkdir(exist_ok=True)
    date_str = monday.strftime("%Y-%m-%d")
    filename = f"расписание_{date_str}.xlsx"
    filepath = CACHE_DIR / filename

    url = f"{BASE_URL}?studentGroupId={group_id}&weekMonday={date_str}"
    print(f"Скачивание: {url}")

    headers = {"Accept-Language": "ru,en-US;q=0.7,en;q=0.3"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    with open(filepath, "wb") as f:
        f.write(resp.content)

    print(f"Сохранено: {filepath}")
    return filepath


EN_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
EN_DAYS = {
    "monday": "понедельник", "tuesday": "вторник", "wednesday": "среда",
    "thursday": "четверг", "friday": "пятница", "saturday": "суббота",
    "sunday": "воскресенье",
}


def extract_date(day_str: str, monday: date):
    """Извлекает дату из строки вида 'вторник 15 сентября' или 'Tuesday September 15'."""
    if not isinstance(day_str, str):
        return None
    text = day_str.replace("\n", " ").lower()
    parts = text.split()
    day_num = None
    for p in parts:
        if p.isdigit():
            day_num = int(p)
            break
    if day_num is None:
        return None
    month_num = None
    for mname, mnum in EN_MONTHS.items():
        if mname in text:
            month_num = mnum
            break
    if month_num is None:
        for mname, mnum in RU_MONTHS.items():
            if mname in text:
                month_num = mnum
                break
    if month_num is None:
        return None
    try:
        return date(monday.year, month_num, day_num)
    except ValueError:
        return None


def _matches_filter(row, rule: str) -> bool:
    """
    Проверяет, подходит ли занятие под правило.
    Правило — строка вида 'предмет' или 'предмет|преподаватель'
    (можно больше частей через |). Все части должны присутствовать
    в объединённой строке занятия (название + место + преподаватель),
    регистр не важен.
    """
    parts = [p.strip().lower() for p in rule.split("|") if p.strip()]
    if not parts:
        return False
    haystack = " ".join([
        str(row.get("Название", "")),
        str(row.get("Место", "")),
        str(row.get("Преподаватель", "")),
    ]).lower()
    return all(p in haystack for p in parts)


def parse_schedule(filepath: Path, filters: list) -> pd.DataFrame:
    raw = pd.read_excel(filepath, header=None)

    header_row = None
    for i, row in raw.iterrows():
        if str(row.iloc[1]).strip() == "Время":
            header_row = i
            break
    if header_row is None:
        raise ValueError("Не удалось найти строку заголовков.")

    data = raw.iloc[header_row + 1:].copy()
    data.columns = ["День", "Время", "Название", "Место", "Преподаватель"]
    data["День"] = data["День"].ffill()
    data = data.dropna(subset=["Название"])

    monday_match = filepath.stem.split("_")[-1]
    try:
        monday = datetime.strptime(monday_match, "%Y-%m-%d").date()
    except ValueError:
        monday = get_monday()

    data["Дата"] = data["День"].apply(lambda x: extract_date(x, monday))

    # ---- Фильтрация ----
    if filters:
        mask = data.apply(
            lambda row: any(_matches_filter(row, rule) for rule in filters),
            axis=1,
        )
        data = data[mask].copy()

    if data.empty:
        print("Нет занятий, удовлетворяющих фильтрам.")
        return pd.DataFrame(
            columns=["День", "Дата", "Время", "Название", "Место", "Преподаватель"]
        )

    def normalize_day(day_str):
        if not isinstance(day_str, str):
            return ""
        first_word = day_str.replace("\n", " ").split()[0].lower()
        return EN_DAYS.get(first_word, first_word)

    data["День_недели"] = data["День"].apply(normalize_day)
    data = data.sort_values(["Дата", "Время"]).reset_index(drop=True)
    return data


# ----------------------------------------------------------------------
# Определение номера пары
# ----------------------------------------------------------------------

def get_slot_number(time_str: str) -> str:
    """Возвращает номер пары по времени начала. '?' — если не найдено."""
    if not isinstance(time_str, str):
        return "?"
    t = time_str.replace("–", "-").replace("—", "-").strip()
    start = t.split("-")[0].strip()
    return SLOT_NUMBERS.get(start, "?")


# ----------------------------------------------------------------------
# Построение «сетки» (двух колонок)
# ----------------------------------------------------------------------

def build_grid(df: pd.DataFrame):
    """
    Возвращает список пар (левая_строка, правая_строка).
    Левая колонка — пн, вт, ср; правая — чт, пт, сб.
    """
    if df.empty:
        return []

    day_order = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота"]
    grouped = {day: [] for day in day_order}

    for _, row in df.iterrows():
        day_key = row["День_недели"]
        if day_key in grouped:
            time_str = str(row["Время"]).strip()
            slot = get_slot_number(time_str)
            name = str(row["Название"]).strip()
            place = str(row["Место"]).strip()
            teacher = str(row["Преподаватель"]).strip()
            entry = f"  {slot}) {time_str}\n  {name}\n  {place}\n  {teacher}"
            grouped[day_key].append(entry)

    left_days = ["понедельник", "вторник", "среда"]
    right_days = ["четверг", "пятница", "суббота"]

    def cell_lines(day):
        items = grouped.get(day, [])
        lines = [day.capitalize()]
        if not items:
            lines.append("  —")
        else:
            for item in items:
                lines.extend(item.split("\n"))
        lines.append("")  # пустая строка-разделитель между днями
        return lines

    left_lines = []
    for d in left_days:
        left_lines.extend(cell_lines(d))
    right_lines = []
    for d in right_days:
        right_lines.extend(cell_lines(d))

    max_len = max(len(left_lines), len(right_lines))
    left_lines += [""] * (max_len - len(left_lines))
    right_lines += [""] * (max_len - len(right_lines))

    return list(zip(left_lines, right_lines))


# ----------------------------------------------------------------------
# Текстовый вывод в консоль
# ----------------------------------------------------------------------

def format_schedule_text(grid) -> str:
    if not grid:
        return "Нет занятий для отображения."
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'ЛЕВАЯ КОЛОНКА (ПН–СР)':^48} | {'ПРАВАЯ КОЛОНКА (ЧТ–СБ)':^48}")
    lines.append("=" * 100)
    for l, r in grid:
        lines.append(f"{l:<48} | {r:<48}")
    lines.append("=" * 100)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Классификация строк для раскраски
# ----------------------------------------------------------------------

def classify_line(text: str) -> str:
    """
    Возвращает тип строки:
      'day'     — название дня недели,
      'time'    — строка со временем пары,
      'content' — всё остальное (название, место, преподаватель),
      'empty'   — пустая строка.
    """
    stripped = text.strip()
    if not stripped:
        return "empty"
    if stripped in DAY_NAMES:
        return "day"
    if TIME_RE.match(text):
        return "time"
    return "content"


# ----------------------------------------------------------------------
# Сохранение в PNG
# ----------------------------------------------------------------------

def find_font(font_size: int):
    candidates = [
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/Consolas.ttf",
        "C:/Windows/Fonts/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue
    return ImageFont.load_default()


def save_schedule_as_image(grid, output_path="расписание.png",
                           font_size=16, padding=20):
    if not grid:
        print("Нет данных для изображения.")
        return None

    font = find_font(font_size)

    def tw(s):
        return font.getlength(s)

    left_max = 0
    right_max = 0
    for l, r in grid:
        left_max = max(left_max, tw(l))
        right_max = max(right_max, tw(r))

    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    row_height = line_height + 6
    col_gap = 20

    img_width = int(padding * 2 + left_max + col_gap + right_max)
    img_height = int(padding * 2 + row_height * len(grid))

    img = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(img)

    DARK_RED = (139, 0, 0)      # тёмно-красный — для дней недели
    GRAY = (211, 211, 211)      # светло-серый — для времени

    x_left = padding
    x_right = padding + left_max + col_gap
    pad_text = 6

    y = padding
    for l, r in grid:
        lt = classify_line(l)
        rt = classify_line(r)

        if lt == "day":
            draw.rectangle([x_left, y, x_left + left_max, y + row_height - 3],
                           fill=DARK_RED)
        elif lt == "time":
            draw.rectangle([x_left, y, x_left + left_max, y + row_height - 3],
                           fill=GRAY)

        if rt == "day":
            draw.rectangle([x_right, y, x_right + right_max, y + row_height - 3],
                           fill=DARK_RED)
        elif rt == "time":
            draw.rectangle([x_right, y, x_right + right_max, y + row_height - 3],
                           fill=GRAY)

        text_y = y + 2
        fill_l = "white" if lt == "day" else "black"
        fill_r = "white" if rt == "day" else "black"

        draw.text((x_left + pad_text, text_y), l, fill=fill_l, font=font)
        draw.text((x_right + pad_text, text_y), r, fill=fill_r, font=font)

        y += row_height

    img.save(output_path)
    print(f"Картинка сохранена: {output_path}")
    return output_path


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Расписание студенческой группы СПбГУ (ПМ-ПУ)."
    )
    parser.add_argument("--week", choices=["current", "next"], default="current",
                        help="current — текущая (по умолчанию), next — следующая.")
    parser.add_argument("--config", default=CONFIG_FILE,
                        help="Путь к файлу конфигурации.")
    parser.add_argument("--no-download", action="store_true",
                        help="Не скачивать, использовать последний файл из cache/.")
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
    except FileNotFoundError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)

    group_id = cfg["student_group_id"]
    filters = cfg.get("subject_filters", [])

    monday = get_monday()
    if args.week == "next":
        monday += timedelta(days=7)

    print(f"Группа ID: {group_id}")
    print(f"Неделя: {monday.strftime('%d.%m.%Y')} – "
          f"{(monday + timedelta(days=6)).strftime('%d.%m.%Y')}")

    if args.no_download:
        files = sorted(CACHE_DIR.glob("расписание_*.xlsx"))
        if not files:
            print("Нет сохранённых файлов.", file=sys.stderr)
            sys.exit(1)
        filepath = files[-1]
        print(f"Используется файл: {filepath}")
    else:
        try:
            filepath = download_schedule(group_id, monday)
        except Exception as e:
            print(f"Ошибка скачивания: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        df = parse_schedule(filepath, filters)
    except Exception as e:
        print(f"Ошибка разбора файла: {e}", file=sys.stderr)
        sys.exit(1)

    grid = build_grid(df)
    text = format_schedule_text(grid)
    print("\n" + text)

    if grid:
        week_label = "текущая" if args.week == "current" else "следующая"
        img_name = f"расписание_{monday.strftime('%Y-%m-%d')}_{week_label}.png"
        save_schedule_as_image(grid, output_path=img_name)


if __name__ == "__main__":
    main()