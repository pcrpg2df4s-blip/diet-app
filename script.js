// ==========================================
// 1. ИНИЦИАЛИЗАЦИЯ ТЕЛЕГРАМА (САМОЕ ВАЖНОЕ)
// ==========================================
let tg = null;
try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand(); // Раскрыть на весь экран
    }
} catch (e) {
    console.error("Ошибка Telegram:", e);
}

// ==========================================
// 2. ГЛОБАЛЬНАЯ ФУНКЦИЯ УДАЛЕНИЯ
// ==========================================
window.deleteFood = function(id) {
    // 1. Спрашиваем подтверждение
    if (!confirm('Удалить эту запись?')) return;

    // 2. Проверяем, работает ли Телеграм
    if (!tg) {
        alert("Ошибка: Приложение открыто не в Telegram или скрипт не загрузился.");
        return;
    }

    try {
        // 3. Готовим данные
        const data = JSON.stringify({
            action: 'delete_food',
            id: id
        });
        
        // 4. Отправляем!
        tg.sendData(data);
        
        // 5. На всякий случай закрываем окно принудительно (если sendData тупит)
        setTimeout(() => {
            tg.close();
        }, 100);

    } catch (error) {
        alert("Ошибка отправки: " + error.message);
    }
};

// ==========================================
// 3. ОСНОВНОЙ КОД СТРАНИЦЫ
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    
    const urlParams = new URLSearchParams(window.location.search);
    
    // --- Сбор данных ---
    let currentData = {
        calories: urlParams.get('calories') || "2500",
        name: decodeURI(urlParams.get('name') || "Гость"),
        weight: urlParams.get('weight') || "70",
        height: urlParams.get('height') || "175",
        age: urlParams.get('age') || "25",
        goal: decodeURI(urlParams.get('goal') || "Быть в форме"),
        c_cal: urlParams.get('c_cal') || "0",
        c_prot: urlParams.get('c_prot') || "0",
        c_fat: urlParams.get('c_fat') || "0",
        c_carb: urlParams.get('c_carb') || "0"
    };

    // --- Обновление UI ---
    function safeSetText(id, text) {
        const el = document.getElementById(id);
        if (el) el.innerText = text;
    }

    function updateUI() {
        safeSetText('target-calories', currentData.calories);
        safeSetText('profile-name', currentData.name);
        safeSetText('user-weight', currentData.weight);
        safeSetText('user-height', currentData.height);
        safeSetText('user-age', currentData.age);
        safeSetText('user-goal', currentData.goal);

        safeSetText('stats-calories-today', `${currentData.c_cal} ккал`);
        safeSetText('consumed-val', parseInt(currentData.c_cal));

        // Круг прогресса
        const goal = parseInt(currentData.calories);
        const consumed = parseInt(currentData.c_cal);
        const percent = Math.min((consumed / goal) * 100, 100);
        const circle = document.querySelector('.progress-ring__circle');
        if (circle) {
            const radius = circle.r.baseVal.value;
            const circumference = 2 * Math.PI * radius;
            circle.style.strokeDasharray = `${circumference} ${circumference}`;
            circle.style.strokeDashoffset = circumference - (percent / 100) * circumference;
        }

        // БЖУ
        const p_max = urlParams.get('p_max') || Math.round((goal * 0.3) / 4);
        const f_max = urlParams.get('f_max') || Math.round((goal * 0.3) / 9);
        const c_max = urlParams.get('c_max') || Math.round((goal * 0.4) / 4);

        const p_cur = parseInt(currentData.c_prot) || 0;
        const f_cur = parseInt(currentData.c_fat) || 0;
        const c_cur = parseInt(currentData.c_carb) || 0;

        safeSetText('prot-val', p_cur); safeSetText('prot-max', p_max);
        safeSetText('fat-val', f_cur);  safeSetText('fat-max', f_max);
        safeSetText('carb-val', c_cur); safeSetText('carb-max', c_max);

        setBar('prot-bar', p_cur, p_max);
        setBar('fat-bar', f_cur, f_max);
        setBar('carb-bar', c_cur, c_max);
        
        // Отрисовка списка еды
        const foodLogParam = urlParams.get('food_log');
        renderFoodList(foodLogParam);
    }

    function setBar(id, current, max) {
        const bar = document.getElementById(id);
        if (bar) {
            const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
            bar.style.width = `${percent}%`;
            if (current > max) bar.style.setProperty('background', '#ff4b4b', 'important');
            else bar.style.removeProperty('background');
        }
    }

    // --- Отрисовка карточек ---
    function renderFoodList(foodLogRaw) {
        const listContainer = document.getElementById('food-list');
        if (!listContainer) return;

        if (!foodLogRaw) {
            listContainer.innerHTML = '<p style="text-align:center; color:#888; margin-top:20px;">Пока пусто</p>';
            return;
        }

        try {
            const foodList = JSON.parse(decodeURIComponent(foodLogRaw));
            if (foodList.length === 0) {
                 listContainer.innerHTML = '<p style="text-align:center; color:#888; margin-top:20px;">Сегодня записей нет</p>';
                 return;
            }

            listContainer.innerHTML = ''; 

            foodList.forEach(item => {
                const card = document.createElement('div');
                card.className = 'food-card';
                card.innerHTML = `
                    <button class="btn-delete" onclick="deleteFood(${item.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                    <div class="food-header"><div class="food-name">${item.name}</div></div>
                    <div class="food-calories">${item.cal} ккал</div>
                    <div class="food-macros">
                        <div class="macro-item macro-prot">🥩 <span>${item.p}</span></div>
                        <div class="macro-item macro-fat">🥑 <span>${item.f}</span></div>
                        <div class="macro-item macro-carb">🥖 <span>${item.c}</span></div>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        } catch (e) {
            console.error(e);
        }
    }

    updateUI();

    // --- Навигация и График ---
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(nav => nav.classList.remove('active'));
            document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));
            item.classList.add('active');
            const targetId = item.getAttribute('href').substring(1);
            document.getElementById(targetId).classList.add('active');
            if (targetId === 'stats') initStatsChart();
        });
    });

    // График статистики
    let statsChart = null;
    function initStatsChart() {
        const ctx = document.getElementById('caloriesChart');
        if (!ctx) return;
        
        const historyStr = urlParams.get('history') || '0,0,0,0,0,0,0';
        const historyData = historyStr.split(',').map(Number);
        
        // Обновляем текущий день
        const todayIndex = (new Date().getDay() + 6) % 7;
        historyData[todayIndex] = parseInt(currentData.c_cal) || 0;

        if (!statsChart) { 
            statsChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'],
                    datasets: [{
                        label: 'Калории',
                        data: historyData,
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.2)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#4CAF50'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true }, x: { grid: { display: false } } },
                    plugins: { legend: { display: false } }
                }
            });
        }
    }
    
    if (document.getElementById('stats').classList.contains('active')) {
        initStatsChart();
    }
});