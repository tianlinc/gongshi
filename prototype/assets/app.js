/* ============================================================
 * RDM 工时填报系统 · 原型公共脚本
 *
 * 本文件提供：
 *  - 日期/ISO 周工具
 *  - mock fetch（拦截所有 /api/* 调用，从 mock/ JSON 取数据）
 *  - 登录态 sessionStorage 模拟
 *  - 未登录拦截 → 跳登录页
 *  - toast 弹窗
 *
 * 真实接入时替换 mockFetch 为 fetch 即可，其他工具函数可直接复用。
 * ============================================================ */

const STORAGE_KEYS = {
    REMEMBER_USERNAME: 'gongshi_remember_username',
    REMEMBER_PASSWORD: 'gongshi_remember_password',
    REMEMBER_FLAG: 'gongshi_remember_flag',
    SESSION_USER: 'gongshi_session_user'
};

/* ============================================================
 * 日期工具：ISO 周（周一为起点）
 * ============================================================ */

function pad2(n) { return String(n).padStart(2, '0'); }

function fmtDate(d) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function fmtMD(d) {
    return `${d.getMonth() + 1}/${d.getDate()}`;
}

/** 把任意日期对齐到该周周一 0 点 */
function getWeekMonday(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    const day = d.getDay();          // 0=周日, 1=周一, ..., 6=周六
    const diff = day === 0 ? -6 : 1 - day;
    d.setDate(d.getDate() + diff);
    return d;
}

/** 返回该周 7 天数组（周一→周日），每天为 {date, weekday, isWeekend, isToday} */
function getWeekDays(monday) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
    const days = [];
    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        days.push({
            date: new Date(d),
            dateStr: fmtDate(d),
            weekday: labels[i],
            mdLabel: fmtMD(d),
            isWeekend: i >= 5,
            isToday: d.getTime() === today.getTime()
        });
    }
    return days;
}

/** ISO 周号 */
function getISOWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

/* ============================================================
 * mock fetch
 * ============================================================ */

async function mockFetch(url, opts = {}) {
    await new Promise(r => setTimeout(r, 280)); // 模拟网络延迟

    // 未登录拦截：除登录端点之外，未登录返回未登录响应
    const isLogin = url.startsWith('/api/login');
    const isLogout = url.startsWith('/api/logout');
    if (!isLogin && !isLogout && !isLoggedIn()) {
        return { success: false, message: '未登录' };
    }

    if (url.startsWith('/api/login')) {
        const body = JSON.parse(opts.body || '{}');
        if (!body.username || !body.password) {
            return { success: false, message: '用户名或密码不能为空' };
        }
        // 演示一种失败：用户名 'fail'
        if (body.username === 'fail') {
            return { success: false, message: '用户名或密码错误' };
        }
        sessionStorage.setItem(STORAGE_KEYS.SESSION_USER, body.username);
        return { success: true, username: body.username };
    }

    if (url.startsWith('/api/logout')) {
        sessionStorage.removeItem(STORAGE_KEYS.SESSION_USER);
        return { success: true };
    }

    if (url.startsWith('/api/tasks')) {
        const res = await fetch('mock/tasks.json');
        const data = await res.json();
        // B4：状态过滤
        data.tasks = data.tasks.filter(t => ['未启动', '进行中'].includes(t.status));
        // U3：负责优先 → 参与优先 → both最后
        const order = { responsible: 0, participate: 1, both: 2 };
        data.tasks.sort((a, b) => (order[a.source] ?? 9) - (order[b.source] ?? 9));
        return data;
    }

    if (url.startsWith('/api/timesheet')) {
        const m = url.match(/week_start=([0-9-]+)/);
        const weekStart = m ? m[1] : '';
        const res = await fetch('mock/timesheet.json');
        const all = await res.json();
        if (all[weekStart]) return all[weekStart];
        return { success: true, week_start: weekStart, tasks: [] };
    }

    if (url.startsWith('/api/submit-day')) {
        const body = JSON.parse(opts.body || '{}');
        const taskId = body?.task_id || '';
        // 演示失败：T-FAIL-DEMO 永远失败
        if (taskId === 'T-FAIL-DEMO') {
            return { success: false, message: '网络异常（mock 故意失败演示）' };
        }
        return { success: true, message: '提交成功', task_id: taskId, day_index: body.day_index };
    }

    return { success: false, message: '未知接口' };
}

/* ============================================================
 * 登录态（sessionStorage 模拟 Flask session）
 * ============================================================ */

function isLoggedIn() {
    return !!sessionStorage.getItem(STORAGE_KEYS.SESSION_USER);
}

function currentUser() {
    return sessionStorage.getItem(STORAGE_KEYS.SESSION_USER) || '';
}

/** 任何 /api/* 调用前用这个包一层，自动跳登录 */
async function apiCall(url, opts) {
    const data = await mockFetch(url, opts);
    if (data && data.success === false && data.message === '未登录') {
        // A4 / F2：未登录自动跳，不弹框
        window.location.href = 'index.html';
        return data;
    }
    return data;
}

/* ============================================================
 * toast
 * ============================================================ */

function ensureToastStack() {
    let el = document.querySelector('.toast-stack');
    if (!el) {
        el = document.createElement('div');
        el.className = 'toast-stack';
        document.body.appendChild(el);
    }
    return el;
}

const TOAST_ICONS = {
    success: 'bi-check-circle-fill',
    error: 'bi-x-circle-fill',
    warn: 'bi-exclamation-triangle-fill',
    info: 'bi-info-circle-fill'
};

function toast(message, type = 'info', duration = 2600) {
    const stack = ensureToastStack();
    const el = document.createElement('div');
    el.className = `toast-item ${type}`;
    el.innerHTML = `
        <i class="bi ${TOAST_ICONS[type] || TOAST_ICONS.info} toast-icon"></i>
        <div>${message}</div>
    `;
    stack.appendChild(el);
    setTimeout(() => {
        el.style.transition = 'opacity 0.3s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 300);
    }, duration);
}

/* ============================================================
 * 校验工具
 * ============================================================ */

function clampHour(v) {
    let n = parseFloat(v);
    if (isNaN(n) || n < 0) n = 0;
    if (n > 24) n = 24;
    // 步进 0.5
    n = Math.round(n * 2) / 2;
    return n;
}

function clampRate(v) {
    if (v === '' || v == null) return null;
    let n = parseInt(v, 10);
    if (isNaN(n) || n < 0) n = 0;
    if (n > 100) n = 100;
    return n;
}
