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
        const remainEl = document.querySelector('.stat-side .stat-val'); // More specific selector
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

        const protMax = Math.round((goal * 0.3) / 4);
        const fatMax = Math.round((goal * 0.3) / 9);
        const carbMax = Math.round((goal * 0.4) / 4);

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

        // Render food history from URL
        const foodLogParam = urlParams.get('food_log');
        if (foodLogParam) {
            try {
                const foodLog = JSON.parse(decodeURIComponent(foodLogParam));
                renderFoodHistory(foodLog);
            } catch (e) {
                console.error("Error parsing food log:", e);
            }
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
                // Remove the !important rule to revert to CSS-defined color
                bar.style.removeProperty('background');
            }
        }
    }

    function renderFoodHistory(foodLog) {
        const historyList = document.getElementById('food-history-list');
        historyList.innerHTML = ''; // Clear previous entries

        foodLog.forEach(item => {
            const historyItem = document.createElement('div');
            historyItem.className = 'history-item';

            historyItem.innerHTML = `
                <div class="history-item-header">
                    <span>${item.name}</span>
                    <span>${item.calories} ккал</span>
                </div>
                <div class="history-item-macros">
                    <span>Б: ${item.protein}г</span>
                    <span>Ж: ${item.fat}г</span>
                    <span>У: ${item.carbs}г</span>
                </div>
            `;
            historyList.appendChild(historyItem);
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

        // Get today's index (0=Mon, 6=Sun)
        const todayIndex = (new Date().getDay() + 6) % 7;
        historyData[todayIndex] = parseInt(currentData.c_cal) || 0;

        const labels = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];

        if (ctx && !statsChart) { // Check if chart instance exists
            statsChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Калории',
                        data: historyData,
                        borderColor: 'var(--primary)',
                        backgroundColor: 'rgba(128, 203, 196, 0.2)',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: 'var(--primary)',
                        pointBorderColor: '#fff',
                        pointHoverRadius: 7,
                        pointHoverBorderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: '#f0f0f0' },
                            ticks: { color: 'var(--text-light)' }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: 'var(--text-light)' }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: '#333',
                            titleFont: { size: 14 },
                            bodyFont: { size: 12 },
                            padding: 10,
                            cornerRadius: 8
                        }
                    }
                }
            });
        }
    }

    // Initialize chart if stats tab is active on load
    if (document.getElementById('stats').classList.contains('active')) {
        initStatsChart();
    }
});