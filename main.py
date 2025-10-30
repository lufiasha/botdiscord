# main.py
import os
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from discord_interactions import verify_key_decorator, InteractionType, InteractionResponseType
from datetime import datetime, timedelta

app = Flask(__name__)

# === Discord Public Key из твоего Developer Portal ===
DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY", "34d3c6086fed9cb712e1bc84a4b9ea82aa29eeb977815e115659102509a23c31")

if not DISCORD_PUBLIC_KEY:
    raise ValueError("❌ DISCORD_PUBLIC_KEY не установлен")

# === Предметы ===
ITEMS = {
    "rusty_sword": {"name": "Ржавый меч", "type": "weapon", "attack": 5},
    "iron_sword": {"name": "Железный меч", "type": "weapon", "attack": 12},
    "steel_blade": {"name": "Стальной клинок", "type": "weapon", "attack": 20},
    "leather_armor": {"name": "Кожаный доспех", "type": "armor", "defense": 3},
    "iron_armor": {"name": "Железный доспех", "type": "armor", "defense": 8},
    "obsidian_plate": {"name": "Обсидиановая броня", "type": "armor", "defense": 15},
    "healing_herb": {"name": "Целебная трава", "type": "consumable", "effect": "heal_20"}
}

# === Мобы ===
MOBS = [
    {"name": "Теневой Страж", "xp": 15, "gold": 3, "drops": ["rusty_sword"]},
    {"name": "Хранитель Порога", "xp": 30, "gold": 8, "drops": ["iron_sword", "leather_armor"]}
]

# === Боссы ===
BOSSES = [
    {"name": "Эхо Ты", "level_req": 1, "xp": 100, "gold": 25, "drops": ["iron_sword"], "cooldown_min": 15},
    {"name": "Страж Времени", "level_req": 5, "xp": 250, "gold": 60, "drops": ["steel_blade", "iron_armor"], "cooldown_min": 25},
    {"name": "Тень Академии", "level_req": 10, "xp": 500, "gold": 120, "drops": ["obsidian_plate"], "cooldown_min": 35},
    {"name": "Циклоп", "level_req": 15, "xp": 1000, "gold": 250, "drops": ["obsidian_plate", "steel_blade"], "cooldown_min": 45}
]

# === Подключение к БД ===
def get_db():
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

