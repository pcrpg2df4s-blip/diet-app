import asyncio
import logging
import sys
import re
import io
import aiosqlite
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg') # Это важно! Чтобы график рисовался в памяти, а не пытался открыть окно
import io
import sqlite3
from aiogram.types import BufferedInputFile # Проверь, что это есть
import json
from datetime import datetime, date, timedelta
from aiogram.types import WebAppInfo
from database import init_db, add_user
from database import update_body_params
from aiogram.types import ReplyKeyboardRemove
from aiogram import F
import time
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F, Router, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    BufferedInputFile, ReplyKeyboardRemove, FSInputFile, MenuButtonWebApp
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from aiogram.types import FSInputFile

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8338504661:AAH6RmVVXqbsavQ3Es2grZYvyzFgu6elTAs"
GEMINI_API_KEY = "AIzaSyBH_PcefYezMJFOhkShyVC-1S2di5OH6y8"

# Настройка Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-exp') # Используем быструю модель с поддержкой фото

# Ссылка на логотип (заглушка, замените на свою или отправляйте локальный файл)
LOGO_URL = "https://cdn-icons-png.flaticon.com/512/3063/3063822.png" 

# --- БАЗА ДАННЫХ ---
DB_NAME = "diet_bot.db"

async def init_db():
    # Открываем соединение
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                weight REAL,
                height REAL,
                age INTEGER,
                gender TEXT,
                activity TEXT,
                goal TEXT,
                calories_limit REAL,
                consumed_calories REAL DEFAULT 0,
                consumed_protein REAL DEFAULT 0,
                consumed_fat REAL DEFAULT 0,
                consumed_carbs REAL DEFAULT 0,
                last_water_update TEXT
            )
        """)
        
        # 2. Таблица логов еды
        await db.execute("""
            CREATE TABLE IF NOT EXISTS food_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                food_name TEXT,
                calories REAL,
                proteins REAL,
                fats REAL,
                carbs REAL,
                date TEXT
            )
        """)

        # 3. НОВАЯ ТАБЛИЦА ДЛЯ ГРАФИКА (Шаг 1 из прошлого совета)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS nutrition_history (
                user_id INTEGER,
                date TEXT,
                total_calories REAL,
                PRIMARY KEY (user_id, date)
            )
        """)
        
        # Сохраняем ВСЕ таблицы сразу, пока соединение активно (внутри блока async with)
        await db.commit() 
    # Здесь блок async with заканчивается, и соединение закрывается автоматически

# --- МАШИНА СОСТОЯНИЙ (FSM) ---
class Registration(StatesGroup):
    gender = State()
    age = State()
    height = State()
    weight = State()
    activity = State()
    goal = State()
    diet_type = State()

class IngredientAnalysis(StatesGroup):
    waiting_for_product = State()

class FoodAnalysis(StatesGroup):
    waiting_for_food = State()        # <--- Добавили эту строчку
    waiting_for_confirmation = State()
    waiting_for_products = State()

