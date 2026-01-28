document.addEventListener('DOMContentLoaded', function() {
    
    // ==========================================
    // 1. СБОР ДАННЫХ (МОЗГИ 🧠)
    // ==========================================
    const urlParams = new URLSearchParams(window.location.search);
    
    let currentData = {
        calories: urlParams.get('calories') || localStorage.getItem('user_calories') || "2500",
        name: urlParams.get('name') || localStorage.getItem('user_name') || "Гость",
        weight: urlParams.get('weight') || localStorage.getItem('user_weight') || "70",
        height: urlParams.get('height') || localStorage.getItem('user_height') || "175",
        age: urlParams.get('age') || localStorage.getItem('user_age') || "25",
        goal: urlParams.get('goal') || localStorage.getItem('user_goal') || "Быть в форме",
        c_cal: urlParams.get('c_cal') || localStorage.getItem('user_c_cal') || "0",
        c_prot: urlParams.get('c_prot') || localStorage.getItem('user_c_prot') || "0",
        c_fat: urlParams.get('c_fat') || localStorage.getItem('user_c_fat') || "0",
        c_carb: urlParams.get('c_carb') || localStorage.getItem('user_c_carb') || "0"
    };

    try {
        currentData.goal = decodeURI(currentData.goal);
        currentData.name = decodeURI(currentData.name);
    } catch (e) {}

    if (urlParams.get('calories')) {
        Object.keys(currentData).forEach(key => {
            localStorage.setItem(`user_${key}`, currentData[key]);
        });
    }

    // ==========================================
    // 2. ОБНОВЛЕНИЕ UI
    // ==========================================
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

        // Update calories on stats page
        safeSetText('stats-calories-today', `${currentData.c_cal} ккал`);

        const goal = parseInt(currentData.calories);
        const consumed = parseInt(currentData.c_cal);
        safeSetText('consumed-val', consumed);

        const remaining = goal - consumed;
        const remainEl = document.querySelector('.stat-side .stat-val'); 
        if (remainEl) remainEl.innerText = remaining > 0 ? remaining : 0;

        const percent = Math.min((consumed / goal) * 100, 100);
        const circle = document.querySelector('.progress-ring__circle');
        if (circle) {
            const radius = circle.r.baseVal.value;
            const circumference = 2 * Math.PI * radius;
            circle.style.strokeDasharray = `${circumference} ${circumference}`;
            const offset = circumference - (percent / 100) * circumference;
            circle.style.strokeDashoffset = offset;
        }

        // Лимиты БЖУ (передаются из Python или считаются тут)
        const p_max_param = urlParams.get('p_max');
        const f_max_param = urlParams.get('f_max');
        const c_max_param = urlParams.get('c_max');

        const protMax = p_max_param ? parseInt(p_max_param) : Math.round((goal * 0.3) / 4);
        const fatMax = f_max_param ? parseInt(f_max_param) : Math.round((goal * 0.3) / 9);
        const carbMax = c_max_param ? parseInt(c_max_param) : Math.round((goal * 0.4) / 4);

        safeSetText('prot-max', protMax);
        safeSetText('fat-max', fatMax);
        safeSetText('carb-max', carbMax);

        const protCur = parseInt(currentData.c_prot) || 0;
        const fatCur = parseInt(currentData.c_fat) || 0;
        const carbCur = parseInt(currentData.c_carb) || 0;

        safeSetText('prot-val', protCur);
        safeSetText('fat-val', fatCur);
        safeSetText('carb-val', carbCur);

        setBar('prot-bar', protCur, protMax);
        setBar('fat-bar', fatCur, fatMax);
        setBar('carb-bar', carbCur, carbMax);

        // === ОТРИСОВКА ИСТОРИИ ЕДЫ (ИСПРАВЛЕНО) ===
        const foodLogParam = urlParams.get('food_log');
        if (foodLogParam) {
            try {
                const foodLog = JSON.parse(decodeURIComponent(foodLogParam));
                renderFoodHistory(foodLog);
            } catch (e) {
                console.error("Error parsing food log:", e);
            }
        } else {
             // Если данных нет, очищаем или пишем пусто
             const historyList = document.getElementById('food-list');
             if(historyList) historyList.innerHTML = '<p style="text-align:center; color:#888; margin-top:20px;">Пока пусто</p>';
        }
    }

    function setBar(id, current, max) {
        const bar = document.getElementById(id);
        if (bar) {
            const percent = max > 0 ? Math.min((current / max) * 100, 100) : 0;
            bar.style.width = `${percent}%`;

            if (current > max) {
                bar.style.setProperty('background', '#ff4b4b', 'important');
            } else {
                bar.style.removeProperty('background');
            }
        }
    }

    // === НОВАЯ ФУНКЦИЯ ОТРИСОВКИ КАРТОЧЕК ===
    function renderFoodHistory(foodLog) {
        // ВАЖНО: Ищем 'food-list', который мы добавили в HTML в Шаге 2
        const historyList = document.getElementById('food-list'); 
        if (!historyList) return;
        
        historyList.innerHTML = ''; // Очищаем

        if (foodLog.length === 0) {
             historyList.innerHTML = '<p style="text-align:center; color:#888; margin-top:20px;">Сегодня записей нет</p>';
             return;
        }

        foodLog.forEach(item => {
            const card = document.createElement('div');
            card.className = 'food-card'; // Используем новый класс стилей

            // ВАЖНО: Используем item.cal, item.p, item.f, item.c (как в Python)
            card.innerHTML = `
                <button class="btn-delete" onclick="deleteFood(${item.id})">
                    <i class="fa-solid fa-trash"></i>
                </button>

                <div class="food-header">
                    <div class="food-name">${item.name}</div>
                </div>

                <div class="food-calories">${item.cal} ккал</div>

                <div class="food-macros">
                    <div class="macro-item macro-prot">🥩 <span>${item.p}</span></div>
                    <div class="macro-item macro-fat">🥑 <span>${item.f}</span></div>
                    <div class="macro-item macro-carb">🥖 <span>${item.c}</span></div>
                </div>
            `;
            historyList.appendChild(card);
        });
    }

    updateUI();

    // ==========================================
    // 4. TELEGRAM И НАВИГАЦИЯ
    // ==========================================
    if (window.Telegram && window.Telegram.WebApp) {
        const tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();

        const user = tg.initDataUnsafe?.user;
        if (user && user.photo_url) {
            const avatarImg = document.querySelector('.avatar img');
            if (avatarImg) avatarImg.src = user.photo_url;
        }
    }

    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(nav => nav.classList.remove('active'));
            document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));
            
            item.classList.add('active');
            const targetId = item.getAttribute('href').substring(1);
            const targetSection = document.getElementById(targetId);
            if (targetSection) {
                targetSection.classList.add('active');
                if (targetId === 'stats') {
                    initStatsChart();
                }
            }
        });
    });

    // ==========================================
    // 5. ИНИЦИАЛИЗАЦИЯ ГРАФИКА СТАТИСТИКИ
    // ==========================================
    let statsChart = null;
    function initStatsChart() {
        const ctx = document.getElementById('caloriesChart');
        const historyStr = urlParams.get('history') || '0,0,0,0,0,0,0';
        const historyData = historyStr.split(',').map(Number);

        const todayIndex = (new Date().getDay() + 6) % 7;
        // Тут берем актуальные данные из currentData
        historyData[todayIndex] = parseInt(currentData.c_cal) || 0;

        const labels = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];

        if (ctx && !statsChart) { 
            statsChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Калории',
                        data: historyData,
                        borderColor: '#4CAF50', // Зеленый цвет как в дизайне
                        backgroundColor: 'rgba(76, 175, 80, 0.2)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#4CAF50',
                        pointBorderColor: '#fff',
                        pointHoverRadius: 7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: '#f0f0f0' }
                        },
                        x: {
                            grid: { display: false }
                        }
                    },
                    plugins: {
                        legend: { display: false }
                    }
                }
            });
        }
    }

    if (document.getElementById('stats').classList.contains('active')) {
        initStatsChart();
    }
});

// ==========================================
// 6. ФУНКЦИЯ УДАЛЕНИЯ (ГЛОБАЛЬНАЯ)
// ==========================================
// Мы вынесли её из DOMContentLoaded, чтобы HTML видел её
window.deleteFood = function(id) {
    if (confirm('Удалить эту запись?')) {
        const data = JSON.stringify({
            action: 'delete_food',
            id: id
        });
        if (window.Telegram && window.Telegram.WebApp) {
             window.Telegram.WebApp.sendData(data);
        } else {
             console.log("Telegram WebApp not found, data to send:", data);
        }
    }
};