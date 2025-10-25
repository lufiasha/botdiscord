import os
from flask import Flask, request, jsonify
from discord_interactions import verify_key_decorator, InteractionType, InteractionResponseType

app = Flask(__name__)

# Получаем из переменных окружения (установим позже на Render)
PUBLIC_KEY = os.environ['DISCORD_PUBLIC_KEY']

@app.route('/interactions', methods=['POST'])
@verify_key_decorator(PUBLIC_KEY)
def interactions():
    data = request.json

    # Проверяем тип взаимодействия
    if data['type'] == InteractionType.APPLICATION_COMMAND:
        command_name = data['data']['name']

        if command_name == 'ping':
            return jsonify({
                'type': InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
                'data': {
                    'content': '🏓 Pong! Вы помогаете мне получить значок разработчика — спасибо!'
                }
            })

    # Для других типов (например, ping от Discord)
    return jsonify({'type': InteractionResponseType.PONG})