class RecipeState(StatesGroup):
    waiting_for_products = State()

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🍽 Добавить еду"), KeyboardButton(text="🔍 Разбор состава"))
    builder.row(KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👨‍🍳 Что приготовить?"))
    builder.row(KeyboardButton(text="👤 Профиль"), KeyboardButton(text="👨‍⚕️ Диетолог"))
    
    return builder.as_markup(resize_keyboard=True, is_persistent=True)

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def calculate_calories(gender, weight, height, age, activity, goal):
    # Формула Миффлина-Сан Жеора
    bmr = 10 * weight + 6.25 * height - 5 * age
    bmr += 5 if gender == 'М' else -161

    multipliers = {
        "🛋 Сидячий": 1.2,
        "🚶‍♂️ Легкая": 1.375,
        "🏃‍♂️ Средняя": 1.55,
        "🏋️‍♂️ Высокая": 1.725
    }
    tdee = bmr * multipliers.get(activity, 1.2)

    if "Похудеть" in goal:
        return int(tdee * 0.85) # Дефицит 15%
    elif "Набрать" in goal:
        return int(tdee * 1.15) # Профицит 15%
    else:
        return int(tdee)

async def get_smart_advice(user_id):
    today = date.today().isoformat()
    
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Получаем норму калорий пользователя
        async with db.execute("SELECT calories_limit FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return None
            daily_limit = row[0]

        # 2. Считаем, сколько всего съедено за сегодня (суммируем БЖУ)
        async with db.execute("""
            SELECT SUM(calories), SUM(proteins), SUM(fats), SUM(carbs) 
            FROM food_log 
            WHERE user_id = ? AND date = ?
        """, (user_id, today)) as cursor:
            stats = await cursor.fetchone()
            
    # Если за сегодня еще ничего не ели (или там None), возвращаем пустоту
    if not stats or stats[0] is None:
        return None

    total_cals = stats[0]
    total_prot = stats[1] or 0
    total_fat = stats[2] or 0
    total_carb = stats[3] or 0

    # --- ЛОГИКА СОВЕТОВ ---
    
    # Советуем только если человек уже поел хотя бы на 40% от нормы 
    # (чтобы не ругать его за одни углеводы сразу после завтрака)
    if total_cals < (daily_limit * 0.4):
        return None

    # Переводим граммы в калории для оценки вклада
    # 1г белка = 4 ккал, 1г жира = 9 ккал, 1г угля = 4 ккал
    p_cals = total_prot * 4
    f_cals = total_fat * 9
    c_cals = total_carb * 4
    
    # Процентное соотношение
    p_pct = p_cals / total_cals
    f_pct = f_cals / total_cals
    c_pct = c_cals / total_cals

    # 1. ПЕРЕБОР УГЛЕВОДОВ (> 55% энергии от углей)
    if c_pct > 0.55:
        return (
            "⚠️ <b>Внимание:</b> Сегодня многовато углеводов.\n"
            "💡 <i>Совет:</i> На следующий прием пищи (или ужин) сделай упор на <b>белок</b> и овощи. "
            "Отлично подойдет творог, белая рыба, куриная грудка или омлет. Макароны и хлеб лучше отложить."
        )

    # 2. ПЕРЕБОР ЖИРОВ (> 45% энергии от жиров)
    if f_pct > 0.45:
        return (
            "⚠️ <b>Внимание:</b> В рационе сегодня много жирного.\n"
            "💡 <i>Совет:</i> Постарайся до конца дня есть более легкую пищу. "
            "Избегай масла, орехов, свинины. Лучше съешь салат, кефир или постное мясо на пару."
        )

    # 3. ПЕРЕБОР БЕЛКОВ (> 40% энергии - редко, но бывает)
    if p_pct > 0.40:
        return (
            "⚠️ <b>Внимание:</b> Очень много белка.\n"
            "💡 <i>Совет:</i> Твоему организму нужна энергия! Добавь немного <b>сложных углеводов</b>: "
            "гречка, запеченный картофель или цельнозерновой хлеб пойдут на пользу."
        )
        
    # 4. НЕДОБОР КАЛОРИЙ К ВЕЧЕРУ (если уже вечер, а съедено мало)
    # Здесь можно добавить проверку времени, но пока сделаем просто по факту заполнения
    if total_cals > daily_limit * 1.1:
         return "🔴 <b>Ты превысил норму калорий на сегодня.</b> Остановись, попей водички! 💧"

    return None

async def get_todays_food_log(user_id):
    today_str = date.today().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT food_name, calories, proteins, fats, carbs FROM food_log WHERE user_id = ? AND date = ?",
            (user_id, today_str)
        ) as cursor:
            rows = await cursor.fetchall()
            food_log = [dict(row) for row in rows]
            # Rename keys to match frontend expectations
            for item in food_log:
                item['name'] = item.pop('food_name')
            return food_log

async def get_current_week_history(user_id):
    today = date.today()
    # Находим прошлый понедельник (0 - понедельник, 1 - вторник и т.д.)
    start_of_week = today - timedelta(days=today.weekday())
    
    week_data = []
    async with aiosqlite.connect(DB_NAME) as db:
        for i in range(7):
            current_day = (start_of_week + timedelta(days=i)).isoformat()
            async with db.execute(
                "SELECT total_calories FROM nutrition_history WHERE user_id = ? AND date = ?",
                (user_id, current_day)
            ) as cursor:
                row = await cursor.fetchone()
                week_data.append(str(row[0]) if row else "0")
    
    # Возвращаем строку через запятую, например: "0,12000,0,0,0,0,0"
    return ",".join(week_data)

async def get_today_food_json(user_id):
    today = date.today().isoformat()
    food_list = []

    async with aiosqlite.connect(DB_NAME) as db:
        # Берем id, имя, калории, бжу и дату
        async with db.execute("""
            SELECT id, food_name, calories, proteins, fats, carbs 
            FROM food_log 
            WHERE user_id = ? AND date = ?
            ORDER BY id DESC
        """, (user_id, today)) as cursor:
            rows = await cursor.fetchall()

            for row in rows:
                food_list.append({
                    "id": row[0],
                    "name": row[1],
                    "cal": int(row[2]),
                    "p": int(row[3]),
                    "f": int(row[4]),
                    "c": int(row[5])
                })

    # Превращаем список в строку JSON
    return json.dumps(food_list, ensure_ascii=False)

# --- ОБРАБОТЧИКИ (HANDLERS) ---
dp = Dispatcher()
router = Router()
dp.include_router(router)

import sqlite3 # Не забудь этот импорт наверху
from aiogram.enums import ParseMode # И этот для HTML

# === НОВЫЙ ХЕНДЛЕР ДЛЯ УДАЛЕНИЯ ЕДЫ (ШАГ 5) ===
@router.message(F.web_app_data)
async def handle_web_app_data(message: Message, state: FSMContext):
    try:
        # Читаем данные, которые прислал сайт
        data = json.loads(message.web_app_data.data)
        
        # Если это команда на удаление
        if data.get('action') == 'delete_food':
            food_id = data.get('id')
            user_id = message.from_user.id
            
            async with aiosqlite.connect(DB_NAME) as db:
                # 1. Узнаем, сколько калорий было в этой еде (чтобы вернуть их)
                async with db.execute("SELECT calories, proteins, fats, carbs FROM food_log WHERE id = ?", (food_id,)) as cursor:
                    row = await cursor.fetchone()
                
                if row:
                    cal, prot, fat, carb = row
                    
                    # 2. Удаляем запись из лога
                    await db.execute("DELETE FROM food_log WHERE id = ?", (food_id,))
                    
                    # 3. Вычитаем эти калории из съеденного сегодня (возвращаем лимит)
                    # Используем MAX(0, ...), чтобы случайно не уйти в минус
                    await db.execute("""
                        UPDATE users 
                        SET consumed_calories = MAX(0, consumed_calories - ?),
                            consumed_protein = MAX(0, consumed_protein - ?),
                            consumed_fat = MAX(0, consumed_fat - ?),
                            consumed_carbs = MAX(0, consumed_carbs - ?)
                        WHERE user_id = ?
                    """, (cal, prot, fat, carb, user_id))
                    
                    # 4. Обновляем график (nutrition_history)
                    today = date.today().isoformat()
                    await db.execute("""
                        UPDATE nutrition_history
                        SET total_calories = MAX(0, total_calories - ?)
                        WHERE user_id = ? AND date = ?
                    """, (cal, user_id, today))
                    
                    await db.commit()
                    
                    await message.answer(f"🗑 <b>Удалено!</b>\nКалории ({int(cal)}) возвращены в лимит.", parse_mode="HTML")
                    
                    # 5. Самое важное: Обновляем кнопку меню, чтобы там удалилась еда
                    await cmd_start(message, state)
                    
                else:
                    await message.answer("⚠️ Не удалось найти эту запись (возможно, она уже удалена).")
                    
    except Exception as e:
        print(f"Ошибка при обработке данных из WebApp: {e}")

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Сброс регистрации
    current_state = await state.get_state()
    if current_state and current_state.startswith("Registration:"):
        await state.clear()

    user_id = message.from_user.id
    name = message.from_user.first_name or "Друг"

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Проверка нового дня
        async with db.execute("SELECT last_water_update FROM users WHERE user_id = ?", (user_id,)) as cursor:
            last_update_row = await cursor.fetchone()
        
        today_str = date.today().isoformat()
        if last_update_row and last_update_row[0] != today_str:
            await db.execute("""
                UPDATE users
                SET consumed_calories = 0, consumed_protein = 0, consumed_fat = 0, consumed_carbs = 0, last_water_update = ?
                WHERE user_id = ?
            """, (today_str, user_id))
            await db.commit()

        # 2. Получаем данные пользователя
        async with db.execute("""
            SELECT weight, height, age, calories_limit, 
                   consumed_calories, consumed_protein, consumed_fat, consumed_carbs 
            FROM users WHERE user_id = ?
        """, (user_id,)) as cursor:
            user_data = await cursor.fetchone()

    if user_data:
        weight, height, age, limit, c_cal, c_prot, c_fat, c_carb = user_data
        
        limit = limit or 2500
        # Расчет лимитов БЖУ
        p_max = int((limit * 0.3) / 4)
        f_max = int((limit * 0.3) / 9)
        c_max = int((limit * 0.4) / 4)

        # === НОВЫЕ СТРОКИ ===
        # 1. Получаем историю для графика
        history_str = await get_current_week_history(user_id)
        
        # 2. Получаем список еды (JSON) и кодируем его
        food_log_json = await get_today_food_json(user_id)
        food_log_encoded = quote(food_log_json)
        # ====================

        base_url = "https://pcrpg2df4s-blip.github.io/diet-app/"
        url_with_params = (
            f"{base_url}?"
            f"calories={limit}&name={name}&weight={weight}&height={height}&age={age}&goal=Цель&"
            f"c_cal={c_cal or 0}&c_prot={c_prot or 0}&c_fat={c_fat or 0}&c_carb={c_carb or 0}&"
            f"p_max={p_max}&f_max={f_max}&c_max={c_max}&"
            f"history={history_str}&"
            f"food_log={food_log_encoded}" # <--- ВОТ ТУТ МЫ ДОБАВИЛИ ЕДУ В ССЫЛКУ
        )

        web_app_info = WebAppInfo(url=url_with_params)
        
        await message.bot.set_chat_menu_button(
            chat_id=user_id,
            menu_button=MenuButtonWebApp(text="Дневник", web_app=web_app_info)
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📱 Открыть Дневник", web_app=web_app_info)]
        ])

        await message.answer(
            f"👋 С возвращением, <b>{name}</b>!\n"
            f"Сегодня съедено: <b>{c_cal or 0} / {limit} ккал</b>\n\n"
            f"Журнал питания обновлен! 🥗", 
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Регистрация
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id, first_name) VALUES (?, ?)", (user_id, name))
            await db.commit()
        
        builder = ReplyKeyboardBuilder()
        builder.add(KeyboardButton(text="М"), KeyboardButton(text="Ж"))
        builder.adjust(2)
        await message.answer(f"Привет, <b>{name}</b>! Начнем настройку. Какой твой пол?", reply_markup=builder.as_markup(resize_keyboard=True), parse_mode="HTML")
        await state.set_state(Registration.gender)