# === Инициализация БД ===
def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS players (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        level INT DEFAULT 1,
        xp INT DEFAULT 0,
        gold INT DEFAULT 0,
        sanity INT DEFAULT 100,
        max_sanity INT DEFAULT 100,
        last_meditation TIMESTAMP,
        last_boss_fight TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS inventory (
        user_id BIGINT,
        item_id TEXT,
        count INT DEFAULT 1,
        PRIMARY KEY (user_id, item_id)
    );
    CREATE TABLE IF NOT EXISTS equipment (
        user_id BIGINT PRIMARY KEY,
        weapon TEXT,
        armor TEXT
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

# === Вспомогательные функции ===
def create_player(user_id, username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO players (user_id, username) VALUES (%s, %s) ON CONFLICT DO NOTHING;
        INSERT INTO equipment (user_id) VALUES (%s) ON CONFLICT DO NOTHING;
    """, (user_id, username, user_id))
    conn.commit()
    cur.close()
    conn.close()

def get_player(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return {
        "user_id": row[0], "username": row[1], "level": row[2], "xp": row[3],
        "gold": row[4], "sanity": row[5], "max_sanity": row[6],
        "last_meditation": row[7], "last_boss_fight": row[8]
    }

def add_item(user_id, item_id, count=1):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO inventory (user_id, item_id, count)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, item_id)
        DO UPDATE SET count = inventory.count + %s;
    """, (user_id, item_id, count, count))
    conn.commit()
    cur.close()
    conn.close()

def get_equipment(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT weapon, armor FROM equipment WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return {"weapon": row[0], "armor": row[1]} if row else {"weapon": None, "armor": None}

def equip_item(user_id, item_id):
    if item_id not in ITEMS:
        return False
    item = ITEMS[item_id]
    conn = get_db()
    cur = conn.cursor()
    if item["type"] == "weapon":
        cur.execute("UPDATE equipment SET weapon = %s WHERE user_id = %s", (item_id, user_id))
    elif item["type"] == "armor":
        cur.execute("UPDATE equipment SET armor = %s WHERE user_id = %s", (item_id, user_id))
    else:
        return False
    conn.commit()
    cur.close()
    conn.close()
    return True

def get_stats(user_id):
    equip = get_equipment(user_id)
    attack = ITEMS.get(equip["weapon"], {}).get("attack", 0)
    defense = ITEMS.get(equip["armor"], {}).get("defense", 0)
    return {"attack": attack, "defense": defense}

# === Обработка команд ===
@app.route('/interactions', methods=['POST'])
@verify_key_decorator(DISCORD_PUBLIC_KEY)
def interactions():
    data = request.json
    if data['type'] == InteractionType.APPLICATION_COMMAND:
        cmd = data['data']['name']
        user_id = int(data['member']['user']['id'])
        username = data['member']['user']['username']

        create_player(user_id, username)
        player = get_player(user_id)

        if cmd == "status":
            stats = get_stats(user_id)
            msg = (
                f"🌀 {player['username']} | Уровень {player['level']}\n"
                f"🧠 Рассудок: {player['sanity']}/{player['max_sanity']}\n"
                f"⭐ Опыт: {player['xp']} | 💰 Золото: {player['gold']}\n"
                f"⚔️ Атака: {stats['attack']} | 🛡 Защита: {stats['defense']}"
            )
            return jsonify({'type': 4, 'data': {'content': msg}})

        elif cmd == "hunt":
            mob = random.choice(MOBS)
            xp_gain = mob["xp"]
            gold_gain = mob["gold"]
            drop = random.choice(mob["drops"]) if random.random() < 0.3 else None

            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE players SET xp = xp + %s, gold = gold + %s WHERE user_id = %s
            """, (xp_gain, gold_gain, user_id))
            conn.commit()
            cur.close()
            conn.close()

            if drop:
                add_item(user_id, drop)
                drop_msg = f"\n📦 Добыча: {ITEMS[drop]['name']}"
            else:
                drop_msg = ""

            msg = f"⚔️ Убит: {mob['name']}\n+{xp_gain} опыта, +{gold_gain} золота{drop_msg}"
            return jsonify({'type': 4, 'data': {'content': msg}})

        elif cmd == "equip":
            if 'options' not in data['data'] or not data['data']['options']:
                return jsonify({'type': 4, 'data': {'content': "Укажи предмет: `/equip <название>`"}})
            item_name = data['data']['options'][0]['value']
            item_id = item_name.lower().replace(" ", "_")
            if item_id not in ITEMS:
                return jsonify({'type': 4, 'data': {'content': "Такого предмета нет."}})
            if equip_item(user_id, item_id):
                return jsonify({'type': 4, 'data': {'content': f"✅ Экипировано: {ITEMS[item_id]['name']}"}})
            else:
                return jsonify({'type': 4, 'data': {'content': "Нельзя экипировать этот предмет."}})

        elif cmd == "boss":
            now = datetime.utcnow()
            last_fight = player["last_boss_fight"]

            eligible_bosses = [b for b in BOSSES if player["level"] >= b["level_req"]]
            if not eligible_bosses:
                return jsonify({'type': 4, 'data': {'content': "Ты ещё не готов к боссам."}})

            boss = eligible_bosses[-1]
            if last_fight and now - last_fight < timedelta(minutes=boss["cooldown_min"]):
                remaining = boss["cooldown_min"] - (now - last_fight).total_seconds() // 60
                return jsonify({'type': 4, 'data': {'content': f"Босс доступен через {int(remaining)} мин."}})

            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE players SET xp = xp + %s, gold = gold + %s, last_boss_fight = %s WHERE user_id = %s
            """, (boss["xp"], boss["gold"], now, user_id))
            conn.commit()
            cur.close()
            conn.close()

            if boss["drops"] and random.random() < 0.6:
                drop = random.choice(boss["drops"])
                add_item(user_id, drop)
                drop_msg = f"\n🔥 Добыча: {ITEMS[drop]['name']}"
            else:
                drop_msg = ""

            msg = f"💀 Побеждён: {boss['name']}\n+{boss['xp']} опыта, +{boss['gold']} золота{drop_msg}"
            return jsonify({'type': 4, 'data': {'content': msg}})

        elif cmd == "meditate":
            now = datetime.utcnow()
            last = player["last_meditation"]
            if last and now - last < timedelta(hours=1):
                return jsonify({'type': 4, 'data': {'content': "Медитация доступна раз в час."}})
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE players SET gold = gold + 5, last_meditation = %s WHERE user_id = %s
            """, (now, user_id))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'type': 4, 'data': {'content': "🕯️ Ты медитировал. +5 золота."}})

        elif cmd == "leaderboard":
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                SELECT username, level, xp FROM players ORDER BY xp DESC LIMIT 5
            """)
            rows = cur.fetchall()
            top = "\n".join([f"{i+1}. {r[0]} (ур. {r[1]}, {r[2]} опыта)" for i, r in enumerate(rows)])
            cur.close()
            conn.close()
            return jsonify({'type': 4, 'data': {'content': f"🏆 Топ героев:\n{top}"}})

        else:
            return jsonify({'type': 4, 'data': {'content': "Неизвестная команда."}})

    return jsonify({'type': InteractionResponseType.PONG})

# === Запуск ===
with app.app_context():
    init_db()

port = int(os.environ.get('PORT', 10000))
app.run(host='0.0.0.0', port=port)


