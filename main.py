import os
from flask import Flask, request, jsonify
from discord_interactions import verify_key_decorator, InteractionType, InteractionResponseType

app = Flask(__name__)

# Получаем публичный ключ из переменных окружения
PUBLIC_KEY = os.environ['DISCORD_PUBLIC_KEY']

@app.route('/interactions', methods=['POST'])
@verify_key_decorator(PUBLIC_KEY)
def interactions():
    print("✅ Получен запрос от Discord")
    data = request.json
    print("Данные запроса:", data)

    # Проверяем тип взаимодействия
    if data['type'] == InteractionType.APPLICATION_COMMAND:
        command_name = data['data']['name']
        print(f"Вызов команды: {command_name}")

        if command_name == 'ping':
            print("Отправляем ответ...")
            return jsonify({
                'type': InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
                'data': {
                    'content': '🏓 Pong! Вы помогаете мне получить значок разработчика — спасибо!'
                }
            })

    # Для других типов (например, ping от Discord)
    print("Отправляем PONG...")
    return jsonify({'type': InteractionResponseType.PONG})

# Запуск сервера
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
