// ==========================================
// 1. ИНИЦИАЛИЗАЦИЯ TELEGRAM WEBAPP
// ==========================================
let tg = null;
try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
        // Можно включить черный статус-бар для красоты
        // tg.setHeaderColor('#F7F7F7'); 
    }
} catch (e) { console.error(e); }

// ==========================================
// 2. СБОР ДАННЫХ ИЗ URL
// ==========================================
const urlParams = new URLSearchParams(window.location.search);
let currentData = {
    // Основные данные
    calories: urlParams.get('calories') || "2500",
    name: decodeURI(urlParams.get('name') || "User"),
    weight: urlParams.get('weight') || "70",
    goal: decodeURI(urlParams.get('goal') || "Form"),
    
    // Потребленное
    c_cal: urlParams.get('c_cal') || "0",
    c_prot: urlParams.get('c_prot') || "0",
    c_fat: urlParams.get('c_fat') || "0",
    c_carb: urlParams.get('c_carb') || "0"
};

// ==========================================
// 3. ФУНКЦИЯ: ГЕНЕРАЦИЯ КАЛЕНДАРЯ (ПН-ВС)
// ==========================================
function generateCalendar() {
    const container = document.getElementById('week-days-row');
    if (!container) return;
    container.innerHTML = '';

    const days = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];
    const today = new Date().getDay(); // 0 = Воскресенье, 1 = Понедельник...
    
    // Превращаем формат JS (0=ВС) в наш (0=ПН ... 6=ВС)
    const todayIndex = today === 0 ? 6 : today - 1; 

    // Генерируем даты текущей недели
    const curr = new Date(); 
    // Находим понедельник этой недели
    const first = curr.getDate() - curr.getDay() + 1; 

    days.forEach((d, index) => {
        // Создаем дату для каждого дня
        const date = new Date(curr.setDate(first + index));
        const dayNum = date.getDate(); 
        
        const el = document.createElement('div');
        // Если индекс совпадает с сегодня - добавляем класс active
        el.className = `day-item ${index === todayIndex ? 'active' : ''}`;
        el.innerHTML = `
            <span class="day-name">${d}</span>
            <span class="day-num">${dayNum}</span>
        `;
        container.appendChild(el);
    });
}

// ==========================================
// 4. ФУНКЦИЯ: РИСОВАНИЕ КРУГА (ПРОГРЕСС)
// ==========================================
function setCircle(id, current, max, radius) {
    const circle = document.getElementById(id);
    if (!circle) return;

    const circumference = 2 * Math.PI * radius;
    // Считаем процент (не больше 100%)
    const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
    
    // Считаем отступ линии (чем меньше отступ, тем длиннее линия)
    const offset = circumference - (percent / 100) * circumference;

    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    circle.style.strokeDashoffset = offset;
}

// ==========================================
// 5. ГЛАВНАЯ ФУНКЦИЯ ОБНОВЛЕНИЯ ЭКРАНА
// ==========================================
function updateUI() {
    // --- 1. ПРЕВРАЩАЕМ ТЕКСТ В ЧИСЛА ---
    const goal = parseInt(currentData.calories) || 1;
    const consumed = parseInt(currentData.c_cal) || 0;
    const remaining = goal - consumed; // ОСТАТОК

    const p_cur = parseInt(currentData.c_prot) || 0;
    const f_cur = parseInt(currentData.c_fat) || 0;
    const c_cur = parseInt(currentData.c_carb) || 0;

    // Рассчитываем цели БЖУ (30% белки, 30% жиры, 40% угли)
    const p_goal = Math.round((goal * 0.3) / 4);
    const f_goal = Math.round((goal * 0.3) / 9);
    const c_goal = Math.round((goal * 0.4) / 4);

    // --- 2. ОБНОВЛЯЕМ ЦИФРЫ НА ЭКРАНЕ ---
    
    // Большая цифра "Осталось"
    const elCalLeft = document.getElementById('cal-left-display');
    if(elCalLeft) elCalLeft.innerText = remaining > 0 ? remaining : 0;

    // Цифры БЖУ (Остаток грамм)
    safeSetText('prot-left', `${Math.max(0, p_goal - p_cur)}г`);
    safeSetText('fat-left', `${Math.max(0, f_goal - f_cur)}г`);
    safeSetText('carb-left', `${Math.max(0, c_goal - c_cur)}г`);

    // --- 3. ОБНОВЛЯЕМ КРУГИ ---
    
    // Главный круг с огнем (Радиус 50)
    setCircle('cal-progress-circle', consumed, goal, 50);

    // Маленькие круги БЖУ (Радиус 20)
    setCircle('prot-ring', p_cur, p_goal, 20); // Красный
    setCircle('carb-ring', c_cur, c_goal, 20); // Желтый
    setCircle('fat-ring', f_cur, f_goal, 20);  // Синий

    // --- 4. ГРУЗИМ СПИСОК ЕДЫ ---
    renderFoodList(urlParams.get('food_log'));
}

// Вспомогательная функция для безопасной вставки текста
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if(el) el.innerText = text;
}

// ==========================================
// 6. ОТРИСОВКА СПИСКА ЕДЫ
// ==========================================
function renderFoodList(raw) {
    const con = document.getElementById('recent-food-list');
    if(!con) return;
    
    // Если данных нет
    if(!raw) { 
        con.innerHTML = '<p style="text-align:center;color:#ccc;margin-top:20px">Список пуст</p>'; 
        return; 
    }
    
    try {
        let list = JSON.parse(decodeURIComponent(raw));
        // Берем последние 4 записи и переворачиваем (новые сверху)
        list = list.reverse().slice(0, 4);

        if(list.length === 0) {
            con.innerHTML = '<p style="text-align:center;color:#ccc;margin-top:20px">Список пуст</p>'; 
            return;
        }

        con.innerHTML = '';
        list.forEach(item => {
            const card = document.createElement('div');
            card.className = 'food-card';
            
            // Вставляем HTML карточки
            card.innerHTML = `
                <div class="food-info">
                    <h4>${item.name}</h4>
                    <div class="food-cal-time">
                        <i class="fa-solid fa-fire"></i> ${item.cal} ккал
                    </div>
                </div>
                <button class="btn-delete" onclick="deleteFood(${item.id})">
                    <i class="fa-solid fa-trash"></i>
                </button>
            `;
            con.appendChild(card);
        });
    } catch(e) { console.error(e); }
}

// ==========================================
// 7. ФУНКЦИЯ УДАЛЕНИЯ
// ==========================================
window.deleteFood = function(id) {
    // Спрашиваем подтверждение
    if(!confirm('Удалить эту запись?')) return;
    
    if(tg) {
        // Отправляем команду боту
        tg.sendData(JSON.stringify({ action: 'delete_food', id: id }));
    } else {
        alert("В Телеграме это удалит запись ID: " + id);
    }
};

// ==========================================
// 8. ЗАПУСК ПРИ ЗАГРУЗКЕ
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    generateCalendar(); // Рисуем дни недели
    updateUI();         // Обновляем цифры и круги

    // Логика переключения вкладок (если нижнее меню есть)
    document.querySelectorAll('.nav-item').forEach(i => i.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-item, .content-section').forEach(x => x.classList.remove('active'));
        i.classList.add('active');
        document.getElementById(i.getAttribute('href').substring(1)).classList.add('active');
    }));
});