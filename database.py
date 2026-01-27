import sqlite3

# Название файла базы данных
DB_NAME = 'bot_database.db'

def init_db():
    """Создает таблицы, если их еще нет"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Таблица Пользователей (кто ты, рост, вес)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            age INTEGER,
            height INTEGER,
            weight REAL,
            activity_level TEXT,
            daily_calories INTEGER DEFAULT 2500
        )
    ''')
    
    # 2. Таблица Питания (что ты съел)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            food_name TEXT,
            calories INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных создана и таблицы готовы!")

# Функция: Добавить или обновить пользователя
def add_user(user_id, username, full_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Пытаемся найти пользователя
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        # Если нет - создаем
        cursor.execute('INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)', 
                       (user_id, username, full_name))
        conn.commit()
        print(f"Пользователь {full_name} добавлен!")
    
    conn.close()

# Функция: Обновить параметры тела (Рост, Вес, Возраст)
# Функция: Обновить параметры и учесть АКТИВНОСТЬ
# Функция: Обновить параметры (BMR * Активность * Цель)
def update_body_params(user_id, age, height, weight, activity_multiplier, goal_modifier):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. BMR (База)
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    
    # 2. ИТОГ = База * Активность * Цель
    # goal_modifier: 0.85 (похудение), 1.0 (вес), 1.15 (набор)
    final_calories = int(bmr * activity_multiplier * goal_modifier)
    
    # 3. Обновляем базу
    cursor.execute('''
        UPDATE users 
        SET age = ?, height = ?, weight = ?, daily_calories = ?
        WHERE user_id = ?
    ''', (age, height, weight, final_calories, user_id))
    
    conn.commit()
    conn.close()
    print(f"Готово! Калории: {final_calories}")

# Запускаем создание базы прямо сейчас, если запустить этот файл
if __name__ == '__main__':
    init_db()