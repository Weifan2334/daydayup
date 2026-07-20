/* daydayup v0.3 客户端 */
(function () {
  'use strict';

  // ===================== 状态 =====================
  const TOKEN_KEY = 'daydayup_token';
  const USER_KEY = 'daydayup_user';

  const state = {
    token: localStorage.getItem(TOKEN_KEY) || null,
    user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
    todayDate: '',
    view: null,
    currentView: 'today',
    calendarMonth: '',
    calendarView: null,
    selectedDate: '',
    authMode: 'login', // login | register
    cloudBackups: [],
    reviewRange: 'day',
    aiBlocks: null, // DeepSeek 临时生成的作息轴
    actualRecords: [], // 自由真实记录
  };

  const $ = (id) => document.getElementById(id);
  const pad = (n) => String(n).padStart(2, '0');
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function todayStr() {
    const d = new Date();
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  function monthStr(dateStr) { return dateStr.slice(0, 7); }
  function shiftMonth(monthStrVal, delta) {
    const [y, m] = monthStrVal.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
  }

  // ===================== HTTP 客户端 =====================
  async function api(url, opts = {}) {
    opts = { method: opts.method || 'GET', ...opts };
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    const res = await fetch(url, { ...opts, headers });
    if (res.status === 401) {
      // token 失效
      logout({ silent: true });
      return Promise.reject(new Error('登录已过期，请重新登录'));
    }
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j.detail) {
          msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
        } else if (j.message) {
          msg = typeof j.message === 'string' ? j.message : JSON.stringify(j.message);
        }
      } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  // ===================== 通用 UI：确认弹窗 / Toast / 焦点陷阱 =====================
  let _confirmLastFocus = null;
  let _goalLastFocus = null;
  const prefersReducedMotion = () => !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  // 通用确认弹窗（替代原生 confirm）。返回 Promise<boolean>
  function confirmDialog({ title = '确认', message = '', confirmText = '确定', danger = false } = {}) {
    return new Promise((resolve) => {
      _confirmResolver = resolve;
      _confirmLastFocus = document.activeElement;
      if (window.AudioManager) window.AudioManager.play('panel_open');
      const dlg = $('confirm-dialog');
      $('confirm-title').textContent = title;
      $('confirm-message').textContent = message;
      $('confirm-ok').textContent = confirmText;
      dlg.classList.toggle('is-danger', !!danger);
      dlg.hidden = false;
      setTimeout(() => { try { $('confirm-ok').focus(); } catch (_) {} }, 0);
    });
  }
  let _confirmResolver = null;
  function closeConfirmDialog(result) {
    const dlg = $('confirm-dialog');
    dlg.hidden = true;
    if (_confirmResolver) { const r = _confirmResolver; _confirmResolver = null; r(result); }
    if (_confirmLastFocus && _confirmLastFocus.focus) _confirmLastFocus.focus();
  }
  $('confirm-ok').addEventListener('click', () => closeConfirmDialog(true));
  $('confirm-cancel').addEventListener('click', () => closeConfirmDialog(false));
  $('confirm-dialog').addEventListener('click', (e) => { if (e.target === $('confirm-dialog')) closeConfirmDialog(false); });
  document.addEventListener('keydown', (e) => {
    const dlg = $('confirm-dialog');
    if (dlg.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closeConfirmDialog(false); }
    else if (e.key === 'Tab') { e.preventDefault(); trapTab(dlg); }
  });

  // 在容器内循环 Tab 焦点（模态焦点陷阱）
  function trapTab(container) {
    const f = container.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (document.activeElement === first) last.focus();
    else if (document.activeElement === last) first.focus();
    else first.focus();
  }

  // 轻提示
  function showToast(msg, kind) {
    const host = $('toast-host');
    if (!host) return;
    const t = document.createElement('div');
    t.className = 'toast' + (kind ? ' ' + kind : '');
    t.textContent = msg;
    host.appendChild(t);
    setTimeout(() => {
      t.style.opacity = '0';
      t.style.transition = 'opacity .3s';
      setTimeout(() => t.remove(), 320);
    }, 2800);
  }

  // ===================== 鉴权门 =====================
  function showAuthGate() {
    $('auth-gate').style.display = 'flex';
    $('app').hidden = true;
  }
  function showApp() {
    $('auth-gate').style.display = 'none';
    $('app').hidden = false;
  }

  function persistAuth(token, user) {
    state.token = token;
    state.user = user;
    if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user)); else localStorage.removeItem(USER_KEY);
  }

  function logout(opts) {
    if (state.token && !opts?.silent) {
      api('/api/auth/logout', { method: 'POST' }).catch(() => {});
    }
    persistAuth(null, null);
    showAuthGate();
  }

  $('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const username = form.username.value.trim();
    const password = form.password.value;
    const display_name = form.display_name.value.trim() || null;
    const isRegister = state.authMode === 'register';
    setAuthMsg('');
    $('auth-submit-btn').disabled = true;
    try {
      const url = isRegister ? '/api/auth/register' : '/api/auth/login';
      const body = isRegister ? { username, password, display_name } : { username, password };
      const r = await api(url, { method: 'POST', body });
      persistAuth(r.token, r.user);
      showApp();
      bootstrap();
    } catch (err) {
      setAuthMsg(err.message, 'err');
    } finally {
      $('auth-submit-btn').disabled = false;
    }
  });

  function setAuthMsg(text, kind) {
    const el = $('auth-msg');
    el.textContent = text || '';
    el.className = 'auth-msg' + (kind ? ' ' + kind : '');
  }

  document.querySelectorAll('.auth-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      state.authMode = mode;
      document.querySelectorAll('.auth-tab').forEach((b) => b.classList.toggle('is-active', b === btn));
      $('auth-display-row').hidden = (mode !== 'register');
      $('auth-submit-btn').textContent = mode === 'register' ? '注册并登录' : '登录';
      setAuthMsg('');
    });
  });

  // ===================== 登录页武侠励志语录 =====================
  // 经典武侠 / 励志名句，加载随机呈现，定时淡入轮换（减弱动效时静态）
  const WUXIA_QUOTES = [
    { t: '侠之大者，为国为民。', s: '金庸' },
    { t: '他强任他强，清风拂山冈；他横任他横，明月照大江。', s: '金庸《倚天屠龙记》' },
    { t: '宝剑锋从磨砺出，梅花香自苦寒来。', s: '《警世贤文》' },
    { t: '千磨万击还坚劲，任尔东西南北风。', s: '郑燮《竹石》' },
    { t: '莫等闲，白了少年头，空悲切。', s: '岳飞《满江红》' },
    { t: '长风破浪会有时，直挂云帆济沧海。', s: '李白' },
    { t: '十年磨一剑，霜刃未曾试。', s: '贾岛《剑客》' },
    { t: '天下风云出我辈，一入江湖岁月催。', s: '黄霑' },
    { t: '路漫漫其修远兮，吾将上下而求索。', s: '屈原' },
    { t: '情深不寿，强极则辱；谦谦君子，温润如玉。', s: '金庸《书剑恩仇录》' },
    { t: '古之立大事者，不惟有超世之才，亦必有坚忍不拔之志。', s: '苏轼' },
    { t: '博观而约取，厚积而薄发。', s: '苏轼' },
    { t: '志之所趋，无远弗届；穷山距海，不能限也。', s: '《格言联璧》' },
    { t: '心有猛虎，细嗅蔷薇。', s: '萨松（译）' },
  ];
  function initAuthQuotes() {
    const box = $('auth-quote'); if (!box) return;
    const txt = $('auth-quote-text'); const cite = $('auth-quote-cite');
    let idx = Math.floor(Math.random() * WUXIA_QUOTES.length);
    const show = (i) => { const q = WUXIA_QUOTES[i]; txt.textContent = '“' + q.t + '”'; cite.textContent = '—— ' + q.s; };
    show(idx);
    if (!prefersReducedMotion()) {
      setInterval(() => {
        box.classList.add('is-fading');
        setTimeout(() => {
          idx = (idx + 1) % WUXIA_QUOTES.length;
          show(idx);
          box.classList.remove('is-fading');
        }, 420);
      }, 7000);
    }
  }
  initAuthQuotes();

  // ===================== 今日视图 =====================
  function renderTopBar(view) {
    $('today-date').textContent = `${view.today_date} ${view.weekday}`;
    $('now-time').textContent = view.current_time;
  }
  function renderCurrentBlock(view) {
    const cur = view.current_block;
    const next = view.next_block;
    if (cur) {
      $('cb-start').textContent = cur.anchor_time;
      $('cb-end').textContent = cur.end_time;
      $('cb-title').textContent = cur.label;
      $('cb-note').textContent = cur.note || '（无备注）';
    } else if (next) {
      $('cb-start').textContent = next.anchor_time;
      $('cb-end').textContent = next.end_time;
      $('cb-title').textContent = next.label;
      $('cb-note').textContent = '今天第一段即将开始';
    } else {
      $('cb-title').textContent = '今天没有排程';
    }
    if (next) {
      $('cb-next-label-text').textContent = next.label;
      $('cb-next-when').textContent = '· ' + countdown(next.anchor_time);
    } else {
      $('cb-next-label-text').textContent = '—';
      $('cb-next-when').textContent = '';
    }
  }
  function countdown(targetHHMM) {
    const now = new Date();
    const [h, m] = targetHHMM.split(':').map(Number);
    const target = new Date(now); target.setHours(h, m, 0, 0);
    if (target < now) target.setDate(target.getDate() + 1);
    const diffMin = Math.floor((target - now) / 60000);
    if (diffMin < 1) return '现在';
    if (diffMin < 60) return `${diffMin} 分钟后`;
    return `${Math.floor(diffMin / 60)} 小时 ${diffMin % 60} 分后`;
  }
  function renderTimeline(view) {
    // 「作息时间轴」：展示推荐节奏（可被 AI 定制临时覆盖）
    const ol = $('timeline'); ol.innerHTML = '';
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    const blocks = state.aiBlocks || view.blocks || [];
    blocks.forEach((b) => {
      const startMin = hmToMin(b.anchor_time), endMin = hmToMin(b.end_time);
      const li = document.createElement('li');
      li.className = 'tl-item';
      if (startMin <= nowMin && nowMin < endMin) li.classList.add('is-current');
      else if (nowMin < startMin) li.classList.add('is-future');
      else li.classList.add('is-past');
      const dur = endMin - startMin;
      const durLabel = dur >= 60 ? `${(dur / 60).toFixed(1)}h` : `${dur}m`;
      li.innerHTML = `
        <div class="tl-time"><span class="tl-start">${b.anchor_time}</span><span class="tl-dash">→</span><span class="tl-end">${b.end_time}</span></div>
        <div class="tl-marker"></div>
        <div class="tl-body">
          <div class="tl-plan">
            <div class="tl-row"><div class="tl-title">${escapeHtml(b.label)}</div><span class="tl-dur">${durLabel}</span></div>
            ${b.note ? `<div class="tl-note">${escapeHtml(b.note)}</div>` : ''}
          </div>
        </div>`;
      ol.appendChild(li);
    });
    $('blocks-count').textContent = blocks.length;
  }
  function renderActuals(view) {
    // 已废弃：旧版列表式真实记录，保留函数占位避免其他调用点报错
  }

  // ===================== 真实记录时间轴（自由拖拽） =====================
  const HOUR_HEIGHT = 48; // 与 CSS 一致
  const DAY_MIN = 24 * 60;

  function minToY(min) { return (min / 60) * HOUR_HEIGHT; }
  function yToMin(y) { return Math.round((y / HOUR_HEIGHT) * 60); }
  function snapMin(min) { return Math.max(0, Math.min(DAY_MIN - 15, Math.round(min / 15) * 15)); }
  function formatHM(min) {
    const h = Math.floor(min / 60) % 24;
    const m = min % 60;
    return `${pad(h)}:${pad(m)}`;
  }

  async function renderActualGrid(view) {
    const ruler = $('actual-grid-ruler');
    const lines = $('actual-grid-lines');
    const bars = $('actual-grid-bars');
    const now = $('actual-grid-now');
    const date = state.todayDate;
    if (!ruler || !lines || !bars || !now) return;

    // 构建标尺与网格线
    ruler.innerHTML = ''; lines.innerHTML = '';
    for (let h = 0; h < 24; h++) {
      const hour = pad(h) + ':00';
      const div = document.createElement('div');
      div.className = 'actual-grid-hour';
      div.dataset.hour = hour;
      div.style.top = (h * HOUR_HEIGHT) + 'px';
      div.style.position = 'absolute';
      div.style.width = '100%';
      ruler.appendChild(div.cloneNode(true));
      lines.appendChild(div);
    }

    // 拉取真实记录
    let records = [];
    try {
      records = await api('/api/actual_records?date=' + date);
    } catch (e) {
      console.error('fetch actual_records', e);
      records = state.actualRecords || [];
    }
    state.actualRecords = records || [];
    bars.innerHTML = '';
    (records || []).forEach((r) => {
      const startMin = hmToMin(r.start_time);
      const endMin = hmToMin(r.end_time);
      const el = document.createElement('div');
      el.className = 'actual-grid-bar';
      el.dataset.id = r.id;
      el.style.top = minToY(startMin) + 'px';
      el.style.height = Math.max(22, minToY(endMin - startMin)) + 'px';
      el.innerHTML = `
        <div class="bar-time">${r.start_time} – ${r.end_time}</div>
        <textarea class="bar-text" placeholder="做了什么…">${escapeHtml(r.text || '')}</textarea>
        <div class="bar-handle" title="拉伸调整时长"></div>
        <button class="bar-delete" title="删除">×</button>`;
      bars.appendChild(el);
      bindActualBar(el, r);
    });
    updateActualCount();
    positionNowLine();
  }

  function updateActualCount() {
    const records = state.actualRecords || [];
    const count = records.filter((r) => r.text && r.text.trim()).length;
    $('actual-count').textContent = `${count}/${records.length}`;
  }

  function positionNowLine() {
    const now = $('actual-grid-now');
    if (!now) return;
    const d = new Date();
    const min = d.getHours() * 60 + d.getMinutes() + d.getSeconds() / 60;
    now.style.top = minToY(min) + 'px';
  }

  // 当前时间线每秒刷新一次（仅在今日视图可见时）
  setInterval(() => {
    if (state.currentView === 'today' && $('actual-grid-now')) positionNowLine();
  }, 60000);

  function bindActualBar(el, record) {
    const handle = el.querySelector('.bar-handle');
    const textarea = el.querySelector('.bar-text');
    const delBtn = el.querySelector('.bar-delete');
    let dragMode = null; // 'move' | 'resize'
    let startY = 0;
    let startTop = 0;
    let startHeight = 0;
    let startMin = 0;
    let startEndMin = 0;

    const onPointerDown = (e) => {
      // 点击文字编辑区/删除按钮时不进入拖拽；closest 兼容某些浏览器下 e.target 为子节点的情况
      if (e.target.closest('.bar-text') || e.target === delBtn) { e.stopPropagation(); return; }
      if (e.target === handle) { dragMode = 'resize'; }
      else { dragMode = 'move'; e.preventDefault(); }
      startY = e.clientY;
      startTop = el.offsetTop;
      startHeight = el.offsetHeight;
      startMin = hmToMin(record.start_time);
      startEndMin = hmToMin(record.end_time);
      el.classList.add('dragging');
      el.setPointerCapture(e.pointerId);
      el.addEventListener('pointermove', onPointerMove);
      el.addEventListener('pointerup', onPointerUp);
      el.addEventListener('pointercancel', onPointerUp);
    };

    const onPointerMove = (e) => {
      const dy = e.clientY - startY;
      if (dragMode === 'move') {
        const newMin = snapMin(startMin + yToMin(dy));
        const dur = startEndMin - startMin;
        const newEndMin = Math.min(DAY_MIN, newMin + dur);
        if (newEndMin <= DAY_MIN) {
          el.style.top = minToY(newMin) + 'px';
        }
      } else if (dragMode === 'resize') {
        const newEndMin = snapMin(startEndMin + yToMin(dy));
        const minDur = 15;
        if (newEndMin - startMin >= minDur && newEndMin <= DAY_MIN) {
          el.style.height = Math.max(22, minToY(newEndMin - startMin)) + 'px';
        }
      }
    };

    const onPointerUp = async (e) => {
      el.classList.remove('dragging');
      el.releasePointerCapture(e.pointerId);
      el.removeEventListener('pointermove', onPointerMove);
      el.removeEventListener('pointerup', onPointerUp);
      el.removeEventListener('pointercancel', onPointerUp);
      const top = el.offsetTop;
      const height = el.offsetHeight;
      const newStartMin = snapMin(yToMin(top));
      const newEndMin = snapMin(yToMin(top + height));
      record.start_time = formatHM(newStartMin);
      record.end_time = formatHM(newEndMin);
      el.querySelector('.bar-time').textContent = `${record.start_time} – ${record.end_time}`;
      await saveActualRecord(record);
    };

    el.addEventListener('pointerdown', onPointerDown);

    // 文字编辑自动保存
    let textTimer = null;
    const saveText = async () => {
      if (textTimer) clearTimeout(textTimer);
      record.text = textarea.value;
      await saveActualRecord(record);
      updateActualCount();
    };
    textarea.addEventListener('input', () => {
      if (textTimer) clearTimeout(textTimer);
      textTimer = setTimeout(saveText, 1000);
    });
    textarea.addEventListener('blur', saveText);
    // 阻止编辑区的指针事件冒泡到父级 bar，避免 Electron/触控环境把点击当成拖拽
    const stopProp = (e) => e.stopPropagation();
    textarea.addEventListener('pointerdown', stopProp);
    textarea.addEventListener('mousedown', stopProp);
    textarea.addEventListener('touchstart', stopProp, { passive: true });

    delBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      if (!confirm('确定删除这条真实记录？')) return;
      try {
        await api('/api/actual_records?id=' + record.id, { method: 'DELETE' });
        el.remove();
        state.actualRecords = (state.actualRecords || []).filter((r) => r.id !== record.id);
        updateActualCount();
      } catch (err) {
        showToast('删除失败：' + err.message, 'error');
      }
    });
  }

  async function saveActualRecord(record) {
    try {
      const updated = await api('/api/actual_records', {
        method: 'POST',
        body: {
          id: record.id,
          date: state.todayDate,
          start_time: record.start_time,
          end_time: record.end_time,
          text: record.text || '',
        },
      });
      record.updated_at = updated.updated_at;
      showToast('已保存', 'success');
    } catch (err) {
      showToast('保存失败：' + err.message, 'error');
    }
  }

  function attachActualGridCreate() {
    const track = $('actual-grid-track');
    if (!track || track.dataset.bound) return;
    track.dataset.bound = '1';
    track.addEventListener('click', async (e) => {
      if (e.target.closest('.actual-grid-bar')) return;
      const rect = track.querySelector('.actual-grid-lines').getBoundingClientRect();
      const y = e.clientY - rect.top;
      const startMin = snapMin(yToMin(y));
      const endMin = Math.min(DAY_MIN, startMin + 60);
      const text = '';
      try {
        const created = await api('/api/actual_records', {
          method: 'POST',
          body: { date: state.todayDate, start_time: formatHM(startMin), end_time: formatHM(endMin), text },
        });
        state.actualRecords = state.actualRecords || [];
        state.actualRecords.push(created);
        renderActualGrid(state.view);
      } catch (err) {
        showToast('创建失败：' + err.message, 'error');
      }
    });
  }

  function autosize(el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }
  function hmToMin(hm) { const [h, m] = hm.split(':').map(Number); return h * 60 + m; }
  function renderTasks(view, containerId = 'task-list', countId = 'task-count') {
    const ul = $(containerId); ul.innerHTML = '';
    if (!view.tasks.length) { const li = document.createElement('li'); li.className = 'task-empty'; li.innerHTML = '<span>还没有任务，下方加一条？</span>'; ul.appendChild(li); }
    view.tasks.forEach((t) => {
      const li = document.createElement('li');
      if (t.done) li.classList.add('done');
      li.dataset.id = t.id;
      const timeChip = t.anchor_time ? `<span class="time-chip">${t.anchor_time}</span>` : '<span class="time-chip dim">·</span>';
      const cat = t.category || 'other';
      const catChip = `<span class="cat-chip" style="--cat:${catColor(cat)}">${catLabel(cat)}</span>`;
      const coins = coinsOf(t.duration_min);
      const dur = (t.duration_min ? `<small>· ${t.duration_min} 分钟</small>` : '') + (coins ? ` <small class="coin-mini">· ${coins.toFixed(1)} 金币</small>` : '');
      li.innerHTML = `<span class="checkbox" data-act="toggle">${t.done ? '✓' : ''}</span>${timeChip}${catChip}<span class="label">${escapeHtml(t.title)}${dur}</span><button class="delete" data-act="del" title="删除">×</button>`;
      ul.appendChild(li);
    });
    if (countId && view.summary) $(countId).textContent = `${view.summary.tasks_done}/${view.summary.tasks_total}`;
  }
  async function renderTodayView(view) {
    state.view = view; state.todayDate = view.today_date;
    renderTopBar(view); renderCurrentBlock(view); renderTimeline(view); renderTasks(view);
    renderCoinCard(view);
    await renderActualGrid(view);
  }

  // ===================== 真实记录时间轴（自由拖拽） =====================
  // 一天 24h = 24 金币；每个事件消耗的时间（分钟）→ 金币 = 分钟 / 60。
  // 状态栏展示「当天剩余金币」；回顾视图按类目聚合金币消耗。
  const CATEGORIES = {
    work:    { label: '工作', color: '#c49a4a' },
    study:   { label: '学习', color: '#5b8c7d' },
    health:  { label: '健康', color: '#7fa6c9' },
    life:    { label: '生活', color: '#b5754f' },
    social:  { label: '社交', color: '#a06bb5' },
    leisure: { label: '娱乐', color: '#cf9d57' },
    other:   { label: '其他', color: '#8a8276' },
  };
  const COIN_BUDGET_DAY = 24; // 1 金币 = 1 小时

  function catLabel(c) { return (CATEGORIES[c] || CATEGORIES.other).label; }
  function catColor(c) { return (CATEGORIES[c] || CATEGORIES.other).color; }
  function coinsOf(minutes) { return Math.round((Number(minutes) || 0) / 60 * 100) / 100; }

  // 基于今日视图计算金币消耗（含时间流逝与损失）
  // 时间流逝：当前时刻对应的小时数（含小数），即已自动扣除的金币
  // 事件消耗：各事项 duration_min 之和 / 60
  // 损失：时间流逝但未用于事项的部分 = max(0, 时间流逝 - 事件消耗)
  // 剩余：今天还能用的金币 = max(0, 24 - 时间流逝)
  function computeCoins(view) {
    const tasks = (view && view.tasks) || [];
    const byCat = {};
    let totalMin = 0;
    tasks.forEach((t) => {
      const m = Number(t.duration_min) || 0;
      totalMin += m;
      const c = t.category || 'other';
      byCat[c] = (byCat[c] || 0) + m;
    });
    const now = new Date();
    const timeElapsed = Math.round((now.getHours() + now.getMinutes() / 60 + now.getSeconds() / 3600) * 100) / 100;
    const eventUsed = coinsOf(totalMin);
    const lost = Math.round(Math.max(0, timeElapsed - eventUsed) * 100) / 100;
    const remaining = Math.round(Math.max(0, COIN_BUDGET_DAY - timeElapsed) * 100) / 100;
    return { totalMin, timeElapsed, eventUsed, lost, remaining, byCat };
  }

  function renderCoinCard(view) {
    const c = computeCoins(view);
    const remainEl = $('coin-remaining');
    const usedEl = $('coin-used');
    const fillEl = $('coin-fill');
    const catsEl = $('coin-cats');
    const pillEl = $('coin-pill');
    if (remainEl) remainEl.textContent = c.remaining.toFixed(1);
    if (usedEl) usedEl.textContent = c.eventUsed.toFixed(1);
    if (fillEl) {
      // 进度条按时间流逝填充
      const pct = Math.min(100, Math.round(c.timeElapsed / COIN_BUDGET_DAY * 100));
      fillEl.style.width = pct + '%';
      fillEl.classList.toggle('is-over', c.timeElapsed >= COIN_BUDGET_DAY);
    }
    if (catsEl) {
      const entries = Object.keys(c.byCat).sort((a, b) => c.byCat[b] - c.byCat[a]);
      const parts = [];
      if (c.lost > 0) {
        parts.push(`<span class="coin-cat coin-cat-lost"><span class="coin-cat-dot" style="background:#9e3b2e"></span>损失 <strong>${c.lost.toFixed(1)}</strong><small>未记录</small></span>`);
      }
      if (!entries.length && c.lost <= 0) {
        parts.push('<span class="coin-cat-empty">今天还没有记录消耗时间的事项</span>');
      } else {
        entries.forEach((cat) => {
          const m = c.byCat[cat];
          const coins = coinsOf(m);
          parts.push(`<span class="coin-cat"><span class="coin-cat-dot" style="background:${catColor(cat)}"></span>${catLabel(cat)} <strong>${coins.toFixed(1)}</strong><small>${m}分钟</small></span>`);
        });
      }
      catsEl.innerHTML = parts.join('');
    }
    if (pillEl) {
      pillEl.textContent = `剩余金币 ${c.remaining.toFixed(1)}`;
      pillEl.classList.toggle('is-over', c.timeElapsed >= COIN_BUDGET_DAY);
    }
    // 光阴金币库房：将 24 枚金币渲染为方孔铜钱（明亮=剩余，暗淡=已流逝）
    // 首次构建一次性生成 24 枚，之后仅切换 class，避免每分钟重绘时反复触发入场动画
    const vaultEl = $('coin-vault');
    if (vaultEl) {
      if (!vaultEl._built) {
        let html = '';
        for (let i = 0; i < 24; i++) {
          html += `<span class="coin is-remain" data-i="${i}" title="" style="animation-delay:${i * 18}ms"></span>`;
        }
        vaultEl.innerHTML = html;
        vaultEl._built = true;
      }
      const usedCount = Math.min(24, Math.max(0, Math.round(c.timeElapsed)));
      const coins = vaultEl.children;
      for (let i = 0; i < 24; i++) {
        const el = coins[i];
        const used = i < usedCount;
        el.classList.toggle('is-used', used);
        el.classList.toggle('is-remain', !used);
        el.title = used ? `已流逝 ${i + 1} 枚` : `剩余 ${24 - i} 枚`;
      }
    }
  }

  async function renderReview(range) {
    try {
      const data = await api('/api/review?range=' + range);
      const titles = { day: '今日回顾', week: '本周回顾', month: '本月回顾' };
      if ($('review-range-title')) $('review-range-title').textContent = titles[range] || '回顾';
      if ($('review-range-badge')) $('review-range-badge').textContent = `${data.start} ~ ${data.end}`;
      if ($('review-remaining')) $('review-remaining').textContent = data.remaining.toFixed(1);
      if ($('review-used')) $('review-used').textContent = data.used.toFixed(1);
      if ($('review-budget')) $('review-budget').textContent = data.budget.toFixed(0);
      const fillEl = $('review-fill');
      if (fillEl) {
        // 进度条按时间流逝填充
        const te = data.time_elapsed || 0;
        const pct = Math.min(100, Math.round(data.budget ? te / data.budget * 100 : 0));
        fillEl.style.width = pct + '%';
        fillEl.classList.toggle('is-over', te >= data.budget);
      }
      // 按类目条（含「损失」特殊条目）
      const catsEl = $('review-cats');
      if (catsEl) {
        const catRows = data.by_category.map((c) => ({
          category: c.category, coins: c.coins, count: c.count, minutes: c.minutes, isLost: false,
        }));
        if (data.lost > 0) {
          catRows.push({ category: 'lost', coins: data.lost, count: 0, minutes: 0, isLost: true });
        }
        if (!catRows.length) {
          catsEl.innerHTML = '<span class="coin-cat-empty">这段时间内还没有记录消耗时间的事项</span>';
        } else {
          // 排序：损失放最后，其余按金币降序
          catRows.sort((a, b) => (a.isLost ? 1 : 0) - (b.isLost ? 1 : 0) || b.coins - a.coins);
          const maxCoins = Math.max(...catRows.map((c) => c.coins), 0.01);
          catsEl.innerHTML = catRows.map((c) => {
            const wpct = data.budget ? Math.round(c.coins / data.budget * 100) : 0;
            const barPct = Math.round(c.coins / maxCoins * 100);
            const dotColor = c.isLost ? '#9e3b2e' : catColor(c.category);
            const label = c.isLost ? '损失' : catLabel(c.category);
            const meta = c.isLost ? '时间流逝未记录' : `${c.count} 项 · ${c.minutes} 分钟`;
            return `<div class="review-cat${c.isLost ? ' is-lost' : ''}">
              <div class="review-cat-head">
                <span class="review-cat-dot" style="background:${dotColor}"></span>
                <span class="review-cat-label">${label}</span>
                <strong>${c.coins.toFixed(1)} 金币</strong>
                <small>${meta}</small>
              </div>
              <div class="review-cat-track"><div class="review-cat-fill" style="width:${barPct}%;background:${dotColor}"></div></div>
              <span class="review-cat-pct">占预算 ${wpct}%</span>
            </div>`;
          }).join('');
        }
      }
      // 事项明细
      const ul = $('review-tasks');
      if (ul) {
        if (!data.tasks.length) {
          ul.innerHTML = '<li class="task-empty"><span>暂无事项</span></li>';
        } else {
          ul.innerHTML = data.tasks.map((t) => {
            const cat = t.category || 'other';
            const catChip = `<span class="cat-chip" style="--cat:${catColor(cat)}">${catLabel(cat)}</span>`;
            const coins = coinsOf(t.duration_min);
            const dur = (t.duration_min ? `<small>· ${t.duration_min} 分钟</small>` : '') + (coins ? ` <small class="coin-mini">· ${coins.toFixed(1)} 金币</small>` : '');
            const timeChip = t.anchor_time ? `<span class="time-chip">${t.anchor_time}</span>` : '<span class="time-chip dim">·</span>';
            return `<li class="${t.done ? 'done' : ''}" data-id="${t.id}">
              <span class="checkbox" data-act="toggle">${t.done ? '✓' : ''}</span>
              ${timeChip}${catChip}
              <span class="label">${escapeHtml(t.title)}${dur}</span>
              <span class="review-date">${t.task_date.slice(5)}</span>
              <button class="delete" data-act="del" title="删除">×</button>
            </li>`;
          }).join('');
        }
      }
      if ($('review-task-count')) $('review-task-count').textContent = data.tasks.length;
    } catch (e) {
      console.error('renderReview', e);
    }
  }

  // ===================== 日历 =====================
  function renderCalendar(view) {
    state.calendarView = view; state.calendarMonth = view.month;
    $('cal-title').textContent = view.title;
    const grid = $('cal-grid'); grid.innerHTML = '';
    const today = todayStr();
    const cells = [];
    view.prev_month_tail.forEach((d) => cells.push({ ...d, isOther: true }));
    view.days.forEach((d) => cells.push({ ...d, isOther: false }));
    view.next_month_head.forEach((d) => cells.push({ ...d, isOther: true }));
    cells.forEach((d) => {
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'cal-day';
      if (d.isOther) cell.classList.add('is-other');
      if (d.weekday >= 6) cell.classList.add('is-weekend');
      if (d.date === today) cell.classList.add('is-today');
      if (state.selectedDate && d.date === state.selectedDate) cell.classList.add('is-selected');
      cell.dataset.date = d.date;
      const num = d.date.slice(8, 10);
      const dots = renderDots(d);
      const countHtml = (!d.isOther && d.total > 0) ? `<span class="cal-count">${d.total}</span>` : '';
      cell.innerHTML = `${countHtml}<span class="cal-num">${num}</span><span class="cal-dots">${dots}</span>`;
      grid.appendChild(cell);
    });
    const s = view.summary;
    $('cal-summary').textContent = `${s.days_with_tasks} 天有任务 · ${s.done_tasks}/${s.total_tasks} 已完成`;
  }
  function renderDots(day) {
    if (day.isOther) return '';
    const out = [];
    if (day.total - day.done > 0) out.push('<span class="cal-dot cal-dot-todo"></span>');
    if (day.done > 0) out.push('<span class="cal-dot cal-dot-done"></span>');
    return out.join('');
  }

  // ===================== Tab 切换 =====================
  async function switchView(name) {
    if (!['today', 'calendar', 'review', 'settings', 'year'].includes(name)) return;
    state.currentView = name;
    if (window.AudioManager) window.AudioManager.play('view_switch');
    document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('is-active', b.dataset.view === name));
    $('view-today').hidden = (name !== 'today');
    $('view-calendar').hidden = (name !== 'calendar');
    $('view-review').hidden = (name !== 'review');
    $('view-settings').hidden = (name !== 'settings');
    $('view-year').hidden = (name !== 'year');
    if (name === 'calendar') {
      if (!state.calendarMonth) state.calendarMonth = monthStr(todayStr());
      if (!state.calendarView || state.calendarView.month !== state.calendarMonth) {
        await fetchCalendar(state.calendarMonth);
      }
      if (!state.selectedDate) {
        state.selectedDate = todayStr();
      }
      await fetchTasksForSelected();
    } else if (name === 'settings') {
      loadAccount();
      initAudioUI();
      loadDataStats();
    } else if (name === 'year') {
      loadTargets();
    } else if (name === 'review') {
      await renderReview(state.reviewRange);
    }
  }

  // ===================== 数据获取 =====================
  async function fetchToday() {
    try { await renderTodayView(await api('/api/today')); setHealth(true); }
    catch (e) { console.error('fetchToday', e); setHealth(false); }
  }
  async function fetchCalendar(month) {
    try { renderCalendar(await api('/api/calendar?month=' + month)); }
    catch (e) { console.error('fetchCalendar', e); }
  }
  async function fetchTasksForSelected() {
    const date = state.selectedDate || todayStr();
    state.selectedDate = date;
    try {
      const [tasks, actuals, coins] = await Promise.all([
        api('/api/tasks_in_range?start=' + date + '&end=' + date),
        api('/api/actual_records?date=' + date).catch(() => []),
        api('/api/coins?date=' + date).catch(() => []),
      ]);
      const dt = new Date(date + 'T00:00:00');
      const wd = ['周日','周一','周二','周三','周四','周五','周六'][dt.getDay()];
      $('cal-day-title').textContent = `${date} ${wd}`;
      $('cal-day-card').hidden = false;

      const today = todayStr();
      const isFuture = date > today;

      // 顶部状态徽标
      const modeEl = $('cal-day-mode');
      if (isFuture) { modeEl.textContent = '未来计划'; modeEl.className = 'cal-day-mode future'; }
      else if (date === today) { modeEl.textContent = '今天'; modeEl.className = 'cal-day-mode today'; }
      else { modeEl.textContent = '过往'; modeEl.className = 'cal-day-mode past'; }

      $('cal-day-past').hidden = isFuture;
      $('cal-day-future').hidden = !isFuture;

      if (isFuture) {
        // 未来：呈现任务时间提醒
        const view = { tasks, summary: { tasks_done: tasks.filter(t => t.done).length, tasks_total: tasks.length } };
        renderTasks(view, 'cal-day-tasks', 'cal-day-count');
      } else {
        // 过去 / 今天：数据概览 + DeepSeek 日报
        renderDayOverview(actuals, tasks, coins);
        $('cal-day-count').textContent = `${tasks.filter(t => t.done).length}/${tasks.length}`;
        // 重置日报展示（避免旧内容残留）
        const textEl = $('ai-report-text');
        textEl.textContent = '';
        textEl.classList.remove('show');
        $('ai-report-status').textContent = '';
        $('ai-report-status').className = 'ai-report-status';
        $('ai-report-btn').disabled = false;
        $('ai-report-btn').textContent = '✨ 生成 DeepSeek 日报';
      }
    } catch (e) { console.error('fetchTasksForSelected', e); }
  }

  function renderDayOverview(actuals, tasks, coins) {
    // 真实记录
    const recEl = $('cal-overview-records');
    if (!actuals.length) recEl.innerHTML = '<div class="ov-empty">当天没有自由真实记录</div>';
    else recEl.innerHTML = actuals.map((r) => `
      <div class="ov-row">
        <span class="ov-time">${escapeHtml(r.start_time)}–${escapeHtml(r.end_time)}</span>
        <span class="ov-text">${escapeHtml(r.text || '')}</span>
      </div>`).join('');
    // 任务完成
    const taskEl = $('cal-overview-tasks');
    if (!tasks.length) taskEl.innerHTML = '<div class="ov-empty">当天没有排程任务</div>';
    else taskEl.innerHTML = tasks.map((t) => {
      const cat = t.category || 'other';
      const chip = `<span class="cat-chip" style="--cat:${catColor(cat)}">${catLabel(cat)}</span>`;
      const time = t.anchor_time ? `<span class="time-chip">${t.anchor_time}</span>` : '<span class="time-chip dim">·</span>';
      return `<div class="ov-row ${t.done ? 'done' : ''}">
        <span class="ov-check">${t.done ? '✓' : '✗'}</span>
        ${time}${chip}
        <span class="ov-text">${escapeHtml(t.title)}</span>
      </div>`;
    }).join('');
    // 金币分布
    const coinEl = $('cal-overview-coins');
    if (!coins.length) coinEl.innerHTML = '<div class="ov-empty">当天没有金币消耗记录</div>';
    else {
      const maxCoins = Math.max(...coins.map((c) => c.total_min / 60), 0.01);
      coinEl.innerHTML = coins.map((c) => {
        const coinsVal = (c.total_min / 60).toFixed(1);
        const pct = Math.round((c.total_min / 60) / maxCoins * 100);
        const color = catColor(c.category || 'other');
        return `<div class="coin-dist-row">
          <span class="cd-dot" style="background:${color}"></span>
          <span class="cd-label">${catLabel(c.category || 'other')}</span>
          <strong>${coinsVal} 金币</strong>
          <div class="cd-track"><div class="cd-fill" style="width:${pct}%;background:${color}"></div></div>
        </div>`;
      }).join('');
    }
  }

  async function loadDailyReport() {
    const date = state.selectedDate;
    if (!date) return;
    const btn = $('ai-report-btn');
    const status = $('ai-report-status');
    const textEl = $('ai-report-text');
    if (btn) { btn.disabled = true; btn.textContent = '生成中…'; }
    status.className = 'ai-report-status';
    status.textContent = '正在请谋士撰写当日日报…';
    try {
      const r = await api('/api/ai/daily_report', { method: 'POST', body: { date } });
      textEl.textContent = r.report || '';
      textEl.classList.add('show');
      status.textContent = '日报已生成' + (r.model ? `（${r.model}）` : '');
      if (window.AudioManager) AudioManager.play('panel_open');
    } catch (err) {
      status.className = 'ai-report-status error';
      status.textContent = '生成失败：' + (err && err.message ? err.message : err);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '✨ 重新生成日报'; }
    }
  }
  async function refreshCalendarMonth() {
    await fetchCalendar(state.calendarMonth);
    if (!state.selectedDate) state.selectedDate = todayStr();
    await fetchTasksForSelected();
  }

  function setHealth(ok) {
    $('health-status').classList.toggle('offline', !ok);
    $('health-status').textContent = ok ? '●' : '● offline';
  }

  // ===================== 事件 =====================
  // 侧边栏/导航音效：三国志13木牌/玉佩质感
  (function bindNavSounds() {
    let lastHover = 0;
    function throttledHover() {
      const now = performance.now();
      if (now - lastHover < 90) return; // 90ms 节流，避免快速划过多个按钮时爆音
      lastHover = now;
      if (window.AudioManager) window.AudioManager.play('nav_hover');
    }
    function wireNav(el) {
      el.addEventListener('mouseenter', throttledHover);
      el.addEventListener('click', () => { if (window.AudioManager) window.AudioManager.play('nav_click'); });
    }
    document.querySelectorAll('.tab').forEach((b) => {
      wireNav(b);
      b.addEventListener('click', () => switchView(b.dataset.view));
    });
    document.querySelectorAll('.auth-tab').forEach(wireNav);
    document.querySelectorAll('.subtab').forEach(wireNav);
  })();
  $('cal-prev').addEventListener('click', () => { state.calendarMonth = shiftMonth(state.calendarMonth, -1); state.selectedDate = ''; refreshCalendarMonth(); });
  $('cal-next').addEventListener('click', () => { state.calendarMonth = shiftMonth(state.calendarMonth, 1); state.selectedDate = ''; refreshCalendarMonth(); });
  $('cal-today-btn').addEventListener('click', () => { const t = todayStr(); state.calendarMonth = monthStr(t); state.selectedDate = t; refreshCalendarMonth(); });
  state.calendarMonth = monthStr(todayStr()); state.selectedDate = todayStr();
  fetchCalendar(state.calendarMonth).then(() => fetchTasksForSelected());

  $('cal-grid').addEventListener('click', (e) => {
    const cell = e.target.closest('.cal-day');
    if (!cell || cell.classList.contains('is-other')) return;
    state.selectedDate = cell.dataset.date;
    renderCalendar(state.calendarView);
    fetchTasksForSelected();
  });
  $('ai-report-btn').addEventListener('click', loadDailyReport);

  document.addEventListener('click', async (e) => {
    const li = e.target.closest('li[data-id]');
    if (!li) return;
    // 计划视图的「今日事件」面板由自己委托处理，避免重复调用 toggle/del
    if (li.closest('#day-tasks')) return;
    const id = Number(li.dataset.id);
    const act = e.target.dataset.act;
    try {
      if (act === 'toggle') {
        const becomingDone = !li.classList.contains('done');
        await api('/api/tasks/' + id + '/toggle', { method: 'POST' });
        AudioManager.play('task_done');
        if (becomingDone && !prefersReducedMotion()) {
          li.classList.add('just-done');
          await new Promise((r) => setTimeout(r, 420));
        }
      }
      if (act === 'del') {
        if (!(await confirmDialog({ title: '删除任务', message: '删除这条任务？', confirmText: '删除' }))) return;
        await api('/api/tasks/' + id, { method: 'DELETE' });
      }
      if (state.currentView === 'today') await fetchToday();
      if (state.currentView === 'review') await renderReview(state.reviewRange);
      if (state.currentView === 'calendar' || state.currentView === 'year') await refreshCalendarMonth();
    } catch (err) { console.error(err); }
  });

  $('add-task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('new-task-title').value.trim();
    const time = $('new-task-time').value;
    if (!title) return;
    const category = $('new-task-category').value;
    const durVal = parseInt($('new-task-duration').value, 10);
    const duration_min = Number.isFinite(durVal) && durVal > 0 ? durVal : null;
    try {
      await api('/api/tasks?date=' + state.todayDate, { method: 'POST', body: { title, anchor_time: time || null, category, duration_min } });
      $('new-task-title').value = ''; $('new-task-time').value = ''; $('new-task-duration').value = '';
      await fetchToday();
    } catch (err) { showToast('添加失败：' + err.message, 'err'); }
  });

  $('cal-add-task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('cal-new-task-title').value.trim();
    const time = $('cal-new-task-time').value;
    if (!title || !state.selectedDate) return;
    const category = $('cal-new-task-category').value;
    const durVal = parseInt($('cal-new-task-duration').value, 10);
    const duration_min = Number.isFinite(durVal) && durVal > 0 ? durVal : null;
    try {
      await api('/api/tasks?date=' + state.selectedDate, { method: 'POST', body: { title, anchor_time: time || null, category, duration_min } });
      $('cal-new-task-title').value = ''; $('cal-new-task-time').value = ''; $('cal-new-task-duration').value = '';
      await fetchTasksForSelected(); await refreshCalendarMonth();
    } catch (err) { showToast('添加失败：' + err.message, 'err'); }
  });

  // ===================== 账号 / 备份 =====================
  async function loadAccount() {
    try {
      const me = await api('/api/auth/me');
      state.user = me;
      persistAuth(state.token, me);
      $('user-display').textContent = me.display_name || me.username;
      $('account-username').textContent = me.username;
      $('account-displayname').textContent = me.display_name || '—';
      $('account-created').textContent = (me.created_at || '').slice(0, 19).replace('T', ' ');
      $('account-last-login').textContent = (me.last_login_at || '').slice(0, 19).replace('T', ' ') || '—';
      renderSshStatus(me);
      // 设置页若仍存在 SSH 备份密钥卡片，按需启动轮询
      if ($('ssh-status-badge')) {
        if (!me.ssh_registered) startSshPolling();
        else stopSshPolling();
      }
    } catch (e) { console.error('loadAccount', e); }
  }

  function renderSshStatus(me) {
    if (!$('ssh-status-badge')) return; // 设置页已移除 SSH 备份密钥卡片
    if (me.ssh_registered) {
      $('ssh-status-badge').textContent = '已注册 ✓';
      $('ssh-status-badge').style.color = '#6dd58c';
      $('setup-ssh-btn').textContent = '🔄 重新生成密钥';
      $('setup-ssh-btn').disabled = false;
      $('ssh-info').textContent = '公钥已注册到 CVM（' + (me.username || '?') + '）。每天首次备份时由 CVM 验证。';
    } else {
      $('ssh-status-badge').textContent = '未注册';
      $('ssh-status-badge').style.color = '';
      $('setup-ssh-btn').textContent = '🔑 手动初始化';
      $('setup-ssh-btn').disabled = false;
      $('ssh-info').textContent = '后台正在自动注册到 CVM…几秒后会自动变成「已注册 ✓」。';
    }
  }

  let _sshPollTimer = null;
  let _sshPollCount = 0;
  const SSH_POLL_MAX = 40;  // 40 * 3s = 120s
  function startSshPolling() {
    if (_sshPollTimer) return;
    _sshPollCount = 0;
    _sshPollTimer = setInterval(async () => {
      _sshPollCount++;
      try {
        const me = await api('/api/auth/me');
        renderSshStatus(me);
        if (me.ssh_registered) { stopSshPolling(); return; }
      } catch (e) { /* keep polling on transient errors */ }
      if (_sshPollCount >= SSH_POLL_MAX) {
        stopSshPolling();
        $('ssh-info').textContent = '⏳ 后台继续重试中…如果长时间未注册，可手动点「手动初始化」重试。';
      }
    }, 3000);
  }
  function stopSshPolling() {
    if (_sshPollTimer) { clearInterval(_sshPollTimer); _sshPollTimer = null; }
  }

  $('logout-btn').addEventListener('click', async () => { if (await confirmDialog({ title: '退出登录', message: '确定要退出登录？', confirmText: '退出' })) logout(); });

  if ($('setup-ssh-btn')) {
    $('setup-ssh-btn').addEventListener('click', async () => {
      // Electron 默认禁用 window.prompt，改为 in-app modal
      const password = await askPasswordModal('请输入你的登录密码（用于加密本地私钥）');
      if (!password) return;
      setMsg('ssh-msg', '生成密钥对 + 上传公钥 + 等待 CVM 注册（最长 90 秒）…');
      $('setup-ssh-btn').disabled = true;
      try {
        const r = await api('/api/auth/setup-ssh', { method: 'POST', body: { password, poll_timeout: 90 } });
        if (r.ssh_registered) {
          setMsg('ssh-msg', '✓ ' + r.message, 'ok');
          await loadAccount();
        } else {
          setMsg('ssh-msg', '⏳ ' + r.message);
          // 显示 .ok 后用户再点一次「检查状态」
          $('ssh-info').textContent = '公钥已上传到 CVM inbox/，等待 cron 注册（最长 90 秒）';
        }
      } catch (err) {
        setMsg('ssh-msg', '✗ ' + err.message, 'err');
      } finally {
        $('setup-ssh-btn').disabled = false;
      }
    });
  }

  // ===================== 密码输入 modal（替代 window.prompt） =====================
  let _pwdResolver = null;
  function askPasswordModal() {
    return new Promise((resolve) => {
      _pwdResolver = resolve;
      if (!$('pwd-modal')) return resolve(null);
      $('pwd-input').value = '';
      $('pwd-msg').textContent = '';
      $('pwd-msg').className = 'cloud-msg';
      $('pwd-modal').hidden = false;
      setTimeout(() => $('pwd-input').focus(), 0);
    });
  }
  function closePwdModal(password) {
    if ($('pwd-modal')) $('pwd-modal').hidden = true;
    if (_pwdResolver) { const r = _pwdResolver; _pwdResolver = null; r(password); }
  }
  if ($('pwd-form')) {
    $('pwd-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const v = $('pwd-input').value;
      if (!v) { setMsg('pwd-msg', '请输入密码', 'err'); return; }
      closePwdModal(v);
    });
  }
  if ($('pwd-cancel-btn')) {
    $('pwd-cancel-btn').addEventListener('click', () => closePwdModal(null));
  }
  if ($('pwd-modal')) {
    $('pwd-modal').addEventListener('click', (e) => {
      // 点击遮罩关闭
      if (e.target === $('pwd-modal')) closePwdModal(null);
    });
  }
  document.addEventListener('keydown', (e) => {
    const pm = $('pwd-modal');
    if (!pm || pm.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closePwdModal(null); }
    else if (e.key === 'Tab') { e.preventDefault(); trapTab(pm); }
  });

  $('change-pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    setMsg('change-pw-msg', '更新中…');
    try {
      await api('/api/auth/change-password', { method: 'POST', body: { old_password: form.old_password.value, new_password: form.new_password.value } });
      setMsg('change-pw-msg', '✓ 密码已更新', 'ok');
      form.reset();
      loadAccount();
    } catch (err) { setMsg('change-pw-msg', '✗ ' + err.message, 'err'); }
  });

  if ($('cloud-backup-form')) {
    $('cloud-backup-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const passphrase = e.currentTarget.passphrase.value;
      if (passphrase.length < 6) return setMsg('cloud-backup-msg', '密码至少 6 位', 'err');
      if (!state.user?.ssh_registered) {
        return setMsg('cloud-backup-msg', '请先在「备份密钥」里初始化 SSH 密钥', 'err');
      }
      if (!(await confirmDialog({ title: '加密备份', message: '上传当前数据库到 CVM？', confirmText: '上传' }))) return;
      setMsg('cloud-backup-msg', '备份中…（加密 + 上传）');
      try {
        const r = await api('/api/cloud/backup', { method: 'POST', body: { passphrase } });
        setMsg('cloud-backup-msg', '✓ 上传成功 ' + r.size + ' bytes', 'ok');
        e.currentTarget.passphrase.value = '';
        await cloudRefreshList();
        AudioManager.play('backup_ok');
      } catch (err) {
        setMsg('cloud-backup-msg', '✗ ' + err.message, 'err');
        AudioManager.play('backup_fail');
      }
    });
  }

  async function cloudRefreshList() {
    if (!$('cloud-backup-msg')) return;
    setMsg('cloud-backup-msg', '加载列表…');
    try {
      const items = await api('/api/cloud/backups');
      state.cloudBackups = items;
      renderBackupList();
      if ($('cloud-backup-count')) $('cloud-backup-count').textContent = String(items.length);
      setMsg('cloud-backup-msg', items.length ? '✓ 已加载 ' + items.length + ' 条' : '（列表为空）', items.length ? 'ok' : '');
    } catch (err) { setMsg('cloud-backup-msg', '✗ ' + err.message, 'err'); }
  }
  function renderBackupList() {
    const ul = $('cloud-backup-list');
    if (!ul) return;
    if (!state.cloudBackups.length) { ul.innerHTML = '<li class="cloud-empty">（无备份）</li>'; return; }
    ul.innerHTML = state.cloudBackups.map(b => {
      const sizeKb = (b.size / 1024).toFixed(1);
      const date = (b.last_modified || '').slice(0, 19).replace('T', ' ');
      return `<li><div><div class="cb-key">${escapeHtml(b.key)}</div><div class="cb-meta">${sizeKb} KB · ${escapeHtml(date)}</div></div><div class="cb-actions"><button data-act="restore" data-key="${escapeHtml(b.key)}">恢复</button><button data-act="delete" data-key="${escapeHtml(b.key)}">删除</button></div></li>`;
    }).join('');
  }
  if ($('cloud-backup-list')) {
    $('cloud-backup-list').addEventListener('click', async (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      const key = btn.dataset.key;
      if (btn.dataset.act === 'delete') {
        if (!(await confirmDialog({ title: '删除备份', message: '删除这个备份？\n\n' + key, confirmText: '删除', danger: true }))) return;
        try { await api('/api/cloud/backups/' + encodeURIComponent(key), { method: 'DELETE' }); await cloudRefreshList(); }
        catch (err) { showToast('删除失败：' + err.message, 'err'); }
      } else if (btn.dataset.act === 'restore') {
        if (!$('cloud-restore-card')) return;
        $('cloud-restore-card').hidden = false;
        $('cloud-restore-key').value = key;
        $('cloud-restore-info').innerHTML = '目标：<code>' + escapeHtml(key) + '</code>';
        $('cloud-restore-commit-area').hidden = true;
        $('cloud-restore-card').scrollIntoView({ behavior: 'smooth' });
      }
    });
  }
  if ($('cloud-refresh-btn')) {
    $('cloud-refresh-btn').addEventListener('click', cloudRefreshList);
  }

  if ($('cloud-restore-form')) {
    $('cloud-restore-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const key = form.key.value;
      const passphrase = form.passphrase.value;
      if (passphrase.length < 6) return setMsg('cloud-restore-msg', '密码至少 6 位', 'err');
      if (!(await confirmDialog({ title: '下载并解密', message: '下载并解密这个备份？\n\n' + key, confirmText: '下载并解密' }))) return;
      setMsg('cloud-restore-msg', '下载 + 解密中…');
      try {
        const r = await api('/api/cloud/restore/prepare', { method: 'POST', body: { key, passphrase } });
        $('cloud-restore-warn').textContent = '已解密成功（' + (r.size / 1024).toFixed(1) + ' KB）。恢复将覆盖当前所有数据，确认？';
        $('cloud-restore-commit-area').hidden = false;
        $('cloud-restore-commit-area').dataset.tempPath = r.temp_path;
        setMsg('cloud-restore-msg', '✓ 解密成功，等待确认', 'ok');
      } catch (err) { setMsg('cloud-restore-msg', '✗ ' + err.message, 'err'); }
    });
  }
  if ($('cloud-restore-cancel')) {
    $('cloud-restore-cancel').addEventListener('click', () => { if ($('cloud-restore-card')) $('cloud-restore-card').hidden = true; });
  }
  if ($('cloud-restore-discard')) {
    $('cloud-restore-discard').addEventListener('click', () => { if ($('cloud-restore-commit-area')) $('cloud-restore-commit-area').hidden = true; });
  }
  if ($('cloud-restore-commit')) {
    $('cloud-restore-commit').addEventListener('click', async () => {
      const tempPath = $('cloud-restore-commit-area').dataset.tempPath;
      if (!tempPath) return;
      if (!(await confirmDialog({ title: '确认覆盖', message: '确认覆盖？\n\n此操作不可撤销。\n请在确认后手动关闭并重新打开 daydayup。', confirmText: '确认覆盖', danger: true }))) return;
      try {
        await api('/api/cloud/restore/commit', { method: 'POST', body: { temp_path } });
        showToast('✓ 已恢复。请手动重启 daydayup（关闭再打开）。', 'ok');
        $('cloud-restore-commit-area').hidden = true;
      } catch (err) { setMsg('cloud-restore-msg', '✗ ' + err.message, 'err'); }
    });
  }

  function setMsg(elId, text, kind) {
    const el = $(elId);
    if (!el) return;
    el.textContent = text || '';
    el.className = 'cloud-msg' + (kind ? ' ' + kind : '');
  }

  // ===================== 数据管理 =====================
  async function loadDataStats() {
    try {
      const s = await api('/api/data/stats');
      const fmtKb = (b) => (b / 1024).toFixed(1) + ' KB';
      $('data-size-badge').textContent = fmtKb(s.db_size_bytes);
      const cloud = s.cloud_enabled ? `已开启 (${s.cloud_host || '腾讯云'})` : '未配置';
      const last = s.last_backup ? (s.last_backup.uploaded_at || '').slice(0, 19).replace('T', ' ') : '—';
      $('data-stats').innerHTML = `
        <table class="data-stats-table">
          <tr><th>DB 大小</th><td>${fmtKb(s.db_size_bytes)}</td></tr>
          <tr><th>任务</th><td>${s.tables.today_tasks || 0}</td></tr>
          <tr><th>实际记录</th><td>${s.tables.block_actuals || 0}</td></tr>
          <tr><th>设置</th><td>${s.tables.settings || 0}</td></tr>
          <tr><th>本地备份</th><td>${s.tables.cloud_backups || 0}</td></tr>
          <tr><th>年度目标</th><td>${s.tables.goals || 0} / KRs ${s.tables.key_results || 0}</td></tr>
          <tr><th>腾讯云同步</th><td>${cloud}</td></tr>
          <tr><th>最近同步</th><td>${last}</td></tr>
        </table>`;
    } catch (e) { console.error('loadDataStats', e); }
  }

  $('data-export-btn').addEventListener('click', async () => {
    setMsg('data-msg', '准备导出…');
    try {
      const r = await fetch('/api/data/export', { headers: { Authorization: 'Bearer ' + state.token } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const ts = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      const a = document.createElement('a');
      a.href = url; a.download = 'daydayup-' + ts + '.db'; a.click();
      URL.revokeObjectURL(url);
      setMsg('data-msg', '✓ 已下载，请妥善保存', 'ok');
    } catch (err) { setMsg('data-msg', '✗ ' + err.message, 'err'); }
  });

  $('data-import-btn').addEventListener('click', () => $('data-import-file').click());
  $('data-import-file').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!(await confirmDialog({ title: '导入数据库', message: '导入会覆盖当前所有数据，建议先「导出」备份。确定继续？', confirmText: '导入', danger: true }))) {
      e.target.value = ''; return;
    }
    setMsg('data-msg', '上传中…');
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await fetch('/api/data/import', { method: 'POST', headers: { Authorization: 'Bearer ' + state.token }, body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || 'HTTP ' + r.status);
      setMsg('data-msg', '✓ 导入成功。请手动关闭并重新打开 daydayup。', 'ok');
    } catch (err) { setMsg('data-msg', '✗ ' + err.message, 'err'); }
    e.target.value = '';
  });

  $('data-reset-btn').addEventListener('click', async () => {
    if (!(await confirmDialog({ title: '重置', message: '重置会清空任务 / 实际 / 设置 / 目标 / 本地备份元数据。\n\n用户账号、SSH 备份密钥、作息表会保留。', confirmText: '重置', danger: true }))) return;
    if (!(await confirmDialog({ title: '最后确认', message: '真的重置？此操作不可撤销。', confirmText: '确定重置', danger: true }))) return;
    setMsg('data-msg', '重置中…');
    try {
      const r = await api('/api/data/reset', { method: 'POST', body: { confirm: true } });
      setMsg('data-msg', '✓ 重置完成。已删除: ' + JSON.stringify(r.deleted), 'ok');
      await loadDataStats();
    } catch (err) { setMsg('data-msg', '✗ ' + err.message, 'err'); }
  });

  // ===================== 音效设置 =====================
  function initAudioUI() {
    const s = AudioManager.getSettings();
    const en = $('audio-enabled');
    const vol = $('audio-volume');
    const volOut = $('audio-volume-out');
    const mh = $('audio-mute-hidden');
    const badge = $('audio-status-badge');
    function paint() {
      en.checked = s.enabled;
      vol.value = String(Math.round(s.volume * 100));
      volOut.textContent = Math.round(s.volume * 100) + '%';
      mh.checked = s.muteWhenHidden;
      badge.textContent = s.enabled ? '开' : '关';
      badge.style.color = s.enabled ? 'var(--success)' : '';
    }
    paint();
    en.addEventListener('change', () => { AudioManager.setEnabled(en.checked); Object.assign(s, AudioManager.getSettings()); paint(); });
    vol.addEventListener('input', () => { AudioManager.setVolume(vol.value / 100); Object.assign(s, AudioManager.getSettings()); paint(); });
    mh.addEventListener('change', () => { AudioManager.setMuteWhenHidden(mh.checked); Object.assign(s, AudioManager.getSettings()); paint(); });
    document.querySelectorAll('[data-audio-preview]').forEach((btn) => {
      btn.addEventListener('click', () => AudioManager.preview(btn.dataset.audioPreview));
    });
  }

  // ===================== 年度 OKR =====================
  let stateYear = new Date().getFullYear();

  async function loadGoals() {
    try {
      const goals = await api('/api/goals?year=' + stateYear);
      renderGoals(goals);
    } catch (e) { console.error('loadGoals', e); }
  }
  function renderGoals(goals) {
    const ul = $('goal-list');
    $('year-total-badge').textContent = String(goals.length);
    if (!goals.length) { ul.innerHTML = '<li class="cloud-empty">该年份暂无目标。</li>'; $('year-summary').textContent = ''; return; }
    const total = goals.length;
    const done = goals.filter(g => g.status === 'done').length;
    const avgPct = Math.round(goals.reduce((s, g) => s + (g.progress || 0), 0) / total);
    const active = goals.filter(g => g.status === 'active').length;
    const paused = goals.filter(g => g.status === 'paused').length;
    $('year-summary').textContent = `共 ${total} 个目标 · ${done} 已完成 · 平均进度 ${avgPct}%`;
    // 年度进度概览：今年时间已过 vs 目标平均进度
    const now = new Date();
    const y = now.getFullYear();
    const timePct = Math.round(((now - new Date(y, 0, 1)) / (new Date(y + 1, 0, 1) - new Date(y, 0, 1))) * 100);
    const ov = $('year-overview');
    if (ov) {
      ov.hidden = false;
      $('yo-time-fill').style.width = timePct + '%';
      $('yo-time-val').textContent = timePct + '%';
      $('yo-goal-fill').style.width = avgPct + '%';
      $('yo-goal-val').textContent = avgPct + '%';
      $('year-status').textContent = `进行中 ${active} · 已完成 ${done} · 已暂停 ${paused}`;
    }
    const catNames = { work: '工作', life: '生活', health: '健康', study: '学习', other: '其他' };
    ul.innerHTML = goals.map(g => {
      const krs = g.key_results || [];
      const cat = catNames[g.category] || g.category;
      const stBadge = { active: '进行中', done: '已完成', paused: '已暂停', dropped: '已放弃' }[g.status] || g.status;
      return `<li class="goal-card" data-id="${g.id}">
        <div class="goal-head">
          <div class="goal-title">${escapeHtml(g.title)}</div>
          <span class="goal-cat">${cat}</span>
          <span class="goal-status status-${g.status}">${stBadge}</span>
          <div class="goal-actions">
            <button data-act="edit" data-id="${g.id}">编辑</button>
            <button data-act="del" data-id="${g.id}">删除</button>
          </div>
        </div>
        ${g.description ? `<div class="goal-desc">${escapeHtml(g.description)}</div>` : ''}
        <div class="progress-row">
          <div class="progress-bar"><div class="progress-fill" style="width:${g.progress || 0}%"></div></div>
          <span class="progress-pct">${g.progress || 0}%</span>
        </div>
        <div class="kr-list">
          ${krs.map(kr => `<div class="kr-item">
            <input type="checkbox" data-kr-id="${kr.id}" data-kr-goal="${g.id}" ${kr.done ? 'checked' : ''} />
            <span class="kr-title ${kr.done ? 'done' : ''}">${escapeHtml(kr.title)}</span>
            ${(kr.target_value != null && kr.unit) ? `<span class="kr-progress">${kr.current_value || 0} / ${kr.target_value} ${escapeHtml(kr.unit || '')}</span>` : ''}
            <button data-act="delkr" data-kr-id="${kr.id}" data-goal-id="${g.id}" title="删除">×</button>
          </div>`).join('')}
          <div class="kr-add">
            <input type="text" placeholder="添加关键结果 (KR)…" maxlength="200" data-kr-add="${g.id}" />
            <button data-act="addr" data-goal-id="${g.id}">+</button>
          </div>
        </div>
      </li>`;
    }).join('');
  }

  $('year-filter').addEventListener('change', (e) => { stateYear = Number(e.target.value); loadGoals(); });

  $('add-goal-btn').addEventListener('click', () => openGoalModal());

  function openGoalModal(goal) {
    const m = $('goal-modal');
    _goalLastFocus = document.activeElement;
    m.hidden = false;
    $('goal-modal-title').textContent = goal ? '✏️ 编辑目标' : '➕ 新目标';
    const f = $('goal-form');
    f.reset();
    f.id.value = goal ? goal.id : '';
    if (goal) {
      f.title.value = goal.title || '';
      f.category.value = goal.category || 'work';
      f.year.value = goal.year || stateYear;
      f.description.value = goal.description || '';
      f.target_date.value = goal.target_date || '';
    } else {
      f.year.value = stateYear;
    }
    setMsg('goal-form-msg', '');
    setTimeout(() => { try { f.title.focus(); } catch (_) {} }, 0);
  }
  function closeGoalModal() {
    $('goal-modal').hidden = true;
    if (_goalLastFocus && _goalLastFocus.focus) _goalLastFocus.focus();
  }
  $('goal-cancel-btn').addEventListener('click', closeGoalModal);
  document.addEventListener('keydown', (e) => {
    const m = $('goal-modal');
    if (m.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); closeGoalModal(); }
    else if (e.key === 'Tab') { e.preventDefault(); trapTab(m); }
  });

  $('goal-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const id = f.id.value;
    const data = {
      title: f.title.value.trim(),
      category: f.category.value,
      year: Number(f.year.value),
      description: f.description.value.trim(),
      target_date: f.target_date.value || null,
    };
    setMsg('goal-form-msg', '保存中…');
    try {
      if (id) {
        await api('/api/goals/' + id, { method: 'PATCH', body: data });
      } else {
        await api('/api/goals', { method: 'POST', body: data });
      }
      closeGoalModal();
      await loadGoals();
    } catch (err) { setMsg('goal-form-msg', '✗ ' + err.message, 'err'); }
  });

  // 卡片内操作：编辑 / 删除 / 勾选 KR / 添加 KR / 删除 KR
  $('goal-list').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const act = btn.dataset.act;
    const id = Number(btn.dataset.id || btn.dataset.goalId);
    try {
      if (act === 'edit') {
        const g = await api('/api/goals/' + id);
        openGoalModal(g);
      } else if (act === 'del') {
        if (!(await confirmDialog({ title: '删除目标', message: '删除这个目标？其下 KRs 也会删除。', confirmText: '删除', danger: true }))) return;
        await api('/api/goals/' + id, { method: 'DELETE' });
        await loadGoals();
      } else if (act === 'delkr') {
        if (!(await confirmDialog({ title: '删除 KR', message: '删除这个 KR？', confirmText: '删除', danger: true }))) return;
        await api('/api/key-results/' + btn.dataset.krId, { method: 'DELETE' });
        await loadGoals();
      } else if (act === 'addr') {
        const input = document.querySelector(`input[data-kr-add="${id}"]`);
        const title = (input && input.value || '').trim();
        if (!title) return;
        await api('/api/goals/' + id + '/key-results', { method: 'POST', body: { title } });
        if (input) input.value = '';
        await loadGoals();
      }
    } catch (err) { showToast('操作失败：' + err.message, 'err'); }
  });

  $('goal-list').addEventListener('change', async (e) => {
    if (e.target.matches('input[type=checkbox][data-kr-id]')) {
      const krId = Number(e.target.dataset.krId);
      const done = e.target.checked;
      try {
        await api('/api/key-results/' + krId, { method: 'PATCH', body: { done } });
        await loadGoals();
      } catch (err) { showToast('更新失败：' + err.message, 'err'); }
    }
  });

  // ===================== 目标页：日/周/月/年 + AI 荐策 =====================
  function isoOf(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
  function addDaysISO(iso, n) {
    const d = new Date(iso + 'T00:00:00');
    d.setDate(d.getDate() + n);
    return isoOf(d);
  }
  function startOfWeekISO(iso) {
    const d = new Date(iso + 'T00:00:00');
    const day = d.getDay(); // 0=周日
    const diff = (day === 0 ? -6 : 1 - day);
    d.setDate(d.getDate() + diff);
    return isoOf(d);
  }
  function monthRange(iso) {
    const [y, m] = iso.split('-').map(Number);
    const first = `${y}-${pad(m)}-01`;
    const last = new Date(y, m, 0); // 当月最后一天
    return [first, `${y}-${pad(m)}-${pad(last.getDate())}`];
  }
  function yearRange(iso) {
    const y = Number(iso.split('-')[0]);
    return [`${y}-01-01`, `${y}-12-31`];
  }

  // 启发式「AI 荐策」：分析近 90 天历史事件，推演今日宜为之事
  const DEFAULT_RECS = [
    { title: '晨间复盘：立下今日三件要事', anchor_time: '08:00', reason: '暂无足够历史，先定今日基调' },
    { title: '攻坚今日最重要的一项工作', anchor_time: '09:30', reason: '深睡后专注力最佳' },
    { title: '运动舒展 30 分钟', anchor_time: '18:00', reason: '养身方能久战' },
    { title: '阅读 / 学习 1 小时', anchor_time: '21:00', reason: '日拱一卒，功不唐捐' },
  ];
  function normTitle(t) {
    return (t || '').toLowerCase().replace(/[\s　]+/g, '').replace(/[^\p{L}\p{N}]/gu, '');
  }
  function medianTime(times) {
    const mins = times.map((t) => { const [h, m] = t.split(':').map(Number); return h * 60 + m; })
      .sort((a, b) => a - b);
    const mid = mins[Math.floor(mins.length / 2)];
    return `${pad(Math.floor(mid / 60))}:${pad(mid % 60)}`;
  }
  function computeRecommendations(history) {
    const map = new Map();
    for (const t of history) {
      const key = normTitle(t.title);
      if (!key) continue;
      if (!map.has(key)) map.set(key, { title: t.title, count: 0, done: 0, times: [] });
      const e = map.get(key);
      e.count++; if (t.done) e.done++; if (t.anchor_time) e.times.push(t.anchor_time);
    }
    const cands = [...map.values()].filter((e) => e.count >= 2)
      .sort((a, b) => b.count - a.count).slice(0, 6);
    if (cands.length === 0) {
      return DEFAULT_RECS.map((r) => ({ ...r, freq: 0, doneRate: 0, adopted: false }));
    }
    return cands.map((e) => ({
      title: e.title,
      anchor_time: e.times.length ? medianTime(e.times) : null,
      freq: e.count,
      doneRate: Math.round((e.done / e.count) * 100),
      reason: `近 90 天出现 ${e.count} 次 · 完成率 ${Math.round((e.done / e.count) * 100)}%`,
      adopted: false,
    }));
  }

  let _recs = [];
  async function loadRecommendations() {
    const sub = $('ai-rec-sub');
    try {
      const year = new Date().getFullYear();
      const [goals, recent, planned] = await Promise.all([
        api('/api/goals?year=' + year).catch(() => []),
        api(`/api/tasks_in_range?start=${addDaysISO(todayStr(), -30)}&end=${addDaysISO(todayStr(), -1)}`).catch(() => []),
        api('/api/tasks?date=' + todayStr()).catch(() => []),
      ]);
      const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date().getDay()];
      const context = {
        today: todayStr(),
        weekday: wd,
        goals: (goals || []).map((g) => ({ title: g.title, description: g.description })),
        recent: (recent || []).map((t) => ({ task_date: t.task_date, title: t.title, anchor_time: t.anchor_time, done: t.done })),
        planned: (planned || []).map((t) => ({ title: t.title, anchor_time: t.anchor_time })),
      };
      try {
        const r = await api('/api/ai/analyze', { method: 'POST', body: { context } });
        _recs = (r.schedule || []).filter((x) => x.title).map((x) => ({ ...x, adopted: false }));
        $('ai-rec-sub').textContent = r.insight
          ? '谋士洞察：' + r.insight
          : '基于你的目标与历史，DeepSeek 推演今日宜为之事。';
        renderRecommendations();
      } catch (aiErr) {
        // DeepSeek 不可用 → 回退本地启发式，保证功能不中断
        const msg = aiErr && aiErr.message ? aiErr.message : '';
        $('ai-rec-sub').textContent = '（DeepSeek 暂不可用，已切换本地推演）' + (msg ? ' · ' + msg : '');
        const end = addDaysISO(todayStr(), -1);
        const start = addDaysISO(todayStr(), -90);
        const history = await api(`/api/tasks_in_range?start=${start}&end=${end}`).catch(() => []);
        _recs = computeRecommendations(history);
        renderRecommendations();
      }
    } catch (err) {
      sub.textContent = '推演失败：' + err.message;
      $('ai-rec-list').innerHTML = '<li class="cloud-empty">暂无法推演，请稍后再试。</li>';
    }
  }

  // 未来计划 → 事件安排推荐（调用 /api/ai/plan）
  async function loadPlanRecommendations() {
    const box = $('ai-plan-input');
    const planText = (box && box.value || '').trim();
    if (!planText) {
      $('ai-rec-sub').textContent = '请先在上方描述你的未来计划。';
      if (box) box.focus();
      return;
    }
    const btn = $('ai-plan-btn');
    if (btn) { btn.disabled = true; btn.textContent = '推演中…'; }
    try {
      const year = new Date().getFullYear();
      const [goals, recent, planned] = await Promise.all([
        api('/api/goals?year=' + year).catch(() => []),
        api(`/api/tasks_in_range?start=${addDaysISO(todayStr(), -30)}&end=${addDaysISO(todayStr(), -1)}`).catch(() => []),
        api('/api/tasks?date=' + todayStr()).catch(() => []),
      ]);
      const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][new Date().getDay()];
      const context = {
        plan_text: planText,
        today: todayStr(),
        weekday: wd,
        goals: (goals || []).map((g) => ({ title: g.title, description: g.description })),
        recent: (recent || []).map((t) => ({ task_date: t.task_date, title: t.title, anchor_time: t.anchor_time, done: t.done })),
        planned: (planned || []).map((t) => ({ title: t.title, anchor_time: t.anchor_time })),
      };
      const r = await api('/api/ai/plan', { method: 'POST', body: { plan_text: planText, context } });
      _recs = (r.schedule || []).filter((x) => x.title).map((x) => ({ ...x, adopted: false }));
      $('ai-rec-sub').textContent = r.insight
        ? '谋士洞察：' + r.insight
        : '已基于你的计划生成事件安排推荐。';
      renderRecommendations();
    } catch (err) {
      const msg = err && err.message ? err.message : '';
      $('ai-rec-sub').textContent = '生成失败：' + msg;
      $('ai-rec-list').innerHTML = '<li class="cloud-empty">暂无法生成，请稍后再试。</li>';
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '✨ 生成安排推荐'; }
    }
  }

  // 今日作息轴：DeepSeek 定制推荐（调用 /api/ai/schedule）
  async function loadAiSchedule() {
    const box = $('ai-schedule-input');
    const userInput = (box && box.value || '').trim();
    const btn = $('ai-schedule-btn');
    const status = $('ai-schedule-status');
    const resetBtn = $('ai-schedule-reset');
    if (btn) { btn.disabled = true; btn.textContent = '生成中…'; }
    status.className = 'ai-schedule-status';
    status.textContent = '正在请谋士推演今日作息…';
    try {
      const year = new Date().getFullYear();
      const [goals, recent, planned] = await Promise.all([
        api('/api/goals?year=' + year).catch(() => []),
        api(`/api/tasks_in_range?start=${addDaysISO(todayStr(), -30)}&end=${addDaysISO(todayStr(), -1)}`).catch(() => []),
        api('/api/tasks?date=' + todayStr()).catch(() => []),
      ]);
      const d = new Date();
      const wd = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
      const isWorkday = d.getDay() >= 1 && d.getDay() <= 5;
      const context = {
        user_input: userInput,
        today: todayStr(),
        weekday: wd,
        is_workday: isWorkday,
        location: '', // 未来可从用户设置读取
        weather: '', // 未来可接入天气 API
        goals: (goals || []).map((g) => ({ title: g.title, description: g.description })),
        recent: (recent || []).map((t) => ({ task_date: t.task_date, title: t.title, anchor_time: t.anchor_time, done: t.done })),
        planned: (planned || []).map((t) => ({ title: t.title, anchor_time: t.anchor_time, duration_min: t.duration_min })),
      };
      const r = await api('/api/ai/schedule', { method: 'POST', body: { user_input: userInput, context } });
      const rawBlocks = r.blocks || [];
      // 转成 timeline 需要的格式
      state.aiBlocks = rawBlocks.map((b, i) => ({
        id: 1000 + i,
        label: b.label,
        anchor_time: b.start_time,
        end_time: b.end_time,
        note: b.note,
        weekdays: '1,2,3,4,5,6,7',
        enabled: true,
        kind: 'block',
      })).filter((b) => b.anchor_time && b.end_time);
      renderTimeline(state.view);
      status.textContent = '已生成定制作息轴，点击「恢复默认」可回到原有推荐。';
      if (resetBtn) resetBtn.hidden = false;
      if (window.AudioManager) AudioManager.play('view_switch');
    } catch (err) {
      const msg = err && err.message ? err.message : '';
      status.className = 'ai-schedule-status error';
      status.textContent = '生成失败：' + msg;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = '✨ 生成推荐作息'; }
    }
  }

  function resetAiSchedule() {
    state.aiBlocks = null;
    renderTimeline(state.view);
    $('ai-schedule-status').textContent = '已恢复默认作息推荐。';
    $('ai-schedule-reset').hidden = true;
  }

  function renderRecommendations() {
    const ul = $('ai-rec-list');
    if (!_recs.length) { ul.innerHTML = '<li class="cloud-empty">暂无推荐。</li>'; return; }
    ul.innerHTML = _recs.map((r, i) => `
      <li class="ai-rec-item" data-i="${i}">
        <div class="ai-rec-main">
          <div class="ai-rec-title">${escapeHtml(r.title)}</div>
          <div class="ai-rec-meta">
            ${r.anchor_time ? `<span class="ai-rec-time">⏰ ${formatTimeRange(r.anchor_time, r.duration_min)}</span>` : '<span class="ai-rec-time">⏰ 不限时</span>'}
            <span class="ai-rec-reason">${escapeHtml(r.reason)}</span>
          </div>
        </div>
        <div class="ai-rec-actions">
          <button class="ai-rec-adopt" data-act="adopt" data-i="${i}">采纳</button>
          <button class="ai-rec-edit" data-act="edit" data-i="${i}">改</button>
          <button class="ai-rec-skip" data-act="skip" data-i="${i}">略</button>
        </div>
      </li>`).join('');
  }

  function formatTimeRange(anchor_time, duration_min) {
    if (!anchor_time) return '不限时';
    if (!duration_min || duration_min <= 0) return anchor_time;
    const [h, m] = anchor_time.split(':').map(Number);
    const total = h * 60 + m + duration_min;
    const eh = Math.floor(total / 60) % 24;
    const em = total % 60;
    const end = `${String(eh).padStart(2, '0')}:${String(em).padStart(2, '0')}`;
    return `${anchor_time}–${end}`;
  }

  // 采纳：写入今日事件
  $('ai-rec-list').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const i = Number(btn.dataset.i);
    const rec = _recs[i];
    if (!rec) return;
    const act = btn.dataset.act;
    if (act === 'skip') {
      _recs.splice(i, 1); renderRecommendations();
    } else if (act === 'adopt') {
      try {
        const body = { title: rec.title, anchor_time: rec.anchor_time || null };
        if (rec.duration_min && rec.duration_min > 0) body.duration_min = rec.duration_min;
        await api('/api/tasks?date=' + todayStr(), { method: 'POST', body });
        showToast('已采纳：' + rec.title, 'ok');
        _recs.splice(i, 1); renderRecommendations();
        await loadDayEvents();
      } catch (err) { showToast('采纳失败：' + err.message, 'err'); }
    } else if (act === 'edit') {
      const li = btn.closest('.ai-rec-item');
      li.innerHTML = `
        <div class="ai-rec-main">
          <input type="text" class="ai-edit-title" value="${escapeHtml(rec.title)}" maxlength="200" />
          <div class="ai-edit-row">
            <input type="time" class="ai-edit-time" value="${rec.anchor_time || ''}" />
            <input type="number" class="ai-edit-duration" value="${rec.duration_min || ''}" min="1" max="1440" placeholder="分钟" />
          </div>
        </div>
        <div class="ai-rec-actions">
          <button class="ai-rec-adopt" data-act="save" data-i="${i}">存</button>
          <button class="ai-rec-skip" data-act="skip" data-i="${i}">取消</button>
        </div>`;
      li.querySelector('.ai-edit-title').focus();
    } else if (act === 'save') {
      const li = btn.closest('.ai-rec-item');
      const title = li.querySelector('.ai-edit-title').value.trim();
      const time = li.querySelector('.ai-edit-time').value || null;
      const durVal = parseInt(li.querySelector('.ai-edit-duration').value, 10);
      const duration_min = Number.isFinite(durVal) && durVal > 0 ? durVal : null;
      if (!title) { showToast('标题不可为空', 'err'); return; }
      try {
        const body = { title, anchor_time: time };
        if (duration_min) body.duration_min = duration_min;
        await api('/api/tasks?date=' + todayStr(), { method: 'POST', body });
        showToast('已采纳：' + title, 'ok');
        _recs.splice(i, 1); renderRecommendations();
        await loadDayEvents();
      } catch (err) { showToast('采纳失败：' + err.message, 'err'); }
    }
  });

  // 日 / 周 / 月 / 年 加载
  async function loadDayEvents() {
    try {
      const tasks = await api('/api/tasks?date=' + todayStr());
      $('day-tasks').innerHTML = tasks.map((t) => {
        const cat = t.category || 'other';
        return `<li class="${t.done ? 'done' : ''}" data-id="${t.id}">
          <button type="button" class="checkbox" data-act="toggle" aria-label="完成">${t.done ? '✓' : ''}</button>
          ${t.anchor_time ? `<span class="time-chip">⏰ ${formatTimeRange(t.anchor_time, t.duration_min)}</span>` : '<span class="time-chip dim">·</span>'}
          <span class="cat-chip" style="--cat:${catColor(cat)}">${catLabel(cat)}</span>
          <span class="label">${escapeHtml(t.title)}</span>
          <button class="delete" data-act="del" title="删除" aria-label="删除">×</button>
        </li>`;
      }).join('') || '<li class="task-empty"><span>📝 今天还没有事件，可以手动添加或采纳上方谋士荐策。</span></li>';
      const done = tasks.filter((t) => t.done).length;
      $('day-count').textContent = `${done}/${tasks.length}`;
    } catch (err) { $('day-tasks').innerHTML = '<li class="task-empty"><span>加载失败</span></li>'; }
  }
  $('day-tasks').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const li = btn.closest('li[data-id]');
    if (!li) return;
    const id = Number(li.dataset.id);
    try {
      if (btn.dataset.act === 'toggle') { await api('/api/tasks/' + id + '/toggle', { method: 'POST' }); AudioManager.play('task_done'); }
      if (btn.dataset.act === 'del') { if (!(await confirmDialog({ title: '删除事件', message: '删除这条今日事件？', confirmText: '删除', danger: true }))) return; await api('/api/tasks/' + id, { method: 'DELETE' }); }
      await loadDayEvents();
    } catch (err) { showToast('操作失败：' + err.message, 'err'); }
  });

  function updateTargetDuration() {
    const start = $('target-day-time').value;
    const end = $('target-day-end').value;
    const out = $('target-day-duration-display');
    if (!start || !end) { out.textContent = '—'; return; }
    const startMin = hmToMin(start), endMin = hmToMin(end);
    let dur = endMin - startMin;
    if (dur <= 0) dur += 24 * 60;
    const h = Math.floor(dur / 60);
    const m = dur % 60;
    out.textContent = h > 0 ? `${h}小时${m}分钟` : `${m}分钟`;
  }
  $('target-day-time').addEventListener('input', updateTargetDuration);
  $('target-day-end').addEventListener('input', updateTargetDuration);

  $('target-day-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('target-day-title').value.trim();
    const time = $('target-day-time').value || null;
    const end = $('target-day-end').value || null;
    if (!title) return;
    let duration_min = null;
    if (time && end) {
      const s = hmToMin(time), e = hmToMin(end);
      duration_min = e - s;
      if (duration_min <= 0) duration_min += 24 * 60;
    }
    const category = $('target-day-category').value;
    try {
      await api('/api/tasks?date=' + todayStr(), { method: 'POST', body: { title, anchor_time: time, category, duration_min } });
      $('target-day-title').value = ''; $('target-day-time').value = ''; $('target-day-end').value = '';
      $('target-day-duration-display').textContent = '—';
      await loadDayEvents();
    } catch (err) { showToast('添加失败：' + err.message, 'err'); }
  });

  async function loadWeekEvents() {
    try {
      const start = startOfWeekISO(todayStr());
      const end = addDaysISO(start, 6);
      const tasks = await api(`/api/tasks_in_range?start=${start}&end=${end}`);
      const wd = ['一', '二', '三', '四', '五', '六', '日'];
      const byDay = Array.from({ length: 7 }, () => []);
      tasks.forEach((t) => {
        const idx = (new Date(t.task_date + 'T00:00:00').getDay() + 6) % 7;
        byDay[idx].push(t);
      });
      $('week-grid').innerHTML = byDay.map((arr, i) => `
        <div class="week-col ${i === ((new Date().getDay() + 6) % 7) ? 'is-today' : ''}">
          <div class="week-col-head">周${wd[i]}<span class="week-col-count">${arr.length}</span></div>
          <ul class="week-col-list">
            ${arr.map((t) => `<li class="${t.done ? 'done' : ''}"><span>${escapeHtml(t.title)}</span>${t.anchor_time ? `<em>${t.anchor_time}</em>` : ''}</li>`).join('') || '<li class="week-empty">—</li>'}
          </ul>
        </div>`).join('');
      const done = tasks.filter((t) => t.done).length;
      $('week-count').textContent = `${done}/${tasks.length}`;
    } catch (err) { $('week-grid').innerHTML = '<p class="cloud-empty">加载失败</p>'; }
  }

  async function loadMonthEvents() {
    try {
      const [start, end] = monthRange(todayStr());
      const tasks = await api(`/api/tasks_in_range?start=${start}&end=${end}`);
      const done = tasks.filter((t) => t.done).length;
      const rate = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
      $('month-done-fill').style.width = rate + '%';
      $('month-done-val').textContent = tasks.length ? `${rate}% (${done}/${tasks.length})` : '—';
      // 按周分组概览
      const weeks = {};
      tasks.forEach((t) => {
        const wk = Math.ceil(new Date(t.task_date + 'T00:00:00').getDate() / 7);
        (weeks[wk] = weeks[wk] || []).push(t);
      });
      $('month-weeks').innerHTML = Object.keys(weeks).sort().map((wk) => {
        const arr = weeks[wk];
        const wd = arr.filter((t) => t.done).length;
        return `<div class="month-week-row">
          <span class="month-week-label">第${wk}周</span>
          <span class="month-week-rate">${Math.round((wd / arr.length) * 100)}%</span>
          <span class="month-week-count">${wd}/${arr.length}</span>
        </div>`;
      }).join('') || '<p class="cloud-empty">本月暂无事件。</p>';
      $('month-count').textContent = `${done}/${tasks.length}`;
    } catch (err) { $('month-weeks').innerHTML = '<p class="cloud-empty">加载失败</p>'; }
  }

  async function loadYearEvents() {
    try {
      const [start, end] = yearRange(todayStr());
      const tasks = await api(`/api/tasks_in_range?start=${start}&end=${end}`);
      const done = tasks.filter((t) => t.done).length;
      $('year-summary').textContent = `本年事件 ${tasks.length} 条 · 已完成 ${done} 条`;
      await loadGoals();
    } catch (err) { /* 容错 */ }
  }

  async function loadTargets() {
    $('ai-rec-sub').textContent = '基于近 90 天行事轨迹，推演今日宜为之事。';
    await loadRecommendations();
    await loadDayEvents();
    const active = document.querySelector('.subtab.is-active')?.dataset.range || 'day';
    if (active === 'week') await loadWeekEvents();
    else if (active === 'month') await loadMonthEvents();
    else if (active === 'year') await loadYearEvents();
  }

  // 分段切换
  document.querySelectorAll('#target-subtabs .subtab').forEach((b) => {
    b.addEventListener('click', async () => {
      const range = b.dataset.range;
      document.querySelectorAll('#target-subtabs .subtab').forEach((x) => x.classList.toggle('is-active', x === b));
      ['day', 'week', 'month', 'year'].forEach((r) => { $('panel-' + r).hidden = (r !== range); });
      if (range === 'day') await loadDayEvents();
      else if (range === 'week') await loadWeekEvents();
      else if (range === 'month') await loadMonthEvents();
      else if (range === 'year') await loadYearEvents();
    });
  });
  // 回顾分段切换（日 / 周 / 月）
  document.querySelectorAll('#review-subtabs .subtab').forEach((b) => {
    b.addEventListener('click', async () => {
      const range = b.dataset.range;
      state.reviewRange = range;
      document.querySelectorAll('#review-subtabs .subtab').forEach((x) => x.classList.toggle('is-active', x === b));
      await renderReview(range);
    });
  });

  $('ai-regen-btn').addEventListener('click', loadRecommendations);
  $('ai-plan-btn').addEventListener('click', loadPlanRecommendations);
  $('ai-schedule-btn').addEventListener('click', loadAiSchedule);
  $('ai-schedule-reset').addEventListener('click', resetAiSchedule);

  // 绑定真实记录网格创建事件（只绑定一次）
  attachActualGridCreate();

  // ===================== PWA + 启动 =====================
  // 桌面端禁用 Service Worker：后端始终本地可用，缓存会导致更新后仍显示旧界面
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then((regs) => {
      regs.forEach((r) => r.unregister());
    }).catch(() => {});
  }

  function tickClock() {
    $('now-time').textContent = (() => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; })();
    if (state.view && state.view.next_block) $('cb-next-when').textContent = '· ' + countdown(state.view.next_block.anchor_time);
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    if (window._lastMin !== nowMin) {
      window._lastMin = nowMin;
      if (state.view) { renderCurrentBlock(state.view); refreshTimelineStates(state.view); }
      onMinuteChange(nowMin);
    }
  }

  // 仅更新「当前/过去/未来」状态类，避免每分钟重建整条时间轴而打断正在输入的实际记录
  function refreshTimelineStates(view) {
    if (document.activeElement && document.activeElement.classList.contains('tl-actual')) return;
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    const items = document.querySelectorAll('#timeline .tl-item');
    view.blocks.forEach((b, i) => {
      const li = items[i];
      if (!li) return;
      const startMin = hmToMin(b.anchor_time), endMin = hmToMin(b.end_time);
      li.classList.toggle('is-current', startMin <= nowMin && nowMin < endMin);
      li.classList.toggle('is-future', nowMin < startMin);
      li.classList.toggle('is-past', nowMin >= endMin);
    });
  }

  // 每分钟换点：作息块切换音效 + 任务到点音效
  function onMinuteChange(nowMin) {
    if (!state.view) return;
    // 1) 作息块切换
    const cur = state.view.current_block;
    if (cur) {
      const start = hmToMin(cur.anchor_time);
      if (nowMin === start && window._lastMin !== start) {
        AudioManager.play('block_change');
      }
    }
    // 2) 任务到点
    if (state.view.tasks) {
      const hhmm = `${pad(Math.floor(nowMin/60))}:${pad(nowMin%60)}`;
      for (const t of state.view.tasks) {
        if (t.anchor_time === hhmm && !t.done && !t._alerted) {
          t._alerted = true;
          AudioManager.play('task_due');
        }
      }
    }
  }

  function bootstrap() {
    if (state._booted) return;
    state._booted = true;
    fetchToday();
    setInterval(tickClock, 1000);
    setInterval(fetchToday, 60_000);
  }

  // ===================== 全局拖拽导入 .db 数据库文件 =====================
  // 拖拽 .db 备份到窗口任意位置 → 复用 /api/data/import 接口导入
  (function setupDragDropImport() {
    let dragDepth = 0;
    let overlay = null;

    function ensureOverlay() {
      if (overlay) return overlay;
      overlay = document.createElement('div');
      overlay.id = 'dragdrop-overlay';
      overlay.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:9999', 'display:none',
        'align-items:center', 'justify-content:center',
        'background:rgba(15,17,21,.78)', 'backdrop-filter:blur(2px)',
        'pointer-events:none',
      ].join(';');
      overlay.innerHTML =
        '<div style="text-align:center;border:2px dashed #d4a373;border-radius:16px;padding:48px 64px;background:rgba(26,29,36,.9)">' +
        '<div style="font-size:48px;line-height:1">📥</div>' +
        '<div style="color:#e9c89b;font-size:18px;margin-top:12px">松开以导入数据库备份</div>' +
        '<div style="color:#9a8d7a;font-size:13px;margin-top:6px">导入会覆盖当前所有数据，请确认已备份</div>' +
        '</div>';
      document.body.appendChild(overlay);
      return overlay;
    }

    function hasFiles(e) {
      return e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
    }

    window.addEventListener('dragenter', (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth++;
      ensureOverlay().style.display = 'flex';
    });
    window.addEventListener('dragover', (e) => {
      if (hasFiles(e)) e.preventDefault(); // 允许 drop
    });
    window.addEventListener('dragleave', (e) => {
      if (!hasFiles(e)) return;
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) ensureOverlay().style.display = 'none';
    });
    window.addEventListener('drop', async (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth = 0;
      ensureOverlay().style.display = 'none';
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!file) return;
      if (!/\.db$/i.test(file.name)) {
        showToast('只支持 .db 数据库备份文件', 'err');
        return;
      }
      if (!state.token) {
        showToast('请先登录再导入数据', 'err');
        return;
      }
      const ok = await confirmDialog({
        title: '拖拽导入数据库',
        message: '将导入「' + file.name + '」(' + (file.size / 1024).toFixed(0) + ' KB)。\n导入会覆盖当前所有数据，建议先「导出」备份。确定继续？',
        confirmText: '导入',
        danger: true,
      });
      if (!ok) return;
      showToast('上传中…');
      const fd = new FormData();
      fd.append('file', file);
      try {
        const r = await fetch('/api/data/import', {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + state.token },
          body: fd,
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || 'HTTP ' + r.status);
        showToast('✓ 导入成功，正在刷新…', 'ok');
        setTimeout(() => location.reload(), 800);
      } catch (err) {
        showToast('✗ ' + err.message, 'err');
      }
    });
  })();

  // 启动：决定显示 auth-gate 还是 app
  if (state.token && state.user) {
    // 试着拉一次 /me 验证 token 还有效
    api('/api/auth/me').then((me) => {
      persistAuth(state.token, me);
      showApp();
      bootstrap();
    }).catch(() => {
      persistAuth(null, null);
      showAuthGate();
    });
  } else {
    showAuthGate();
  }
})();