@router.message(Command("eat"))
async def command_eat(message: Message):
    # Пример команды: /eat 500
    try:
        # Берем число из сообщения (делим текст по пробелам и берем вторую часть)
        calories_to_add = int(message.text.split()[1])
        user_id = message.from_user.id
        
        # Для теста примерно раскидаем БЖУ (пропорция 30/20/50)
        prot = int(calories_to_add * 0.3 / 4)
        fat = int(calories_to_add * 0.2 / 9)
        carb = int(calories_to_add * 0.5 / 4)

        # Обновляем базу асинхронно
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("""
                UPDATE users 
                SET consumed_calories = consumed_calories + ?,
                    consumed_protein = consumed_protein + ?,
                    consumed_fat = consumed_fat + ?,
                    consumed_carbs = consumed_carbs + ?
                WHERE user_id = ?
            """, (calories_to_add, prot, fat, carb, user_id))
            await db.commit()
        
        await message.answer(
            f"✅ Добавлено <b>{calories_to_add} ккал</b>!\n"
            f"Напиши /start, чтобы получить новую кнопку с обновленными данными.",
            parse_mode=ParseMode.HTML
        )
        
    except (IndexError, ValueError):
        await message.answer("Ошибка! Пиши так: <code>/eat 500</code>", parse_mode=ParseMode.HTML)

# --- ПРОЦЕСС РЕГИСТРАЦИИ ---
# ==========================================
# 📝 ЛОГИКА РЕГИСТРАЦИИ (ОБНОВЛЕННАЯ)
# ==========================================

@router.message(Registration.gender)
async def process_gender(message: Message, state: FSMContext):
    await state.update_data(gender=message.text)
    
    # 👇 ТУТ МЫ УБИРАЕМ КНОПКИ
    await message.answer("Отлично! Сколько тебе лет? (Напиши число)", reply_markup=ReplyKeyboardRemove())
    
    await state.set_state(Registration.age)

