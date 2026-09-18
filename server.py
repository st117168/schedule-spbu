#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальный сервер планировщика.
Запуск: python server.py
Открыть: http://127.0.0.1:5000
"""

from datetime import datetime, timedelta, date
from pathlib import Path

from flask import Flask, jsonify, render_template, request

import spbu_schedule as spbu

app = Flask(__name__)
CONFIG_FILE = "config.json"


def parse_time_to_minutes(t: str):
    """'09:30' -> 570"""
    try:
        h, m = t.strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def split_time_range(time_str: str):
    """'09:30-11:00' -> ('09:30', '11:00'); поддержка – и —"""
    if not isinstance(time_str, str):
        return None, None
    t = time_str.replace("–", "-").replace("—", "-").strip()
    if "-" not in t:
        return None, None
    a, b = t.split("-", 1)
    return a.strip(), b.strip()


def lesson_to_task(row, cfg_lessons: dict):
    """
    Преобразует строку расписания в задачу для планировщика.
    Возвращает dict или None, если не удалось определить дату.
    """
    date_val = row.get("Дата")
    if date_val is None or (hasattr(date_val, "value") and date_val != date_val):  # NaT
        return None
    if not isinstance(date_val, date):
        return None

    time_str = str(row.get("Время", "")).strip()
    start, end = split_time_range(time_str)

    # Определяем номер пары для отображения
    slot = spbu.get_slot_number(time_str)

    # Ключ темы для СПбГУ — единая тема "СПбГУ" (можно потом менять)
    return {
        "dateKey": date_val.isoformat(),
        "startTime": start,
        "endTime": end,
        "slot": slot,
        "title": str(row.get("Название", "")).strip(),
        "place": str(row.get("Место", "")).strip(),
        "teacher": str(row.get("Преподаватель", "")).strip(),
        "topicId": "spbu",       # фиксированный id темы
        "topicName": "СПбГУ",
        "topicColor": "#4f46e5",
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/schedule")
def api_schedule():
    """
    Параметры: ?week=current|next
    Возвращает JSON со списком занятий.
    """
    week = request.args.get("week", "current")

    try:
        cfg = spbu.load_config(CONFIG_FILE)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400

    group_id = cfg["student_group_id"]
    filters = cfg.get("subject_filters", [])

    monday = spbu.get_monday()
    if week == "next":
        monday += timedelta(days=7)

    try:
        filepath = spbu.download_schedule(group_id, monday)
    except Exception as e:
        # Пробуем взять из кэша
        files = sorted(spbu.CACHE_DIR.glob("расписание_*.xlsx"))
        if not files:
            return jsonify({"error": f"Не удалось скачать: {e}"}), 500
        filepath = files[-1]

    try:
        df = spbu.parse_schedule(filepath, filters)
    except Exception as e:
        return jsonify({"error": f"Ошибка разбора: {e}"}), 500

    lessons = []
    for _, row in df.iterrows():
        t = lesson_to_task(row, cfg)
        if t:
            lessons.append(t)

    return jsonify({
        "monday": monday.isoformat(),
        "week": week,
        "lessons": lessons,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)