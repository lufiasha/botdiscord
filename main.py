# main.py
import os
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from discord_interactions import verify_key_decorator, InteractionType, InteractionResponseType

app = Flask(__name__)

# === Настройки Discord ===
DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
if not DISCORD_PUBLIC_KEY:
    raise ValueError("❌ Переменная DISCORD_PUBLIC_KEY не установлена в Render")

# === Подключение к БД ===
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ Переменная DATABASE_URL не установлена в Render")
    url = urlparse(db_url)
    return psycopg2.connect(
        host=url.hostname,
        port=url.port,
        database=url.path[1:],
        user=url.username,
        password=url.password
    )

# === Создание таблицы при старте ===
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        cycle INT DEFAULT 1,
        sanity INT DEFAULT 100,
        max_sanity INT DEFAULT 100,
        memories INT DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Таблица players готова")

# === Получить или создать игрока ===
def get_or_create_player(user_id, username):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, cycle, sanity, max_sanity, memories FROM players WHERE user_id = %s",
        (user_id,)
    )
    row = cur.fetchone()
    if row:
        player = {
            "user_id": row[0],
            "cycle": row[1],
            "sanity": row[2],
            "max_sanity": row[3],
            "memories": row[4]
        }
    else:
        cur.execute(
            """INSERT INTO players (user_id, username)
               VALUES (%s, %s)
               RETURNING user_id, cycle, sanity, max_sanity, memories""",
            (user_id, username)
        )
        row = cur.fetchone()
        player = {
            "user_id": row[0],
            "cycle": row[1],
            "sanity": row[2],
            "max_sanity": row[3],
            "memories": row[4]
        }
    conn.commit()
    cur.close()
    conn.close()
    return player

# === Обновить данные игрока ===
def update_player(user_id, sanity=None, memories=None, cycle=None, max_sanity=None):
    updates = []
    values = []
    if sanity is not None:
        updates.append("sanity = %s")
        values.append(max(0, sanity))
    if memories is not None:
        updates.append("memories = %s")
        values.append(memories)
    if cycle is not None:
        updates.append("cycle = %s")
        values.append(cycle)
    if max_sanity is not None:
        updates.append("max_sanity = %s")
        values.append(max_sanity)
    if not updates:
        return
    values.append(user_id)
    query = f"UPDATE players SET {', '.join(updates)}, updated_at = NOW() WHERE user_id = %s"
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, values)
    conn.commit()
    cur.close()
    conn.close()

# === Инициализация БД при запуске приложения ===
with app.app_context():
    init_db()

# === Обработка запросов от Discord ===
@app.route('/interactions', methods=['POST'])
@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interactions():
    data = request.json
    if data['type'] == InteractionType.APPLICATION_COMMAND:
        command_name = data['data']['name']
        user_id = int(data['member']['user']['id'])
        username = data['member']['user']['username']

        player = get_or_create_player(user_id, username)

        if command_name == "awaken":
            msg = (
                f"🌀 Цикл #{player['cycle']}\n"
                f"🧠 Рассудок: {player['sanity']}/{player['max_sanity']}\n"
                f"📜 Воспоминаний: {player['memories']}\n\n"
                "Ты просыпаешься в подвале. Стены дышат. Что дальше?"
            )

        elif command_name == "explore":
            if player['sanity'] <= 0:
                msg = "Ты без сознания... Используй `/awaken`, чтобы начать цикл заново."
            else:
                events = [
                    {"text": "Ты нашёл обрывок дневника! +2 воспоминания.", "memories": 2},
                    {"text": "Стены шепчут... −10 рассудка.", "sanity": -10},
                    {"text": "В углу — странный амулет. +5 к макс. рассудку!", "max_sanity": 5},
                    {"text": "Ты вспомнил лицо матери... +5 воспоминаний, но больно. −15 рассудка.", "memories": 5, "sanity": -15}
                ]
                event = random.choice(events)
                new_san = player['sanity'] + event.get("sanity", 0)
                new_mem = player['memories'] + event.get("memories", 0)
                new_max = player['max_sanity'] + event.get("max_sanity", 0)

                update_player(
                    user_id,
                    sanity=new_san,
                    memories=new_mem,
                    max_sanity=new_max if "max_sanity" in event else None
                )
                msg = event["text"]

        elif command_name == "rest":
            if player['sanity'] >= player['max_sanity']:
                msg = "Ты отдохнул... но уже в порядке."
            else:
                healed = min(20, player['max_sanity'] - player['sanity'])
                update_player(user_id, sanity=player['sanity'] + healed)
                msg = f"🕯️ Ты немного отдохнул. +{healed} рассудка."

        else:
            msg = "Неизвестная команда."

        return jsonify({
            'type': InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            'data': {'content': msg}
        })

    return jsonify({'type': InteractionResponseType.PONG})

# === Запуск сервера (обязательно без if __name__ == '__main__' для Render) ===
port = int(os.environ.get('PORT', 10000))
app.run(host='0.0.0.0', port=port)