@router.message(Registration.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число.")
        return
    await state.update_data(age=int(message.text))
    await message.answer("Твой рост в см? (например: 180)")
    await state.set_state(Registration.height)

@router.message(Registration.height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число.")
        return
    await state.update_data(height=int(message.text))
    await message.answer("Твой вес в кг? (например: 75)")
    await state.set_state(Registration.weight)

@router.message(Registration.weight)
async def process_weight(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи число.")
        return
    await state.update_data(weight=int(message.text))
    
    # Кнопки активности
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Сидячая"), KeyboardButton(text="Средняя"))
    kb.add(KeyboardButton(text="Высокая"))
    kb.adjust(1)
    
    await message.answer("Твой тип активности (в неделю)?\n•Сидячая 0-1 раз,\n•Средняя 2-4 раза,\n•Высокая 5-7 раз", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(Registration.activity)

@router.message(Registration.activity)
async def process_activity(message: Message, state: FSMContext):
    await state.update_data(activity=message.text)
    
    # Кнопки цели
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="Похудеть"), KeyboardButton(text="Удержать вес"))
    kb.add(KeyboardButton(text="Набрать массу"))
    kb.adjust(1)
    
    await message.answer("Последний шаг! 🎯\nКакая у тебя цель?", reply_markup=kb.as_markup(resize_keyboard=True))
    await state.set_state(Registration.goal)

# 🔥 ФИНАЛ (С МЕНЮ) 🔥
@router.message(Registration.goal)
async def process_goal(message: Message, state: FSMContext):
    await state.update_data(goal=message.text)
    data = await state.get_data()
    
    # 1. СЧИТАЕМ
    bmr = 10 * data['weight'] + 6.25 * data['height'] - 5 * data['age']
    if data['gender'] == 'М': bmr += 5
    else: bmr -= 161
        
    act_coef = 1.2
    if data['activity'] == 'Средняя': act_coef = 1.55
    if data['activity'] == 'Высокая': act_coef = 1.9
    
    daily_calories = int(bmr * act_coef)
    
    if message.text == "Похудеть": daily_calories -= 400
    if message.text == "Набрать массу": daily_calories += 400

    # 2. СОХРАНЯЕМ
    user_id = message.from_user.id
    name = message.from_user.first_name or "Друг"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE users 
            SET age=?, height=?, weight=?, activity=?, goal=?, calories_limit=?, gender=?
            WHERE user_id=?
        """, (data['age'], data['height'], data['weight'], data['activity'], message.text, daily_calories, data['gender'], user_id))
        await db.commit()

    # 3. ГЕНЕРИРУЕМ ССЫЛКУ
    base_url = "https://pcrpg2df4s-blip.github.io/diet-app/"
    import urllib.parse
    encoded_goal = urllib.parse.quote(message.text)
    encoded_name = urllib.parse.quote(name)

    url_with_params = (
        f"{base_url}?"
        f"calories={daily_calories}&name={encoded_name}&weight={data['weight']}&"
        f"height={data['height']}&age={data['age']}&goal={encoded_goal}&"
        f"c_cal=0&c_prot=0&c_fat=0&c_carb=0"
    )

    web_app_info = WebAppInfo(url=url_with_params)
    
    # Кнопка для открытия приложения (Инлайн)
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть Диетолога", web_app=web_app_info)]
    ])

    # 4. ОТПРАВЛЯЕМ ОТВЕТ И СЛЕДОМ ГЛАВНОЕ МЕНЮ
    await message.answer(
        f"🎉 Готово! Твоя норма: <b>{daily_calories} ккал</b>.\n"
        f"Я создал для тебя персональные настройки.", 
        reply_markup=inline_kb, # Сначала кнопка приложения
        parse_mode=ParseMode.HTML
    )
    
    # 👇 ВОТ ОНО - ГЛАВНОЕ МЕНЮ ВЫЛЕЗАЕТ СНИЗУ
    await message.answer("🏠 Главное меню открыто:", reply_markup=main_menu_kb())
    
    await state.clear()

# --- ГЛАВНОЕ МЕНЮ И ЛОГИКА ---

# --- СТАТИСТИКА (С Рисунком) ---
@router.message(F.text == "📊 Статистика")
async def show_progress(message: Message):
    user_id = message.from_user.id
    today = date.today().isoformat()
    
    status_msg = await message.answer("🎨 Рисую красивый график...")

    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Получаем ТОЛЬКО лимит калорий (воду убрали)
        async with db.execute("SELECT calories_limit FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_data = await cursor.fetchone()
            if not user_data:
                await status_msg.delete()
                await message.answer("Сначала заполни профиль! /start")
                return
            limit = user_data[0] if user_data[0] else 2000

        # 2. Данные за сегодня (сколько съели)
        async with db.execute("SELECT SUM(calories) FROM food_log WHERE user_id = ? AND date = ?", (user_id, today)) as cursor:
            res = await cursor.fetchone()
            eaten_today = res[0] if res[0] else 0

        # 3. История за 7 дней
        async with db.execute("""
            SELECT date, SUM(calories) 
            FROM food_log 
            WHERE user_id = ? 
            GROUP BY date 
            ORDER BY date DESC 
            LIMIT 7
        """, (user_id,)) as cursor:
            history_data = await cursor.fetchall()

    # --- ФУНКЦИЯ РИСОВАНИЯ (ОСТАЕТСЯ ПРЕЖНЕЙ, ОНА И ТАК БЫЛА ПРО КАЛОРИИ) ---
    def make_plot(history, daily_limit):
        plt.rcParams.update({
            'font.family': 'sans-serif',
            'font.sans-serif': ['Helvetica', 'Arial', 'DejaVu Sans'],
            'font.size': 10,
            'text.color': '#333333',
            'axes.labelcolor': '#333333',
            'xtick.color': '#555555',
            'ytick.color': '#555555'
        })

        history.reverse()
        dates = [f"{row[0].split('-')[2]}.{row[0].split('-')[1]}" for row in history]
        cals = [row[1] for row in history]
        
        if not dates:
            dates = ["Сегодня"]
            cals = [0]

        fig, ax = plt.subplots(figsize=(8, 4.5))
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_color('#DDDDDD')
        
        ax.grid(axis='y', linestyle='--', alpha=0.3, color='#CCCCCC')
        
        colors = ['#FF3B30' if c > daily_limit else '#4CD964' for c in cals]
        bars = ax.bar(dates, cals, color=colors, width=0.6, zorder=3)
        
        ax.axhline(y=daily_limit, color='#8E8E93', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)

        ax2 = ax.twinx()
        ax2.set_ylim(ax.get_ylim())
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)
        ax2.spines['left'].set_visible(False)
        ax2.spines['bottom'].set_visible(False)
        ax2.set_yticks([daily_limit])
        ax2.set_yticklabels([f"Норма: {daily_limit}"], color='#8E8E93', fontsize=9, fontweight='bold')
        ax2.tick_params(axis='y', length=0)

        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height + 50, 
                        f'{int(height)}', 
                        ha='center', va='bottom', fontsize=10, fontweight='bold', color='#333333')

        plt.title('Динамика калорий (7 дней)', pad=20, fontsize=13, fontweight='bold')
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, transparent=False)
        buf.seek(0)
        plt.close()
        return buf

    photo_file = await asyncio.to_thread(make_plot, history_data, limit)
    
    # --- ОТПРАВКА (ТЕКСТ ТЕПЕРЬ БЕЗ ВОДЫ) ---
    await status_msg.delete()
    
    left = limit - eaten_today
    status = "🟢 В норме" if left >= 0 else "🔴 Перебор"
    
    # Формируем текст только про еду
    text = (
        f"📊 <b>Статистика за сегодня:</b>\n\n"
        f"🔥 Съедено: <b>{eaten_today}</b> / {limit} ккал\n"
        f"🏁 Остаток: <b>{left} ккал</b>\n"
        f"Состояние: {status}"
    )
    
    input_file = BufferedInputFile(photo_file.read(), filename="chart.png")
    await message.answer_photo(photo=input_file, caption=text, parse_mode=ParseMode.HTML)

# --- АНАЛИЗ ФОТО (GEMINI) ---

# Важно: этот блок должен стоять ВЫШЕ, чем блок приема фото
# --- ДОБАВЬ ЭТОТ БЛОК ---
@router.message(F.text == "Отмена")
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()  # Сброс состояния (выход из режима ожидания)
    await message.answer("🏠 Возвращаемся в главное меню.", reply_markup=main_menu_kb())
# ------------------------
# --- 1. НАЧАЛО: КНОПКА "ДОБАВИТЬ ЕДУ" ---
@router.message(F.text == "🍽 Добавить еду")
async def ask_for_food(message: Message, state: FSMContext):
    # Включаем режим ожидания (фото ИЛИ текста)
    await state.set_state(FoodAnalysis.waiting_for_food)
    
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]], 
        resize_keyboard=True
    )
    
    await message.answer("Пришли мне фото или текст своей еды 🥦", reply_markup=kb)
# А ниже уже идет твой старый код для фото:
# @router.message(F.photo)
# async def analyze_photo...

# --- 2. ЕСЛИ ПРИСЛАЛИ ФОТО ---
@router.message(FoodAnalysis.waiting_for_food, F.photo)
async def analyze_food_photo(message: Message, state: FSMContext):
    status_msg = await message.answer("🤖 Смотрю на фото... Анализирую...")
    
    try:
        bot = message.bot
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        file_content = await bot.download_file(file.file_path)
        image_bytes = file_content.read()
        
        prompt = """
        Ты диетолог. Определи блюдо, вес и КБЖУ по фото.
        Верни ответ СТРОГО в таком формате (без лишних слов):
        Название:[Блюдо]
        • Вес: [число] г
        • Калории: [число]
        • Белки: [число]
        • Жиры: [число]
        • Углеводы: [число]
        
        Если еды нет - напиши ОШИБКА.
        """

        # Пауза перед запросом (защита от бана)
        await status_msg.edit_text("⏳ Загружаю информацию (2 сек)...")
        await asyncio.sleep(2) 
        
        # Отправляем запрос
        response = await asyncio.to_thread(
            lambda: model.generate_content(
                [{"mime_type": "image/jpeg", "data": image_bytes}, prompt],
                generation_config={"temperature": 0.2}
            )
        )
        
        await process_food_response(message, state, response.text, status_msg, photo_id=file_id)
        
    except Exception as e:
        print(f"Ошибка: {e}")
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(
                [{"mime_type": "image/jpeg", "data": image_bytes}, prompt],
                generation_config={"temperature": 0}
            )
        )
        
        await process_food_response(message, state, response.text, status_msg, photo_id=file_id)
        
    except Exception as e:
        print(e)
        await status_msg.edit_text("Ошибка обработки фото.")

        # --- 3. ЕСЛИ ПРИСЛАЛИ ТЕКСТ ---
@router.message(FoodAnalysis.waiting_for_food, F.text & ~F.text.in_({"Отмена"}))
async def analyze_food_text(message: Message, state: FSMContext):
    status_msg = await message.answer("👀 Читаю... Считаю калории...")
    
    try:
        # --- ОБНОВЛЕННЫЙ ПРОМПТ С ТОЧКАМИ ---
        prompt = f"""
        Ты диетолог. Пользователь написал: "{message.text}".
        1. Определи блюдо (если вес не указан, возьми средний стандартный).
        2. Посчитай КБЖУ.
        
        Верни ответ СТРОГО в таком формате (без лишних слов):
        Название:[Блюдо]
        • Вес: [число] г
        • Калории: [число]
        • Белки: [число]
        • Жиры: [число]
        • Углеводы: [число]
        
        Если это не еда - напиши ОШИБКА.
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(
                prompt,
                generation_config={"temperature": 0}
            )
        )
        await process_food_response(message, state, response.text, status_msg, photo_id=None)
        
    except Exception as e:
        print(e)
        await status_msg.edit_text("Ошибка обработки текста.")

@router.callback_query(F.data == "confirm_food")
async def save_food_to_db(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    food_data = data.get("food_temp")
    
    if not food_data:
        try: await callback.message.delete()
        except: pass
        await callback.message.answer("⚠️ Данные устарели.")
        await callback.answer()
        return

    # 1. Парсинг данных
    cals = food_data.get('cals', 0)
    import re
    text = food_data.get('raw_text', '')
    def get_val(key):
        match = re.search(rf"{key}.*?(\d+)", text, re.IGNORECASE)
        return int(match.group(1)) if match else 0
    prot = get_val("Белки")
    fats = get_val("Жиры")
    carbs = get_val("Углеводы")

    async with aiosqlite.connect(DB_NAME) as db:
        today_str = date.today().isoformat()
        
        # 1. Пишем в лог еды
        await db.execute("""
            INSERT INTO food_log (user_id, food_name, calories, proteins, fats, carbs, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, food_data['name'], cals, prot, fats, carbs, today_str))
        
        # 2. Обновляем историю для графика
        await db.execute("""
            INSERT INTO nutrition_history (user_id, date, total_calories)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET total_calories = total_calories + ?
        """, (user_id, today_str, float(cals), float(cals)))
        
        # 3. Обновляем профиль пользователя
        await db.execute("""
            UPDATE users 
            SET consumed_calories = consumed_calories + ?,
                consumed_protein = consumed_protein + ?,
                consumed_fat = consumed_fat + ?,
                consumed_carbs = consumed_carbs + ?
            WHERE user_id = ?
        """, (cals, prot, fats, carbs, user_id))
        
        # 4. Читаем обновленные данные
        async with db.execute("""
            SELECT weight, height, age, calories_limit, 
                   consumed_calories, consumed_protein, consumed_fat, consumed_carbs 
            FROM users WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
        
        await db.commit()

    if row:
        weight, height, age, limit, c_cal, c_prot, c_fat, c_carb = row
        name = callback.from_user.first_name or "Gourmet"
        limit = limit or 2500
        
        p_max = int((limit * 0.3) / 4)
        f_max = int((limit * 0.3) / 9)
        c_max = int((limit * 0.4) / 4)

        # === ВОТ ТУТ НОВЫЕ СТРОКИ ===
        # Получаем данные графика
        history_str = await get_current_week_history(user_id)
        
        # Получаем список еды (JSON) и кодируем его для ссылки
        food_log_json = await get_today_food_json(user_id)
        food_log_encoded = quote(food_log_json)
        # ============================

        base_url = "https://pcrpg2df4s-blip.github.io/diet-app/"
        url_with_params = (
            f"{base_url}?"
            f"calories={limit}&name={name}&weight={weight}&height={height}&age={age}&goal=Цель&"
            f"c_cal={c_cal}&c_prot={c_prot}&c_fat={c_fat}&c_carb={c_carb}&"
            f"p_max={p_max}&f_max={f_max}&c_max={c_max}&"
            f"history={history_str}&"
            f"food_log={food_log_encoded}" # <--- ДОБАВИЛИ ПАРАМЕТР СЮДА
        )

        await callback.bot.set_chat_menu_button(
            chat_id=user_id,
            menu_button=MenuButtonWebApp(text="Дневник", web_app=WebAppInfo(url=url_with_params))
        )

        try: await callback.message.delete()
        except: pass
        
        await callback.message.answer(
            f"✅ <b>Записано!</b>\n• {food_data['name']} ({cals} ккал)",
            parse_mode="HTML"
        )
        await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "cancel_food")
async def cancel_food_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Отменено.", reply_markup=main_menu_kb())

    # --- ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ---

from aiogram import F # Убедись, что это есть вверху

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    
    async with aiosqlite.connect(DB_NAME) as db:
        # 👇 МЫ ЧЕТКО ПЕРЕЧИСЛЯЕМ, ЧТО ХОТИМ ДОСТАТЬ (ПОРЯДОК ВАЖЕН!)
        async with db.execute("""
            SELECT first_name, gender, age, height, weight, activity, goal, calories_limit 
            FROM users WHERE user_id = ?
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()

    if row:
        # Распаковываем данные СТРОГО в том же порядке
        name, gender, age, height, weight, activity, goal, limits = row
        
        # Красиво форматируем (защита от None)
        name = name or "Не указано"
        gender = gender or "-"
        age = age or 0
        height = height or 0
        weight = weight or 0
        activity = activity or "Не указана"
        goal = goal or "Не указана"
        limits = limits or 0

        text = (
            f"👤 <b>Твой профиль:</b>\n\n"
            f"👋 Имя: <b>{name}</b>\n"
            f"🚻 Пол: <b>{gender}</b>\n"
            f"🎂 Возраст: <b>{age} лет</b>\n"
            f"📏 Рост: <b>{height} см</b>\n"
            f"⚖️ Вес: <b>{weight} кг</b>\n\n"
            f"🏃 Активность: <b>{activity}</b>\n"
            f"🎯 Цель: <b>{goal}</b>\n"
            f"🔥 Твоя норма: <b>{limits} ккал</b>"
        )
        
        # Добавим кнопку "Изменить", чтобы можно было перепройти опрос
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="reset_profile")]
        ])
        
        await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await message.answer("Профиль не найден. Нажми /start")

# 👇 А ЭТО ЧТОБЫ КНОПКА "ИЗМЕНИТЬ ДАННЫЕ" РАБОТАЛА
@router.callback_query(F.data == "reset_profile")
async def reset_profile_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Хорошо, давай заполним анкету заново!")
    # Запускаем сценарий регистрации вручную (как в /start)
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="М"), KeyboardButton(text="Ж"))
    builder.adjust(2)
    
    await callback.message.answer("Твой пол?", reply_markup=builder.as_markup(resize_keyboard=True))
    await state.set_state(Registration.gender)
    await callback.answer()

# --- 1. ГЕНЕРАЦИЯ МЕНЮ (ПО КОМАНДЕ) ---
@router.message(F.text == "👨‍🍳 Что приготовить?")
async def ask_for_products(message: Message, state: FSMContext):
    await state.set_state(RecipeState.waiting_for_products)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer(
        "📸 Сфоткай открытый холодильник или напиши список продуктов через запятую (например: яйца, творог, овсянка).\n\n"
        "Я придумаю вкусный и полезный рецепт! 🥣", 
        reply_markup=kb
    )

# --- ШЕФ-ПОВАР: ОБРАБОТКА (КОРОТКО И КРАСИВО) ---
@router.message(RecipeState.waiting_for_products)
async def generate_recipe(message: Message, state: FSMContext):
    # 1. Получаем историю
    data = await state.get_data()
    previous_products = data.get("recipe_query", "")
    
    # Проверка отмены
    if message.text and message.text.lower() == "отмена":
        await state.clear()
        await message.answer("👨‍🍳 Готовка отменена.", reply_markup=main_menu_kb())
        return

    status_msg = await message.answer("👨‍🍳 Думаю над рецептом...")
    
    try:
        content = []
        current_query = ""
        
        # 2. Фото или текст
        if message.photo:
            bot = message.bot
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_content = await bot.download_file(file.file_path)
            image_bytes = file_content.read()
            content.append({"mime_type": "image/jpeg", "data": image_bytes})
            current_query = "фото продуктов"
        elif message.text:
            current_query = message.text
        else:
            await status_msg.edit_text("Пришли фото или текст.")
            return

        full_query = f"{previous_products} {current_query}".strip()
        await state.update_data(recipe_query=full_query)

        # 3. ПРОМПТ
        # 3. ПРОМПТ (ИЗМЕНЕННЫЙ ШАБЛОН)
        prompt = f"""
        Ты шеф-повар. Придумай 1 рецепт из: {full_query}.
        
        СТРОГОЕ ТРЕБОВАНИЕ К ФОРМАТУ:
        1. Используй ТОЛЬКО теги <b> и <i>. 
        2. НЕ ИСПОЛЬЗУЙ <details>, <summary>, <ul>, <ol>.
        
        Шаблон ответа для пользователя:
        🍳 <b>Название</b>
        🔥 <b>КБЖУ на порцию:</b> ... ккал (Б: ... | Ж: ... | У: ...)
        
        ⏱ <b>Время:</b> ...
        
        🛒 <b>Ингредиенты:</b>
        - ...
        
        🔪 <b>Рецепт:</b>
        1. ...
        
        💡 <b>Совет:</b> ...

        ВАЖНО: В САМОМ КОНЦЕ ОТВЕТА (после совета) добавь дубликат КБЖУ в скрытом блоке для программы. 
        Напиши СТРОГО в таком формате:
        
        === БЖУ ===
        Название: [Название блюда]
        Калории: [число]
        Белки: [число]
        Жиры: [число]
        Углеводы: [число]
        """
        
        content.append(prompt)
        
        # Пауза
        await status_msg.edit_text("⏳ Подбираю ингредиенты...")
        await asyncio.sleep(2) 
        
        # Запрос
        response = await asyncio.to_thread(
            lambda: model.generate_content(
                content,
                generation_config={"temperature": 0.4}
            )
        )
        
        text = response.text
        
        # --- 🧹 УЛУЧШЕННАЯ ЧИСТКА ТЕКСТА (Fix ошибки Telegram) ---
        # Удаляем всё, что бесит Телеграм
        text = text.replace("```html", "").replace("```", "").strip()
        text = text.replace("<details>", "").replace("</details>", "") # Вот из-за этого была ошибка
        text = text.replace("<summary>", "").replace("</summary>", "")
        text = text.replace("<ul>", "").replace("</ul>", "")
        text = text.replace("<ol>", "").replace("</ol>", "")
        text = text.replace("<li>", "• ").replace("</li>", "\n")
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text) # Markdown bold -> HTML bold
        text = re.sub(r"</?h\d>", "\n", text)
        
        # 1. Сохраняем ВЕСЬ текст (с блоком БЖУ) в память
        await state.update_data(recipe_text=text)
        
        # 2. Кнопка
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Записать", callback_data="save_recipe")]
        ])
        
        # 3. Обрезаем тех. блок
        visible_text = text.split("=== БЖУ ===")[0].strip()
        
        # 4. ОТПРАВКА С ЗАЩИТОЙ (Если HTML сломан — шлем обычный текст)
        await status_msg.delete()
        
        try:
            # Попытка 1: Красивый HTML
            if message.photo:
                 await message.answer_photo(
                    photo=message.photo[-1].file_id,
                    caption=visible_text,
                    parse_mode="HTML",
                    reply_markup=kb
                )
            else:
                await message.answer(visible_text, parse_mode="HTML", reply_markup=kb)
                
        except Exception as e:
            print(f"Ошибка HTML: {e}")
            # Попытка 2: Обычный текст (План Б)
            fallback_text = visible_text.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
            if message.photo:
                 await message.answer_photo(
                    photo=message.photo[-1].file_id,
                    caption=fallback_text,
                    parse_mode=None, # Отключаем форматирование
                    reply_markup=kb
                )
            else:
                await message.answer(fallback_text, parse_mode=None, reply_markup=kb)

    except Exception as e:
        print(f"ОБЩАЯ ОШИБКА: {e}")
        await status_msg.edit_text("⚠️ Ошибка генерации. Попробуй еще раз.")

        # --- ОБРАБОТКА КНОПОК РЕЦЕПТА ---

# 👇 ОБРАБОТЧИК КНОПКИ "✅ ЗАПИСАТЬ" (НОВЫЙ)
@router.callback_query(F.data == "save_recipe")
async def save_recipe_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    recipe_text = data.get("recipe_text")
    user_id = callback.from_user.id
    
    if recipe_text:
        import re
        # Функция поиска цифр в скрытом блоке === БЖУ ===
        def get_val(key):
            match = re.search(rf"{key}.*?(\d+)", recipe_text, re.IGNORECASE)
            return int(match.group(1)) if match else 0
            
        cals = get_val("Калории")
        prot = get_val("Белки")
        fats = get_val("Жиры")
        carbs = get_val("Углеводы")
        
        # Название
        name_match = re.search(r"Название:\s*(.+)", recipe_text)
        food_name = name_match.group(1).strip() if name_match else "Рецепт шефа"

        # ПИШЕМ В БАЗУ И ОБНОВЛЯЕМ ПРИЛОЖЕНИЕ
        async with aiosqlite.connect(DB_NAME) as db:
            # 1. Лог еды
            await db.execute("""
                INSERT INTO food_log (user_id, food_name, calories, proteins, fats, carbs, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, food_name, cals, prot, fats, carbs, date.today().isoformat()))
            
            # 2. Обновляем юзера
            await db.execute("""
                UPDATE users 
                SET consumed_calories = consumed_calories + ?,
                    consumed_protein = consumed_protein + ?,
                    consumed_fat = consumed_fat + ?,
                    consumed_carbs = consumed_carbs + ?
                WHERE user_id = ?
            """, (cals, prot, fats, carbs, user_id))
            
            # 3. Читаем новые итоги для кнопки
            async with db.execute("""
                SELECT weight, height, age, calories_limit, 
                       consumed_calories, consumed_protein, consumed_fat, consumed_carbs 
                FROM users WHERE user_id = ?
            """, (user_id,)) as cursor:
                user_data = await cursor.fetchone()
            
            await db.commit()

        # ... (начало функции не трогаем) ...
        # ... (после того как достали user_data из базы) ...

        weight, height, age, limit, c_cal, c_prot, c_fat, c_carb = user_data
        name = callback.from_user.first_name or "Gourmet"
        limit = limit or 2500
        
        # 👇 НОВАЯ СТРОКА: Получаем историю
        history_str = await get_current_week_history(user_id)

        base_url = "https://pcrpg2df4s-blip.github.io/diet-app/"
        url_with_params = (
            f"{base_url}?"
            f"calories={limit}&name={name}&weight={weight}&height={height}&age={age}&goal=Цель&"
            f"c_cal={c_cal or 0}&c_prot={c_prot or 0}&c_fat={c_fat or 0}&c_carb={c_carb or 0}&"
            f"history={history_str}" # 👈 ДОБАВИЛИ ПАРАМЕТР СЮДА
        )

        await callback.bot.set_chat_menu_button(
            chat_id=user_id,
            menu_button=MenuButtonWebApp(text="Дневник", web_app=WebAppInfo(url=url_with_params))
        )
        
        # ... (дальше ответ бота "Записано" и callback.answer) ...

        # Финальный ответ
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ <b>Записано!</b>\n🥘 {food_name} (+{cals} ккал)", 
            reply_markup=main_menu_kb(),
            parse_mode="HTML"
        )
    else:
        await callback.message.answer("Рецепт устарел.")
    
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "refine_recipe")
async def ask_refinement(callback: CallbackQuery, state: FSMContext):
    # Мы остаемся в состоянии RecipeState.waiting_for_products
    # Но теперь бот знает, что у него есть предыдущий контекст (в recipe_query)
    
    await callback.message.answer(
        "Что добавить или изменить? Напиши ингредиент (например: 'добавь курицу' или 'убеди лук'). 🥕", 
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )
    await callback.answer()

    # --- АНАЛИЗАТОР СОСТАВА (YUKA STYLE) ---

