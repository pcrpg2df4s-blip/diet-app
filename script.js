// 1. ИНИЦИАЛИЗАЦИЯ TELEGRAM
let tg = null;
try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
    }
} catch (e) { console.error(e); }

// 2. ДАННЫЕ ИЗ URL
const urlParams = new URLSearchParams(window.location.search);
let currentData = {
    calories: urlParams.get('calories') || "2500",
    name: decodeURI(urlParams.get('name') || "User"),
    weight: urlParams.get('weight') || "70",
    goal: decodeURI(urlParams.get('goal') || "Form"),
    c_cal: urlParams.get('c_cal') || "0",
    c_prot: urlParams.get('c_prot') || "0",
    c_fat: urlParams.get('c_fat') || "0",
    c_carb: urlParams.get('c_carb') || "0"
};

// 3. ФУНКЦИЯ: ГЕНЕРАЦИЯ КАЛЕНДАРЯ
function generateCalendar() {
    const container = document.getElementById('week-days-row');
    if (!container) return;
    container.innerHTML = '';

    const days = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];
    const today = new Date().getDay(); // 0 = ВС, 1 = ПН
    const todayIndex = today === 0 ? 6 : today - 1; 

    // Простая логика дат (можно усложнить, если нужно реальные даты)
    const curr = new Date(); 
    const first = curr.getDate() - curr.getDay() + 1; 

    days.forEach((d, index) => {
        const dayNum = new Date(curr.setDate(first + index)).getDate(); 
        const el = document.createElement('div');
        el.className = `day-item ${index === todayIndex ? 'active' : ''}`;
        el.innerHTML = `<span class="day-name">${d}</span><span class="day-num">${dayNum}</span>`;
        container.appendChild(el);
    });
}

// 4. ФУНКЦИЯ: РИСУЕМ КРУГ
function setCircle(id, current, max, radius) {
    const circle = document.getElementById(id);
    if (!circle) return;

    const circumference = 2 * Math.PI * radius;
    // Если переел, круг полный (100%)
    const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
    const offset = circumference - (percent / 100) * circumference;

    circle.style.strokeDasharray = `${circumference} ${circumference}`;
    circle.style.strokeDashoffset = offset;
}

// 5. ГЛАВНАЯ ФУНКЦИЯ ОБНОВЛЕНИЯ UI
function updateUI() {
    // --- СЧИТАЕМ ЦИФРЫ ---
    const goal = parseInt(currentData.calories) || 1;
    const consumed = parseInt(currentData.c_cal) || 0;
    const remaining = goal - consumed; // Остаток

    const p_cur = parseInt(currentData.c_prot) || 0;
    const f_cur = parseInt(currentData.c_fat) || 0;
    const c_cur = parseInt(currentData.c_carb) || 0;

    // Цели БЖУ (30% / 30% / 40%)
    const p_goal = Math.round((goal * 0.3) / 4);
    const f_goal = Math.round((goal * 0.3) / 9);
    const c_goal = Math.round((goal * 0.4) / 4);

    // --- ОБНОВЛЯЕМ ТЕКСТ НА ЭКРАНЕ ---
    
    // Большая цифра "Осталось"
    const elCalLeft = document.getElementById('cal-left-display');
    if(elCalLeft) elCalLeft.innerText = remaining > 0 ? remaining : 0;

    // Цифры БЖУ (сколько осталось)
    safeSetText('prot-left', `${Math.max(0, p_goal - p_cur)}г`);
    safeSetText('fat-left', `${Math.max(0, f_goal - f_cur)}г`);
    safeSetText('carb-left', `${Math.max(0, c_goal - c_cur)}г`);

    // --- ОБНОВЛЯЕМ КРУГИ ---
    // Главный круг (прогресс потребления)
    setCircle('cal-progress-circle', consumed, goal, 50);

    // Маленькие круги
    setCircle('prot-ring', p_cur, p_goal, 20);
    setCircle('carb-ring', c_cur, c_goal, 20);
    setCircle('fat-ring', f_cur, f_goal, 20);

    // --- СПИСОК ЕДЫ ---
    renderFoodList(urlParams.get('food_log'));
}

// Хелпер
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if(el) el.innerText = text;
}

// 6. СПИСОК ЕДЫ
function renderFoodList(raw) {
    const con = document.getElementById('recent-food-list');
    if(!con) return;
    
    if(!raw) { con.innerHTML = '<p style="text-align:center;color:#ccc;margin-top:20px">Пока пусто</p>'; return; }
    
    try {
        let list = JSON.parse(decodeURIComponent(raw));
        list = list.reverse().slice(0, 4); // Берем последние 4

        if(list.length === 0) {
            con.innerHTML = '<p style="text-align:center;color:#ccc">Пока пусто</p>'; return;
        }

        con.innerHTML = '';
        list.forEach(item => {
            const card = document.createElement('div');
            card.className = 'food-card';
            card.innerHTML = `
                <div class="food-info">
                    <h4>${item.name}</h4>
                    <div class="food-cal-time"><i class="fa-solid fa-fire"></i> ${item.cal} ккал</div>
                </div>
                <button class="btn-delete" onclick="deleteFood(${item.id})">
                    <i class="fa-solid fa-trash"></i>
                </button>
            `;
            con.appendChild(card);
        });
    } catch(e) { console.error(e); }
}

// 7. УДАЛЕНИЕ
window.deleteFood = function(id) {
    if(!confirm('Удалить запись?')) return;
    if(tg) {
        tg.sendData(JSON.stringify({ action: 'delete_food', id: id }));
    }
};

// ЗАПУСК
document.addEventListener('DOMContentLoaded', function() {
    generateCalendar();
    updateUI();
});