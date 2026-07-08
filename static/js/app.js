/* ============================================================
 * RDM 工时填报系统 · 公共脚本（v2 真实接入版）
 *
 * 本文件提供：
 *  - 日期 / ISO 周工具
 *  - apiCall：直接走 fetch()，未登录自动跳 '/'
 *  - toast 弹窗
 *  - clampHour / clampRate / escapeHtml / formatHour
 *
 * 与原型差异：
 *  - 删除 mockFetch（不再拦截 /api/*）
 *  - 不再用 sessionStorage 存登录态（服务端 flask.session 管理）
 *  - currentUser() 从 #navUsername 读取（由模板渲染）
 * ============================================================ */

const STORAGE_KEYS = {
    REMEMBER_USERNAME: 'gongshi_remember_username',
    REMEMBER_PASSWORD: 'gongshi_remember_password',
    REMEMBER_FLAG: 'gongshi_remember_flag'
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
 * apiCall：真实 fetch 包装
 *   - 网络异常 → {success:false, message:'网络异常，请稍后重试'}
 *   - 收到 {success:false, message:'未登录'} → 跳 '/' 并返回该对象
 * ============================================================ */

async function apiCall(url, opts = {}) {
    const fetchOpts = {
        method: opts.method || 'GET',
        credentials: 'same-origin',
        headers: Object.assign(
            { 'Content-Type': 'application/json' },
            opts.headers || {}
        )
    };
    if (opts.body !== undefined) {
        fetchOpts.body = opts.body;
    }

    let data;
    try {
        const resp = await fetch(url, fetchOpts);
        // 即便是 401/500，后端也大都返回 JSON；解析失败再降级
        try {
            data = await resp.json();
        } catch (e) {
            data = { success: false, message: '网络异常，请稍后重试' };
        }
    } catch (e) {
        return { success: false, message: '网络异常，请稍后重试' };
    }

    if (data && data.success === false) {
        // A4 / F2：未登录自动跳，不弹框
        // Phase 1b：RDM 会话过期也跳回登录页重新建立会话
        if (data.message === '未登录' ||
            (data.message && data.message.includes('会话已过期'))) {
            window.location.href = '/';
            return data;
        }
        // License 激活拦截：未激活用户跳转到激活页面
        if (data.need_activate) {
            window.location.href = '/activate';
            return data;
        }
    }
    return data;
}

/* ============================================================
 * 登录态：基于服务端 session
 *   currentUser() 从模板渲染的 #navUsername 取
 *   登录拦截统一靠 apiCall 中 message==='未登录' 的跳转
 * ============================================================ */

function currentUser() {
    const el = document.getElementById('navUsername');
    return el ? (el.textContent || '').trim() : '';
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

function toast(message, type = 'info', duration = 4000) {
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
    // INSPUR-23：工时仅接受整数
    n = Math.round(n);
    return n;
}

function clampRate(v) {
    if (v === '' || v == null) return null;
    let n = parseInt(v, 10);
    if (isNaN(n) || n < 0) n = 0;
    if (n > 100) n = 100;
    return n;
}

function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

function formatHour(n) {
    if (!n) return '0';
    // INSPUR-23：工时仅接受整数
    return Math.round(n).toString();
}

/** 格式化缓存时间 ISO 字符串为友好文本 */
function formatCachedTime(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        if (isNaN(d.getTime())) return isoStr;
        const now = new Date();
        const diffMin = Math.floor((now - d) / 60000);
        if (diffMin < 1) return '刚刚';
        if (diffMin < 60) return diffMin + ' 分钟前';
        const diffH = Math.floor(diffMin / 60);
        if (diffH < 24) return diffH + ' 小时前';
        return pad2(d.getMonth() + 1) + '/' + pad2(d.getDate()) + ' ' +
               pad2(d.getHours()) + ':' + pad2(d.getMinutes());
    } catch (e) {
        return isoStr;
    }
}