@router.message(F.text == "🔍 Разбор состава")
async def start_ingredients_analysis(message: Message, state: FSMContext):
    await state.set_state(IngredientAnalysis.waiting_for_product)
    
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    
    await message.answer(
        "📸 <b>Пришли фото состава</b> (с задней стороны упаковки) или скопируй текст сюда.\n\n"
        "Я найду скрытый сахар, вредные добавки и поставлю честную оценку от 0 до 100! 🧐",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

@router.message(IngredientAnalysis.waiting_for_product)
async def analyze_ingredients(message: Message, state: FSMContext):
    # Проверка отмены
    if message.text and message.text.lower() == "отмена":
        await state.clear()
        await message.answer("Анализ отменен.", reply_markup=main_menu_kb())
        return

    status_msg = await message.answer("🧐 Изучаю этикетку... Ищу подвох...")
    
    try:
        content = []
        
        if message.photo:
            bot = message.bot
            file_id = message.photo[-1].file_id
            file = await bot.get_file(file_id)
            file_content = await bot.download_file(file.file_path)
            image_bytes = file_content.read()
            content.append({"mime_type": "image/jpeg", "data": image_bytes})
            query_type = "фото состава продукта"
        elif message.text:
            content.append(message.text)
            query_type = "текст состава: " + message.text
        else:
            await status_msg.edit_text("Пришли фото или текст.")
            return

        # --- ОБНОВЛЕННЫЙ ПРОМПТ (С ЖЕСТКИМ ПРИМЕРОМ ОЦЕНКИ) ---
        prompt = f"""
        Ты строгий нутрициолог-эксперт. Оцени состав продукта: {query_type}.
        
        ИНСТРУКЦИЯ ПО РАСЧЕТУ БАЛЛОВ:
        1. Изначально 100 баллов.
        2. Вычитай: Сахар (-15), Трансжиры/Маргарин (-30), Е-добавки (-10 за каждую), Пальмовое масло (-10).
        3. Результат не может быть ниже 0.

        ИНСТРУКЦИЯ ПО ОФОРМЛЕНИЮ:
        1. Используй ТОЛЬКО HTML-тег <b>Текст</b> для жирного.
        2. Списки делай через символ "• ".
        
        ФОРМАТ ОТВЕТА (СТРОГО):
        
        <b>Оценка: [ЧИСЛО]/100 [ЦВЕТНОЙ КРУГ]</b>
        (Пример: <b>Оценка: 55/100 🟡</b>)
        
        🏷 <b>Вердикт:</b> [Краткий вывод]
        
        ⚠️ <b>Минусы:</b>
        • [Ингредиент] - [Кратко в 2-4 словах, почему это вредно]
        (Пример: • Е450 - вымывает кальций)
        
        ✅ <b>Плюсы:</b>
        • ...
        
        💡 <b>Резюме:</b> ...

        КРИТЕРИИ ЦВЕТА: 0-30: 🔴, 31-50: 🟠, 51-75: 🟡, 76-100: 🟢
        """
        
        content.append(prompt)
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(
                content,
                generation_config={"temperature": 0.3}
            )
        )
        
        text = response.text
        
        # --- ЧИСТКА ТЕКСТА ---
        text = text.replace("```html", "").replace("```", "").strip()
        text = re.sub(r'\s*\(\-\d+\)', '', text) # Убираем (-15)
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text) # Markdown -> HTML
        text = re.sub(r'^\s*\*\s+', '• ', text, flags=re.MULTILINE)
        
        # КНОПКИ
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="🔄 Новый разбор", callback_data="new_analysis"))
        kb.add(InlineKeyboardButton(text="🏠 В меню", callback_data="stop_analysis"))
        
        await status_msg.delete()
        
        await message.answer(
            text, 
            reply_markup=kb.as_markup(), 
            parse_mode=ParseMode.HTML
        )
        
        await state.clear()

    except Exception as e:
        print(f"Ошибка анализа: {e}")
        try:
             await status_msg.edit_text(f"Результат:\n\n{response.text}")
        except:
             await status_msg.edit_text("Не удалось прочитать состав. Попробуй еще раз.")

        # Обработка кнопки "Новый разбор"
