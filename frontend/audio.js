/* daydayup AudioManager v0.3
 * Web Audio API 合成 5 种提示音（无文件依赖）。
 * 触发：block_change / task_due / task_done / backup_ok / backup_fail
 * 规则：首次用户交互后才创建 AudioContext（autoplay policy）
 *      document.hidden 时不响（焦点不在 daydayup）
 *      5 秒渐入开关（防启动时突然响）
 * 持久化：localStorage
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'daydayup_audio_v1';
  const DEFAULT = { enabled: true, volume: 0.5, muteWhenHidden: true };

  // ---- 5 种音（频率 + 时长 + 波形）----
  const SOUNDS = {
    block_change: [
      { freq: 880, dur: 0.12, type: 'sine' }
    ],
    task_due: [
      { freq: 1175, dur: 0.10, type: 'sine' },
      { freq: 1320, dur: 0.10, type: 'sine' }
    ],
    task_done: [
      { freq: 1320, dur: 0.08, type: 'sine' },
      { freq: 1760, dur: 0.10, type: 'sine' }
    ],
    backup_ok: [
      { freq: 880, dur: 0.10, type: 'sine' },
      { freq: 1108, dur: 0.10, type: 'sine' },
      { freq: 1320, dur: 0.16, type: 'sine' }
    ],
    backup_fail: [
      { freq: 220, dur: 0.50, type: 'sawtooth' }
    ],
  };

  function loadSettings() {
    try {
      const s = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      return s ? Object.assign({}, DEFAULT, s) : Object.assign({}, DEFAULT);
    } catch (_) {
      return Object.assign({}, DEFAULT);
    }
  }

  function saveSettings(s) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        enabled: s.enabled,
        volume: s.volume,
        muteWhenHidden: s.muteWhenHidden,
      }));
    } catch (_) {}
  }

  // 合成单个音调
  function tone(ctx, freq, dur, type, masterGain, startTime) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;

    // ADSR 包络：5ms attack + hold + 30ms release，避免 click pop
    const t0 = startTime;
    const t1 = t0 + dur;
    const peak = masterGain;
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(peak, t0 + 0.005);
    gain.gain.setValueAtTime(peak, t1 - 0.030);
    gain.gain.linearRampToValueAtTime(0, t1);

    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t0);
    osc.stop(t1 + 0.01);
  }

  // 状态
  const settings = loadSettings();
  let ctx = null;
  let startedAt = performance.now();
  let fadeInMs = 5000; // 首次启动后 5 秒内的音全部静默
  let userInteracted = false;

  function ensureCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      try { ctx = new AC(); } catch (_) { return null; }
    }
    if (ctx && ctx.state === 'suspended') ctx.resume().catch(() => {});
    return ctx;
  }

  // 公共 API
  function play(name) {
    if (!settings.enabled) return;
    if (settings.muteWhenHidden && document.hidden) return;
    // 启动 5 秒渐入静默
    if (performance.now() - startedAt < fadeInMs) return;
    const seq = SOUNDS[name];
    if (!seq) return;
    const audio = ensureCtx();
    if (!audio) return;
    const master = settings.volume;
    let t = audio.currentTime + 0.02;
    for (const note of seq) {
      tone(audio, note.freq, note.dur, note.type, master, t);
      t += note.dur + 0.02; // 间隔
    }
  }

  function setEnabled(v) { settings.enabled = !!v; saveSettings(settings); }
  function setVolume(v) {
    settings.volume = Math.max(0, Math.min(1, Number(v)));
    saveSettings(settings);
  }
  function setMuteWhenHidden(v) { settings.muteWhenHidden = !!v; saveSettings(settings); }
  function getSettings() { return Object.assign({}, settings); }

  // 测试按钮用（跳过渐入静默）
  function preview(name) {
    const seq = SOUNDS[name];
    if (!seq) return;
    const audio = ensureCtx();
    if (!audio) return;
    const master = settings.volume;
    let t = audio.currentTime + 0.02;
    for (const note of seq) {
      tone(audio, note.freq, note.dur, note.type, master, t);
      t += note.dur + 0.02;
    }
  }

  // 首次用户交互时创建 AudioContext（autoplay policy）
  function bindFirstInteraction() {
    const handler = () => {
      userInteracted = true;
      ensureCtx();
      window.removeEventListener('click', handler);
      window.removeEventListener('keydown', handler);
      window.removeEventListener('touchstart', handler);
    };
    window.addEventListener('click', handler, { once: true });
    window.addEventListener('keydown', handler, { once: true });
    window.addEventListener('touchstart', handler, { once: true });
  }
  bindFirstInteraction();

  // 暴露全局
  window.AudioManager = {
    play, preview,
    setEnabled, setVolume, setMuteWhenHidden, getSettings,
    SOUNDS,
  };
})();
