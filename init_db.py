# init_db.py
import os
import psycopg2
from urllib.parse import urlparse

# Получаем URL из переменной окружения (Render автоматически её передаёт)
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("❌ Переменная DATABASE_URL не найдена. Убедись, что она добавлена в Render.")

# Разбираем URL на части
url = urlparse(db_url)
conn = psycopg2.connect(
    host=url.hostname,
    port=url.port,
    database=url.path[1:],  # убираем первый символ '/' из пути
    user=url.username,
    password=url.password
)

cur = conn.cursor()

# Создаём таблицу игроков
cur.execute("""
CREATE TABLE IF NOT EXISTS players (
    user_id BIGINT PRIMARY KEY,          -- Уникальный ID пользователя Discord
    username TEXT,                       -- Имя пользователя (для удобства)
    cycle INT DEFAULT 1,                 -- Номер цикла (рогалик-прогрессия)
    sanity INT DEFAULT 100,              -- Текущий уровень рассудка
    max_sanity INT DEFAULT 100,          -- Максимальный рассудок (можно прокачивать)
    memories INT DEFAULT 0,              -- Валюта: воспоминания
    created_at TIMESTAMP DEFAULT NOW(),  -- Когда игрок начал играть
    updated_at TIMESTAMP DEFAULT NOW()   -- Когда данные обновлялись в последний раз
);
""")

# Сохраняем изменения
conn.commit()

# Закрываем соединение
cur.close()
conn.close()

print("✅ Таблица 'players' успешно создана или уже существует.")
