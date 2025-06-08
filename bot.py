import telebot
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import random
from telebot import types
import time
import requests


load_dotenv()

bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Словарь для хранения текущего состояния пользователя
user_states = {}


def get_db_connection():
    #Создает и возвращает подключение к БД
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT'),
        cursor_factory=RealDictCursor
    )


def add_user(telegram_id, name):
    #Добавляет нового пользователя в БД
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (telegram_id, name) VALUES (%s, %s) ON CONFLICT (telegram_id) DO NOTHING;",
            (telegram_id, name)
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка при добавлении пользователя: {e}")
    finally:
        cur.close()
        conn.close()


def get_user_id(telegram_id):
    #Получает ID пользователя из БД по telegram_id
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
        result = cur.fetchone()
        return result['id'] if result else None
    finally:
        cur.close()
        conn.close()


def get_random_word(telegram_id):
    #Получает случайное слово для пользователя (из общих и персональных)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        # Объединяем общие слова и персональные слова пользователя
        cur.execute("""
            SELECT * FROM (
                SELECT id, english_text, translation, 'common' as source FROM common_words
                UNION
                SELECT id, english_text, translation, 'user' as source FROM user_words WHERE user_id = %s
            ) AS all_words
            ORDER BY RANDOM()
            LIMIT 1
        """, (user_id,))
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def get_wrong_answers(correct_translation, limit=3):
    #Получает неправильные варианты ответов
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT translation FROM (
                SELECT translation FROM common_words WHERE translation != %s
                UNION
                SELECT translation FROM user_words WHERE translation != %s
            ) AS all_translations
        """, (correct_translation, correct_translation))
        
        all_answers = [row['translation'] for row in cur.fetchall()]
        # Убираем дубликаты и перемешиваем в Python
        unique_answers = list(set(all_answers))
        random.shuffle(unique_answers)
        return unique_answers[:limit]
    finally:
        cur.close()
        conn.close()


def save_user_progress(telegram_id, word_data, is_correct):
    #Сохраняет прогресс пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        # Сохраняем прогресс с текстом слова вместо ID
        cur.execute(
            """INSERT INTO user_progress (user_id, word_english, word_translation, is_correct) 
               VALUES (%s, %s, %s, %s)""",
            (user_id, word_data['english_text'], word_data['translation'], is_correct)
        )
        conn.commit()
        print(f"Прогресс сохранен: {word_data['english_text']} - {is_correct}")
    except Exception as e:
        print(f"Ошибка при сохранении прогресса: {e}")
    finally:
        cur.close()
        conn.close()


def add_user_word(telegram_id, english_text, translation, example=None):
    #Добавляет персональное слово пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        cur.execute(
            """INSERT INTO user_words (user_id, english_text, translation, example) 
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (user_id, english_text) DO NOTHING""",
            (user_id, english_text, translation, example)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"Ошибка при добавлении слова: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def get_user_words_count(telegram_id):
    #Получает количество слов пользователя (общие + персональные)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM common_words) + 
                (SELECT COUNT(*) FROM user_words WHERE user_id = %s) as total
        """, (user_id,))
        result = cur.fetchone()
        return result['total'] if result else 0
    finally:
        cur.close()
        conn.close()


