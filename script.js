// 1. ИНИЦИАЛИЗАЦИЯ ТЕЛЕГРАМА
let tg = null;
try {
    if (window.Telegram && window.Telegram.WebApp) {
        tg = window.Telegram.WebApp;
        tg.ready();
        tg.expand();
    }
} catch (e) { console.error(e); }

// 2. ФУНКЦИЯ УДАЛЕНИЯ
window.deleteFood = function(id) {
    if (!confirm('Удалить эту запись?')) return;

    if (!tg) {
        alert("Ошибка: Запустите через Телеграм!");
        return;
    }

    // Отправляем данные боту
    const data = JSON.stringify({ action: 'delete_food', id: id });
    tg.sendData(data);
};

// 3. ОСНОВНОЙ КОД
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    
    // Сбор данных
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

    // UI Функции
    function safeSetText(id, text) {
        const el = document.getElementById(id);
        if(el) el.innerText = text;
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

        // Круг
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
        const p_max = urlParams.get('p_max') || Math.round((goal * 0.3)/4);
        const f_max = urlParams.get('f_max') || Math.round((goal * 0.3)/9);
        const c_max = urlParams.get('c_max') || Math.round((goal * 0.4)/4);
        
        safeSetText('prot-val', currentData.c_prot || 0); safeSetText('prot-max', p_max);
        safeSetText('fat-val', currentData.c_fat || 0);  safeSetText('fat-max', f_max);
        safeSetText('carb-val', currentData.c_carb || 0); safeSetText('carb-max', c_max);
        
        setBar('prot-bar', currentData.c_prot, p_max);
        setBar('fat-bar', currentData.c_fat, f_max);
        setBar('carb-bar', currentData.c_carb, c_max);

        renderFoodList(urlParams.get('food_log'));
    }

    function setBar(id, cur, max) {
        const bar = document.getElementById(id);
        if(bar) {
            const pct = max > 0 ? Math.min((cur/max)*100, 100) : 0;
            bar.style.width = `${pct}%`;
            if(cur > max) bar.style.setProperty('background', '#ff4b4b', 'important');
            else bar.style.removeProperty('background');
        }
    }

    function renderFoodList(raw) {
        const con = document.getElementById('food-list');
        if(!con) return;
        if(!raw) { con.innerHTML = '<p style="text-align:center;color:#888;margin-top:20px">Пусто</p>'; return; }
        
        try {
            const list = JSON.parse(decodeURIComponent(raw));
            if(list.length===0) { con.innerHTML='<p style="text-align:center;color:#888;margin-top:20px">Нет записей</p>'; return; }
            
            con.innerHTML = '';
            list.forEach(item => {
                const card = document.createElement('div');
                card.className = 'food-card';
                card.innerHTML = `
                    <button class="btn-delete" onclick="deleteFood(${item.id})"><i class="fa-solid fa-trash"></i></button>
                    <div class="food-header"><div class="food-name">${item.name}</div></div>
                    <div class="food-calories">${item.cal} ккал</div>
                    <div class="food-macros">
                        <div class="macro-item macro-prot">🥩 <span>${item.p}</span></div>
                        <div class="macro-item macro-fat">🥑 <span>${item.f}</span></div>
                        <div class="macro-item macro-carb">🥖 <span>${item.c}</span></div>
                    </div>`;
                con.appendChild(card);
            });
        } catch(e) { console.error(e); }
    }

    updateUI();

    // График
    const ctx = document.getElementById('caloriesChart');
    if(ctx && document.getElementById('stats')) {
        const hist = (urlParams.get('history')||'0,0,0,0,0,0,0').split(',').map(Number);
        hist[(new Date().getDay()+6)%7] = parseInt(currentData.c_cal)||0;
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'],
                datasets: [{
                    data: hist,
                    borderColor: '#4CAF50',
                    backgroundColor: 'rgba(76, 175, 80, 0.2)',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: { plugins:{legend:{display:false}}, scales:{x:{grid:{display:false}}, y:{beginAtZero:true}} }
        });
    }

    // Навигация
    document.querySelectorAll('.nav-item').forEach(i => i.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-item, .content-section').forEach(x => x.classList.remove('active'));
        i.classList.add('active');
        document.getElementById(i.getAttribute('href').substring(1)).classList.add('active');
    }));
});