@router.callback_query(F.data == "new_analysis")
async def restart_analysis(callback: CallbackQuery, state: FSMContext):
    await callback.answer() # Убираем часики загрузки
    
    # Снова включаем режим ожидания фото
    await state.set_state(IngredientAnalysis.waiting_for_product)
    
    # Можно удалить старое сообщение с результатом, чтобы не засорять чат (по желанию)
    # await callback.message.delete() 
    
    await callback.message.answer(
        "📸 <b>Жду следующий продукт!</b>\nСкидывай фото или текст.", 
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )

# Обработка кнопки "В меню"
@router.callback_query(F.data == "stop_analysis")
async def stop_analysis_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    # Удаляем сообщение с результатом (опционально) или просто пишем "Меню"
    await callback.message.delete()
    
    await callback.message.answer("🏠 Возвращаемся в главное меню.", reply_markup=main_menu_kb())
    
    # --- СОСТОЯНИЕ ДЛЯ ДИАЛОГА ---
class Chat(StatesGroup):
    talking = State()

# 1. Вход в режим Диетолога
@router.message(F.text == "👨‍⚕️ Диетолог")
async def start_chat_mode(message: Message, state: FSMContext):
    await state.set_state(Chat.talking)
    
    # Кнопка выхода
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Закончить")]], resize_keyboard=True)
    
    await message.answer(
        "👨‍⚕️ Привет! Я твой персональный AI-диетолог.\n"
        "Спрашивай меня о чём угодно: про диеты, продукты, тренировки или рецепты.\n\n"
        "<i>Нажми 'Закончить', чтобы выйти в меню.</i>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )

# 2. Выход из режима
@router.message(Chat.talking, F.text == "Закончить")
async def stop_chat_mode(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Возвращаемся в меню.", reply_markup=main_menu_kb())

# 3. Обработка вопросов (отправляем в Gemini)
@router.message(Chat.talking)
async def chat_with_dietologist(message: Message):
    status_msg = await message.answer("🤔 Думаю...")
    
    try:
        # Простой промпт для диалога
        prompt = f"""
        Ты — профессиональный, дружелюбный диетолог.
        Твоя цель: помогать пользователю с питанием и здоровьем.
        
        ПРАВИЛА ОБЩЕНИЯ:
        1. Отвечай кратко и по делу.
        2. 🚫 НЕ ЗДОРОВАЙСЯ В НАЧАЛЕ (не пиши "Привет", "Здравствуйте"), если пользователь сам не поздоровался.
        3. Если вопрос непонятен, переспроси или отшутись
        4. Старайся разговаривать только на тему диеты, питания, спорта, пищи.
        
        Сообщение пользователя: {message.text}
        """
        
        response = await asyncio.to_thread(
            lambda: model.generate_content(prompt)
        )
        
        # Убираем Markdown звездочки, если есть
        clean_text = response.text.replace("**", "").replace("##", "")
        
        await status_msg.edit_text(clean_text)
        
    except Exception as e:
        await status_msg.edit_text("Ой, я немного устал. Спроси позже!")

        # --- ЭТУ ФУНКЦИЮ НУЖНО ДОБАВИТЬ В ФАЙЛ (ЧТОБЫ РАБОТАЛ АНАЛИЗ) ---
# --- ОБНОВЛЕННАЯ ФУНКЦИЯ (БЕЗ ЛИШНИХ КАРТИНОК) ---
async def process_food_response(message: Message, state: FSMContext, text_resp: str, status_msg: Message, photo_id: str | None):
    text_resp = text_resp.strip()
    
    if "ОШИБКА" in text_resp:
        await status_msg.edit_text("😕 Не похоже на еду. Попробуй еще раз.")
        return

    # Парсим данные
    lines = text_resp.split('\n')
    parsed_data = {}
    for line in lines:
        if ":" in line:
            key, val = line.split(":", 1)
            clean_key = key.replace("•", "").replace("-", "").strip()
            parsed_data[clean_key] = val.strip()

    name = parsed_data.get("Название", "Еда")
    cals = parsed_data.get("Калории", "0")
    
    # Очищаем текст от названия
    stats_text = text_resp.replace(f"Название: {name}", "").replace(f"Название:{name}", "").strip()

    # Сохраняем
    await state.update_data(food_temp={
        "name": name,
        "cals": int(''.join(filter(str.isdigit, cals))),
        "raw_text": text_resp
    })
    
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="✅ Да, записать", callback_data="confirm_food"))
    kb.add(InlineKeyboardButton(text="❌ Нет, ошибка", callback_data="cancel_food"))
    
    await status_msg.delete()
    
    # Текст ответа
    response_text = f"<b>🧐 Я вижу: {name}</b>\n\n{stats_text}\n\nВсё верно?"
    
    # ГЛАВНОЕ ИЗМЕНЕНИЕ ЗДЕСЬ:
    if photo_id:
        # Если есть ID фото (значит скинули фотку) — прикрепляем её
        await message.answer_photo(
            photo=photo_id,
            caption=response_text,
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )
    else:
        # Если ID нет (значит был текст) — шлем просто сообщение
        await message.answer(
            text=response_text,
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.HTML
        )

# --- ЗАПУСК БОТА ---
async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    print("Бот запущен...")
    await dp.start_polling(Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")