def get_user_words(telegram_id):
    #Получает персональные слова пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        cur.execute(
            "SELECT id, english_text, translation FROM user_words WHERE user_id = %s",
            (user_id,)
        )
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def delete_user_word(telegram_id, word_id):
    #Удаляет персональное слово пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(telegram_id)
        cur.execute(
            "DELETE FROM user_words WHERE id = %s AND user_id = %s",
            (word_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"Ошибка при удалении слова: {e}")
        return False
    finally:
        cur.close()
        conn.close()


@bot.message_handler(commands=['start'])
def start(message):
    #Обработчик команды /start
    user_name = message.from_user.first_name or "друг"
    add_user(message.from_user.id, user_name)
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📚 Учить слова', '➕ Добавить слово')
    markup.row('🗑 Удалить слово', '📊 Статистика')
    
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        "Я бот для изучения английского языка. "
        "Я помогу тебе выучить новые слова и запомнить их перевод.\n\n"
        "Вот что я умею:\n"
        "📚 *Учить слова* - я буду показывать слова, а ты выбирать правильный перевод\n"
        "➕ *Добавить слово* - ты можешь добавить свои слова для изучения\n"
        "🗑 *Удалить слово* - удалить слова, которые ты добавил\n"
        "📊 *Статистика* - посмотреть свой прогресс\n\n"
        "Выбери действие из меню ниже 👇"
    )
    
    bot.send_message(
        message.chat.id, 
        welcome_text, 
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.message_handler(func=lambda message: message.text == '📚 Учить слова')
def learn_words(message):
    #Запуск викторины
    word = get_random_word(message.from_user.id)
    if not word:
        bot.send_message(message.chat.id, "В базе пока нет слов для изучения.")
        return
    
    # Сохраняем текущее слово в состоянии пользователя
    user_states[message.from_user.id] = {
        'action': 'learning',
        'word': word,
        'attempts': 0
    }
    
    # Получаем неправильные ответы и смешиваем с правильным
    wrong_answers = get_wrong_answers(word['translation'])
    all_answers = wrong_answers + [word['translation']]
    random.shuffle(all_answers)
    
    # Логи
    print(f"Word: {word['english_text']} -> {word['translation']}")
    print(f"All answers: {all_answers}")
    
    # Создаем клавиатуру с вариантами ответов
    markup = types.InlineKeyboardMarkup(row_width=2)
    for answer in all_answers:
        markup.add(types.InlineKeyboardButton(answer, callback_data=f"answer_{answer}"))
    
    bot.send_message(
        message.chat.id,
        f"Как переводится слово:\n\n🔤 *{word['english_text']}*",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_'))
def handle_answer(call):
    #Обработчик ответов на вопросы викторины
    user_id = call.from_user.id
    
    if user_id not in user_states or user_states[user_id]['action'] != 'learning':
        bot.answer_callback_query(call.id, "Начните новую игру!")
        return
    
    selected_answer = call.data.replace('answer_', '')
    correct_answer = user_states[user_id]['word']['translation']
    user_states[user_id]['attempts'] += 1
    
    # Отладочная информация
    print(f"Selected: '{selected_answer}', Correct: '{correct_answer}', Equal: {selected_answer == correct_answer}")
    
    if selected_answer == correct_answer:
        # Правильный ответ
        bot.edit_message_text(
            f"✅ Правильно! *{user_states[user_id]['word']['english_text']}* - это *{correct_answer}*",
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown'
        )
        # Сохраняем прогресс
        save_user_progress(user_id, user_states[user_id]['word'], True)
        # Предлагаем следующее слово
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Следующее слово ➡️", callback_data="next_word"))
        bot.send_message(call.message.chat.id, "Продолжим?", reply_markup=markup)
    else:
        # Неправильный ответ
        if user_states[user_id]['attempts'] < 3:
            bot.answer_callback_query(call.id, "❌ Неправильно, попробуй еще раз!", show_alert=True)
        else:
            # После 3 попыток показываем правильный ответ
            bot.edit_message_text(
                f"❌ Неправильно!\n\n"
                f"Правильный ответ: *{user_states[user_id]['word']['english_text']}* - *{correct_answer}*",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='Markdown'
            )
            save_user_progress(user_id, user_states[user_id]['word'], False)
            # Предлагаем следующее слово
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("Следующее слово ➡️", callback_data="next_word"))
            bot.send_message(call.message.chat.id, "Продолжим?", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "next_word")
def next_word(call):
    #Показывает следующее слово
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    # Создаем новое слово для изучения
    word = get_random_word(call.from_user.id)
    if not word:
        bot.send_message(call.message.chat.id, "В базе пока нет слов для изучения.")
        return
    
    # Сохраняем текущее слово в состоянии пользователя
    user_states[call.from_user.id] = {
        'action': 'learning',
        'word': word,
        'attempts': 0
    }
    
    # Получаем неправильные ответы и смешиваем с правильным
    wrong_answers = get_wrong_answers(word['translation'])
    all_answers = wrong_answers + [word['translation']]
    random.shuffle(all_answers)
    
    # Создаем клавиатуру с вариантами ответов
    markup = types.InlineKeyboardMarkup(row_width=2)
    for answer in all_answers:
        markup.add(types.InlineKeyboardButton(answer, callback_data=f"answer_{answer}"))
    
    bot.send_message(
        call.message.chat.id,
        f"Как переводится слово:\n\n🔤 *{word['english_text']}*",
        reply_markup=markup,
        parse_mode='Markdown'
    )


@bot.message_handler(func=lambda message: message.text == '➕ Добавить слово')
def add_word_start(message):
    #Начинает процесс добавления нового слова
    user_states[message.from_user.id] = {'action': 'adding_word', 'step': 'english'}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('❌ Отмена')
    
    bot.send_message(
        message.chat.id,
        "Введите слово на английском языке:",
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: message.text == '🗑 Удалить слово')
def delete_word_start(message):
    #Показывает список слов пользователя для удаления
    words = get_user_words(message.from_user.id)
    
    if not words:
        bot.send_message(message.chat.id, "У вас пока нет добавленных слов.")
        return
    
    markup = types.InlineKeyboardMarkup()
    for word in words:
        markup.add(types.InlineKeyboardButton(
            f"🗑 {word['english_text']} - {word['translation']}",
            callback_data=f"delete_{word['id']}"
        ))
    
    bot.send_message(
        message.chat.id,
        "Выберите слово для удаления:",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def handle_delete(call):
    #Обработчик удаления слова
    word_id = int(call.data.replace('delete_', ''))
    
    if delete_user_word(call.from_user.id, word_id):
        bot.edit_message_text(
            "✅ Слово успешно удалено!",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.edit_message_text(
            "❌ Ошибка при удалении слова.",
            call.message.chat.id,
            call.message.message_id
        )


@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def show_statistics(message):
    #Показываем статистику пользователя
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        user_id = get_user_id(message.from_user.id)
        
        # Получаем статистику
        cur.execute("""
            SELECT 
                COUNT(*) as total_attempts,
                COUNT(CASE WHEN is_correct THEN 1 END) as correct_answers,
                COUNT(DISTINCT word_english) as unique_words
            FROM user_progress
            WHERE user_id = %s
        """, (user_id,))
        
        stats = cur.fetchone()
        total_words = get_user_words_count(message.from_user.id)
        
        if stats['total_attempts'] > 0:
            accuracy = (stats['correct_answers'] / stats['total_attempts']) * 100
        else:
            accuracy = 0
        
        text = (
            f"📊 *Ваша статистика:*\n\n"
            f"📚 Всего слов для изучения: {total_words}\n"
            f"✍️ Всего попыток: {stats['total_attempts']}\n"
            f"✅ Правильных ответов: {stats['correct_answers']}\n"
            f"📈 Точность: {accuracy:.1f}%\n"
            f"🎯 Изучено уникальных слов: {stats['unique_words']}"
        )
        
        bot.send_message(message.chat.id, text, parse_mode='Markdown')
        
    finally:
        cur.close()
        conn.close()


@bot.message_handler(func=lambda message: message.text == '❌ Отмена')
def cancel_action(message):
    #Отменяем текущее действие
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('📚 Учить слова', '➕ Добавить слово')
    markup.row('🗑 Удалить слово', '📊 Статистика')
    
    bot.send_message(
        message.chat.id,
        "Действие отменено. Выберите новое действие:",
        reply_markup=markup
    )


@bot.message_handler(func=lambda message: True)
def handle_text(message):
    #Обработчик всех текстовых сообщений
    user_id = message.from_user.id
    
    if user_id not in user_states:
        # Если нет активного состояния, показываем меню
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('📚 Учить слова', '➕ Добавить слово')
        markup.row('🗑 Удалить слово', '📊 Статистика')
        
        bot.send_message(
            message.chat.id,
            "Выберите действие из меню:",
            reply_markup=markup
        )
        return
    
    state = user_states[user_id]
    
    if state['action'] == 'adding_word':
        if state['step'] == 'english':
            # Сохраняем английское слово и переходим к переводу
            state['english'] = message.text.strip()
            state['step'] = 'translation'
            bot.send_message(message.chat.id, "Теперь введите перевод на русском:")
            
        elif state['step'] == 'translation':
            # Сохраняем перевод и переходим к примеру
            state['translation'] = message.text.strip()
            state['step'] = 'example'
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row('⏭ Пропустить', '❌ Отмена')
            
            bot.send_message(
                message.chat.id,
                "Введите пример использования (необязательно):",
                reply_markup=markup
            )
            
        elif state['step'] == 'example':
            # Сохраняем пример (если не пропущен) и добавляем слово
            example = None if message.text == '⏭ Пропустить' else message.text.strip()
            
            if add_user_word(user_id, state['english'], state['translation'], example):
                total_words = get_user_words_count(user_id)
                
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.row('📚 Учить слова', '➕ Добавить слово')
                markup.row('🗑 Удалить слово', '📊 Статистика')
                
                bot.send_message(
                    message.chat.id,
                    f"✅ Слово успешно добавлено!\n"
                    f"Теперь вы изучаете {total_words} слов.",
                    reply_markup=markup
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ Не удалось добавить слово. Возможно, оно уже существует."
                )
            
            del user_states[user_id]


if __name__ == '__main__':
    print(" [INFO] Бот запущен...")
    bot.polling(none_stop=True)

    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except requests.exceptions.ReadTimeout:
            print(" [WARNING] Timeout при подключении к Telegram API. Переподключение через 10 секунд...")
            time.sleep(10)
        except requests.exceptions.ConnectionError:
            print(" [WARNING] Ошибка соединения с Telegram API. Переподключение через 15 секунд...")
            time.sleep(15)
        except Exception as e:
            print(f" [ERROR] Неожиданная ошибка: {e}. Перезапуск через 20 секунд...")
            time.sleep(20)