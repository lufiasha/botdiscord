# main.py
import os
import json
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from discord_interactions import verify_key_decorator, InteractionType, InteractionResponseType

app = Flask(__name__)

# === Настройки Discord ===
DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
if not DISCORD_PUBLIC_KEY:
    raise ValueError("❌ DISCORD_PUBLIC_KEY не установлен в Render")

# === Подключение к БД ===
def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ DATABASE_URL не установлен в Render")
    url = urlparse(db_url)
    return psycopg2.connect(
        host=url.hostname,
        port=url.port,
        database=url.path[1:],
        user=url.username,
        password=url.password
    )

# === Автоматическое создание таблицы при первом запуске ===
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

# === Обновить игрока ===
def update_player(user_id, **kwargs):
    if not kwargs:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    updates = []
    values = []
    for key, value in kwargs.items():
        if key in ("sanity", "memories", "cycle", "max_sanity"):
            updates.append(f"{key} = %s")
            values.append(value)
    if updates:
        values.append(user_id)
        query = f"UPDATE players SET {', '.join(updates)}, updated_at = NOW() WHERE user_id = %s"
        cur.execute(query, values)
        conn.commit()
    cur.close()
    conn.close()

# === Инициализация БД при запуске Flask ===
with app.app_context():
    init_db()

# === Обработка команд ===
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
            msg = f"🌀 Цикл #{player['cycle']}\n🧠 Рассудок: {player['sanity']}/{player['max_sanity']}\n📜 Воспоминаний: {player['memories']}\n\nТы просыпаешься в подвале..."
        
        elif command_name == "explore":
            if player['sanity'] <= 0:
                msg = "Ты без сознания... Используй `/awaken`."
            else:
                events = [
                    {"text": "Нашёл записку! +2 воспоминания.", "memories": 2},
                    {"text": "Стены шепчут... −10 рассудка.", "sanity": -10},
                    {"text": "Амулет силы! +5 к макс. рассудку.", "max_sanity": 5},
                ]
                event = random.choice(events)
                update_player(
                    user_id,
                    sanity=player['sanity'] + event.get("sanity", 0),
                    memories=player['memories'] + event.get("memories", 0),
                    max_sanity=player['max_sanity'] + event.get("max_sanity", 0)
                )
                msg = event["text"]

        elif command_name == "rest":
            healed = min(20, player['max_sanity'] - player['sanity'])
            if healed > 0:
                update_player(user_id, sanity=player['sanity'] + healed)
                msg = f"🕯️ Отдых... +{healed} рассудка."
            else:
                msg = "Ты уже в порядке."

        else:
            msg = "Неизвестная команда."

        return jsonify({
            'type': InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
            'data': {'content': msg}
        })

    return jsonify({'type': InteractionResponseType.PONG})
