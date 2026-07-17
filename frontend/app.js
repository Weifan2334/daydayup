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
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
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
    const ol = $('timeline'); ol.innerHTML = '';
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    const actuals = view.actuals || {};
    view.blocks.forEach((b) => {
      const startMin = hmToMin(b.anchor_time), endMin = hmToMin(b.end_time);
      const li = document.createElement('li');
      li.className = 'tl-item';
      if (startMin <= nowMin && nowMin < endMin) li.classList.add('is-current');
      else if (nowMin < startMin) li.classList.add('is-future');
      else li.classList.add('is-past');
      const dur = endMin - startMin;
      const durLabel = dur >= 60 ? `${(dur / 60).toFixed(1)}h` : `${dur}m`;
      const actualText = actuals[String(b.id)] || '';
      li.innerHTML = `
        <div class="tl-time"><span class="tl-start">${b.anchor_time}</span><span class="tl-dash">→</span><span class="tl-end">${b.end_time}</span></div>
        <div class="tl-marker"></div>
        <div class="tl-body">
          <div class="tl-plan">
            <div class="tl-row"><div class="tl-title">${escapeHtml(b.label)}</div><span class="tl-dur">${durLabel}</span></div>
            ${b.note ? `<div class="tl-note">${escapeHtml(b.note)}</div>` : ''}
          </div>
          <div class="tl-actual-wrap">
            <textarea class="tl-actual" data-block-id="${b.id}" rows="1" placeholder="实际...">${escapeHtml(actualText)}</textarea>
            <div class="tl-actual-save" id="save-${b.id}"></div>
          </div>
        </div>`;
      ol.appendChild(li);
      autosize(li.querySelector('.tl-actual'));
    });
    attachActualHandlers();
    $('blocks-count').textContent = view.blocks.length;
  }
  function autosize(el) { el.style.height = 'auto'; el.style.height = el.scrollHeight + 'px'; }
  function hmToMin(hm) { const [h, m] = hm.split(':').map(Number); return h * 60 + m; }
  function attachActualHandlers() {
    document.querySelectorAll('.tl-actual').forEach((ta) => {
      if (ta.dataset.bound) return; ta.dataset.bound = '1';
      let timer = null;
      const blockId = Number(ta.dataset.blockId);
      const statusEl = document.getElementById('save-' + blockId);
      const save = async () => {
        if (timer) { clearTimeout(timer); timer = null; }
        const text = ta.value;
        if (statusEl) { statusEl.className = 'tl-actual-save saving'; statusEl.textContent = '保存中…'; }
        try {
          await api('/api/block_actual', { method: 'POST', body: { date: state.todayDate, block_id: blockId, actual_text: text } });
          if (statusEl) { statusEl.className = 'tl-actual-save saved'; statusEl.textContent = text ? '已保存 ✓' : ''; }
        } catch (e) {
          if (statusEl) { statusEl.className = 'tl-actual-save error'; statusEl.textContent = '保存失败'; }
        }
      };
      ta.addEventListener('input', () => { autosize(ta); if (timer) clearTimeout(timer); if (statusEl) { statusEl.className = 'tl-actual-save saving'; statusEl.textContent = '输入中…'; } timer = setTimeout(save, 1500); });
      ta.addEventListener('blur', save);
      if (ta.value && statusEl) { statusEl.className = 'tl-actual-save saved'; statusEl.textContent = '已保存 ✓'; }
    });
  }
  function renderTasks(view, containerId = 'task-list', countId = 'task-count') {
    const ul = $(containerId); ul.innerHTML = '';
    if (!view.tasks.length) { const li = document.createElement('li'); li.className = 'task-empty'; li.innerHTML = '<span>还没有任务，下方加一条？</span>'; ul.appendChild(li); }
    view.tasks.forEach((t) => {
      const li = document.createElement('li');
      if (t.done) li.classList.add('done');
      li.dataset.id = t.id;
      const timeChip = t.anchor_time ? `<span class="time-chip">${t.anchor_time}</span>` : '<span class="time-chip dim">·</span>';
      const dur = t.duration_min ? ` <small>· ${t.duration_min} min</small>` : '';
      li.innerHTML = `<span class="checkbox" data-act="toggle">${t.done ? '✓' : ''}</span>${timeChip}<span class="label">${escapeHtml(t.title)}${dur}</span><button class="delete" data-act="del" title="删除">×</button>`;
      ul.appendChild(li);
    });
    if (countId && view.summary) $(countId).textContent = `${view.summary.tasks_done}/${view.summary.tasks_total}`;
  }
  function renderTodayView(view) {
    state.view = view; state.todayDate = view.today_date;
    renderTopBar(view); renderCurrentBlock(view); renderTimeline(view); renderTasks(view);
  }

  // ===================== 自律成长 banner =====================
  // 用本地时区计算「注册日期到今天」的天数，注册当天 = 第 1 天
  function daysSinceRegister(isoDate) {
    if (!isoDate) return null;
    const dateStr = String(isoDate).slice(0, 10); // "YYYY-MM-DD"
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
    if (!m) return null;
    const registered = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    if (isNaN(registered.getTime())) return null;
    const now = new Date();
    const todayMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const diffMs = todayMidnight - registered;
    const days = Math.floor(diffMs / 86400000) + 1;
    return days > 0 ? days : 1;
  }

  function renderAccountBanner(user) {
    const banner = $('account-banner');
    if (!banner) return;
    if (!user || !user.created_at) {
      banner.hidden = true;
      return;
    }
    const days = daysSinceRegister(user.created_at);
    const since = String(user.created_at).slice(0, 10);
    $('ab-days').textContent = days == null ? '—' : String(days);
    $('ab-since').textContent = since;
    $('ab-username').textContent = user.display_name || user.username || '—';
    banner.hidden = false;
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
  function switchView(name) {
    if (name !== 'today' && name !== 'calendar' && name !== 'settings' && name !== 'year') return;
    state.currentView = name;
    document.querySelectorAll('.tab').forEach((b) => b.classList.toggle('is-active', b.dataset.view === name));
    $('view-today').hidden = (name !== 'today');
    $('view-calendar').hidden = (name !== 'calendar');
    $('view-settings').hidden = (name !== 'settings');
    $('view-year').hidden = (name !== 'year');
    if (name === 'calendar') {
      if (!state.calendarMonth) state.calendarMonth = monthStr(todayStr());
      if (!state.calendarView || state.calendarView.month !== state.calendarMonth) fetchCalendar(state.calendarMonth);
    } else if (name === 'settings') {
      loadAccount();
      initAudioUI();
      loadDataStats();
    } else if (name === 'year') {
      loadGoals();
    }
  }

  // ===================== 数据获取 =====================
  async function fetchToday() {
    try { renderTodayView(await api('/api/today')); setHealth(true); }
    catch (e) { console.error('fetchToday', e); setHealth(false); }
  }
  async function fetchCalendar(month) {
    try { renderCalendar(await api('/api/calendar?month=' + month)); }
    catch (e) { console.error('fetchCalendar', e); }
  }
  async function fetchTasksForSelected() {
    if (!state.selectedDate) return;
    try {
      const tasks = await api('/api/tasks_in_range?start=' + state.selectedDate + '&end=' + state.selectedDate);
      const view = { tasks, summary: { tasks_done: tasks.filter(t => t.done).length, tasks_total: tasks.length } };
      renderTasks(view, 'cal-day-tasks', 'cal-day-count');
      const dt = new Date(state.selectedDate + 'T00:00:00');
      const wd = ['周日','周一','周二','周三','周四','周五','周六'][dt.getDay()];
      $('cal-day-title').textContent = `${state.selectedDate} ${wd}`;
      $('cal-day-card').hidden = false;
    } catch (e) { console.error('fetchTasksForSelected', e); }
  }
  async function refreshCalendarMonth() {
    await fetchCalendar(state.calendarMonth);
    if (state.selectedDate && state.selectedDate.startsWith(state.calendarMonth)) {
      await fetchTasksForSelected();
    } else { $('cal-day-card').hidden = true; state.selectedDate = ''; }
  }

  function setHealth(ok) {
    $('health-status').classList.toggle('offline', !ok);
    $('health-status').textContent = ok ? '●' : '● offline';
  }

  // ===================== 事件 =====================
  document.querySelectorAll('.tab').forEach((b) => b.addEventListener('click', () => switchView(b.dataset.view)));
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

  document.addEventListener('click', async (e) => {
    const li = e.target.closest('li[data-id]');
    if (!li) return;
    const id = Number(li.dataset.id);
    const act = e.target.dataset.act;
    try {
      if (act === 'toggle') {
        await api('/api/tasks/' + id + '/toggle', { method: 'POST' });
        AudioManager.play('task_done');
      }
      if (act === 'del') { if (!confirm('删除这条任务？')) return; await api('/api/tasks/' + id, { method: 'DELETE' }); }
      if (state.currentView === 'today') await fetchToday();
      await refreshCalendarMonth();
    } catch (err) { console.error(err); }
  });

  $('add-task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('new-task-title').value.trim();
    const time = $('new-task-time').value;
    if (!title) return;
    try {
      await api('/api/tasks?date=' + state.todayDate, { method: 'POST', body: { title, anchor_time: time || null } });
      $('new-task-title').value = ''; $('new-task-time').value = '';
      await fetchToday();
    } catch (err) { alert('添加失败：' + err.message); }
  });

  $('cal-add-task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = $('cal-new-task-title').value.trim();
    const time = $('cal-new-task-time').value;
    if (!title || !state.selectedDate) return;
    try {
      await api('/api/tasks?date=' + state.selectedDate, { method: 'POST', body: { title, anchor_time: time || null } });
      $('cal-new-task-title').value = ''; $('cal-new-task-time').value = '';
      await fetchTasksForSelected(); await refreshCalendarMonth();
    } catch (err) { alert('添加失败：' + err.message); }
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
      if (me.ssh_registered) {
        $('ssh-status-badge').textContent = '已注册 ✓';
        $('ssh-status-badge').style.color = '#6dd58c';
        $('setup-ssh-btn').textContent = '🔄 重新生成密钥';
        $('ssh-info').textContent = '公钥已注册到 CVM（' + (me.username || '?') + '）。每天首次备份时由 CVM 验证。';
      } else {
        $('ssh-status-badge').textContent = '未配置';
        $('ssh-status-badge').style.color = '';
        $('setup-ssh-btn').textContent = '🔑 初始化备份密钥';
        $('ssh-info').textContent = '';
      }
    } catch (e) { console.error('loadAccount', e); }
  }

  $('logout-btn').addEventListener('click', () => { if (confirm('确定要退出登录？')) logout(); });

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

  // ===================== 密码输入 modal（替代 window.prompt） =====================
  let _pwdResolver = null;
  function askPasswordModal() {
    return new Promise((resolve) => {
      _pwdResolver = resolve;
      $('pwd-input').value = '';
      $('pwd-msg').textContent = '';
      $('pwd-msg').className = 'cloud-msg';
      $('pwd-modal').hidden = false;
      setTimeout(() => $('pwd-input').focus(), 0);
    });
  }
  function closePwdModal(password) {
    $('pwd-modal').hidden = true;
    if (_pwdResolver) { const r = _pwdResolver; _pwdResolver = null; r(password); }
  }
  $('pwd-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const v = $('pwd-input').value;
    if (!v) { setMsg('pwd-msg', '请输入密码', 'err'); return; }
    closePwdModal(v);
  });
  $('pwd-cancel-btn').addEventListener('click', () => closePwdModal(null));
  $('pwd-modal').addEventListener('click', (e) => {
    // 点击遮罩关闭
    if (e.target === $('pwd-modal')) closePwdModal(null);
  });
  document.addEventListener('keydown', (e) => {
    if (!$('pwd-modal').hidden && e.key === 'Escape') closePwdModal(null);
  });

  $('change-pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    setMsg('change-pw-msg', '更新中…');
    try {
      await api('/api/auth/change-password', { method: 'POST', body: { old_password: form.old_password.value, new_password: form.new_password.value } });
      setMsg('change-pw-msg', '✓ 密码已更新。请重新「初始化备份密钥」', 'ok');
      form.reset();
      loadAccount();
    } catch (err) { setMsg('change-pw-msg', '✗ ' + err.message, 'err'); }
  });

  $('cloud-backup-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const passphrase = e.currentTarget.passphrase.value;
    if (passphrase.length < 6) return setMsg('cloud-backup-msg', '密码至少 6 位', 'err');
    if (!state.user?.ssh_registered) {
      return setMsg('cloud-backup-msg', '请先在「备份密钥」里初始化 SSH 密钥', 'err');
    }
    if (!confirm('上传当前数据库到 CVM？')) return;
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

  async function cloudRefreshList() {
    setMsg('cloud-backup-msg', '加载列表…');
    try {
      const items = await api('/api/cloud/backups');
      state.cloudBackups = items;
      renderBackupList();
      $('cloud-backup-count').textContent = String(items.length);
      setMsg('cloud-backup-msg', items.length ? '✓ 已加载 ' + items.length + ' 条' : '（列表为空）', items.length ? 'ok' : '');
    } catch (err) { setMsg('cloud-backup-msg', '✗ ' + err.message, 'err'); }
  }
  function renderBackupList() {
    const ul = $('cloud-backup-list');
    if (!state.cloudBackups.length) { ul.innerHTML = '<li class="cloud-empty">（无备份）</li>'; return; }
    ul.innerHTML = state.cloudBackups.map(b => {
      const sizeKb = (b.size / 1024).toFixed(1);
      const date = (b.last_modified || '').slice(0, 19).replace('T', ' ');
      return `<li><div><div class="cb-key">${escapeHtml(b.key)}</div><div class="cb-meta">${sizeKb} KB · ${escapeHtml(date)}</div></div><div class="cb-actions"><button data-act="restore" data-key="${escapeHtml(b.key)}">恢复</button><button data-act="delete" data-key="${escapeHtml(b.key)}">删除</button></div></li>`;
    }).join('');
  }
  $('cloud-backup-list').addEventListener('click', async (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const key = btn.dataset.key;
    if (btn.dataset.act === 'delete') {
      if (!confirm('删除这个备份？\n\n' + key)) return;
      try { await api('/api/cloud/backups/' + encodeURIComponent(key), { method: 'DELETE' }); await cloudRefreshList(); }
      catch (err) { alert('删除失败：' + err.message); }
    } else if (btn.dataset.act === 'restore') {
      $('cloud-restore-card').hidden = false;
      $('cloud-restore-key').value = key;
      $('cloud-restore-info').innerHTML = '目标：<code>' + escapeHtml(key) + '</code>';
      $('cloud-restore-commit-area').hidden = true;
      $('cloud-restore-card').scrollIntoView({ behavior: 'smooth' });
    }
  });
  $('cloud-refresh-btn').addEventListener('click', cloudRefreshList);

  $('cloud-restore-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const key = form.key.value;
    const passphrase = form.passphrase.value;
    if (passphrase.length < 6) return setMsg('cloud-restore-msg', '密码至少 6 位', 'err');
    if (!confirm('下载并解密这个备份？\n\n' + key)) return;
    setMsg('cloud-restore-msg', '下载 + 解密中…');
    try {
      const r = await api('/api/cloud/restore/prepare', { method: 'POST', body: { key, passphrase } });
      $('cloud-restore-warn').textContent = '已解密成功（' + (r.size / 1024).toFixed(1) + ' KB）。恢复将覆盖当前所有数据，确认？';
      $('cloud-restore-commit-area').hidden = false;
      $('cloud-restore-commit-area').dataset.tempPath = r.temp_path;
      setMsg('cloud-restore-msg', '✓ 解密成功，等待确认', 'ok');
    } catch (err) { setMsg('cloud-restore-msg', '✗ ' + err.message, 'err'); }
  });
  $('cloud-restore-cancel').addEventListener('click', () => { $('cloud-restore-card').hidden = true; });
  $('cloud-restore-discard').addEventListener('click', () => { $('cloud-restore-commit-area').hidden = true; });
  $('cloud-restore-commit').addEventListener('click', async () => {
    const tempPath = $('cloud-restore-commit-area').dataset.tempPath;
    if (!tempPath) return;
    if (!confirm('确认覆盖？\n\n此操作不可撤销。\n请在确认后手动关闭并重新打开 daydayup。')) return;
    try {
      await api('/api/cloud/restore/commit', { method: 'POST', body: { temp_path } });
      alert('✓ 已恢复。请手动重启 daydayup（关闭再打开）。');
      $('cloud-restore-commit-area').hidden = true;
    } catch (err) { setMsg('cloud-restore-msg', '✗ ' + err.message, 'err'); }
  });

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
      const ssh = s.ssh_registered ? '✓' : '✗';
      const cloud = s.cloud_enabled ? `已配 (${s.cloud_host})` : '未配';
      const last = s.last_backup ? (s.last_backup.uploaded_at || '').slice(0, 19).replace('T', ' ') : '—';
      $('data-stats').innerHTML = `
        <table class="data-stats-table">
          <tr><th>DB 大小</th><td>${fmtKb(s.db_size_bytes)}</td></tr>
          <tr><th>任务</th><td>${s.tables.today_tasks || 0}</td></tr>
          <tr><th>实际记录</th><td>${s.tables.block_actuals || 0}</td></tr>
          <tr><th>设置</th><td>${s.tables.settings || 0}</td></tr>
          <tr><th>本地备份</th><td>${s.tables.cloud_backups || 0}</td></tr>
          <tr><th>年度目标</th><td>${s.tables.goals || 0} / KRs ${s.tables.key_results || 0}</td></tr>
          <tr><th>SSH 备份密钥</th><td>${ssh}</td></tr>
          <tr><th>云备份配置</th><td>${cloud}</td></tr>
          <tr><th>最近备份</th><td>${last}</td></tr>
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
    if (!confirm('导入会覆盖当前所有数据，建议先「导出」备份。确定继续？')) {
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
    if (!confirm('重置会清空任务 / 实际 / 设置 / 目标 / 本地备份元数据。\n\n用户账号、SSH 备份密钥、作息表会保留。\n\n确定继续？')) return;
    if (!confirm('真的重置？此操作不可撤销。')) return;
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
    $('year-summary').textContent = `共 ${total} 个目标 · ${done} 已完成 · 平均进度 ${avgPct}%`;
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
    const m = $('goal-modal'); m.hidden = false;
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
  }
  function closeGoalModal() { $('goal-modal').hidden = true; }
  $('goal-cancel-btn').addEventListener('click', closeGoalModal);

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
        if (!confirm('删除这个目标？其下 KRs 也会删除。')) return;
        await api('/api/goals/' + id, { method: 'DELETE' });
        await loadGoals();
      } else if (act === 'delkr') {
        if (!confirm('删除这个 KR？')) return;
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
    } catch (err) { alert('操作失败：' + err.message); }
  });

  $('goal-list').addEventListener('change', async (e) => {
    if (e.target.matches('input[type=checkbox][data-kr-id]')) {
      const krId = Number(e.target.dataset.krId);
      const done = e.target.checked;
      try {
        await api('/api/key-results/' + krId, { method: 'PATCH', body: { done } });
        await loadGoals();
      } catch (err) { alert('更新失败：' + err.message); }
    }
  });

  // ===================== PWA + 启动 =====================
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  }

  function tickClock() {
    $('now-time').textContent = (() => { const d = new Date(); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; })();
    if (state.view && state.view.next_block) $('cb-next-when').textContent = '· ' + countdown(state.view.next_block.anchor_time);
    const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
    if (window._lastMin !== nowMin) {
      window._lastMin = nowMin;
      if (state.view) { renderCurrentBlock(state.view); renderTimeline(state.view); }
      onMinuteChange(nowMin);
    }
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
    renderAccountBanner(state.user);
    fetchToday();
    setInterval(tickClock, 1000);
    setInterval(fetchToday, 60_000);
  }

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
