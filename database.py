import aiosqlite
from datetime import date

DB_NAME = 'bot_database.db'

async def init_db():
    """Создает таблицы асинхронно"""
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица Пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                age INTEGER,
                height INTEGER,
                weight REAL,
                activity_level TEXT,
                daily_calories INTEGER DEFAULT 2000
            )
        ''')
        
        # 2. Таблица Еды (food_logs) с БЖУ!
        # Мы добавили protein, fat, carbs
        await db.execute('''
            CREATE TABLE IF NOT EXISTS food_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                food_name TEXT,
                calories INTEGER,
                protein INTEGER,
                fat INTEGER,
                carbs INTEGER,
                timestamp DATE DEFAULT CURRENT_DATE,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        await db.commit()
        print("✅ База данных (aiosqlite) готова!")

async def add_user(user_id, username, full_name):
    """Добавляет пользователя, если его нет"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user = await cursor.fetchone()
            
            if not user:
                await db.execute('INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?)', 
                               (user_id, username, full_name))
                await db.commit()
                print(f"👤 Пользователь {full_name} добавлен!")

async def update_body_params(user_id, age, height, weight, activity_multiplier, goal_modifier):
    """Обновляет параметры тела и пересчитывает норму"""
    # Формула Миффлина-Сан Жеора
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + 5
    final_calories = int(bmr * activity_multiplier * goal_modifier)
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            UPDATE users 
            SET age = ?, height = ?, weight = ?, daily_calories = ?
            WHERE user_id = ?
        ''', (age, height, weight, final_calories, user_id))
        await db.commit()
    print(f"📊 Параметры обновлены. Новая норма: {final_calories}")

# 👇 ВАЖНАЯ НОВАЯ ФУНКЦИЯ: Сохраняет еду с БЖУ
async def log_food(user_id, food_name, calories, protein, fat, carbs):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO food_logs (user_id, food_name, calories, protein, fat, carbs, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_DATE)
        ''', (user_id, food_name, calories, protein, fat, carbs))
        await db.commit()
    print(f"🍎 Еда сохранена: {food_name} ({calories} ккал)")

# 👇 ФУНКЦИЯ ДЛЯ САЙТА (Считает всё за сегодня)
async def get_daily_stats(user_id):
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT SUM(calories), SUM(protein), SUM(fat), SUM(carbs)
            FROM food_logs
            WHERE user_id = ? AND timestamp = ?
        """, (user_id, today)) as cursor:
            row = await cursor.fetchone()
            
            if not row or row[0] is None:
                return {"cal": 0, "prot": 0, "fat": 0, "carb": 0}
            
            return {
                "cal": int(row[0]),
                "prot": int(row[1]),
                "fat": int(row[2]),
                "carb": int(row[3])
            }