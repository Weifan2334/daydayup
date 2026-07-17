"""add-year-css.py -- append v0.3 year-view (OKR) styles to styles.css"""
fp = r'C:\Users\fanwei\.openclaw\workspace\lifemgr-pwa\frontend\styles.css'
with open(fp, 'rb') as f:
    raw = f.read()

new_block = b'''
/* =============== v0.3 \xe5\xb9\xb4\xe5\xba\xa6 OKR =============== */
.year-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.year-toolbar label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-dim); margin: 0; }
.year-toolbar select { padding: 6px 10px; background: var(--bg-input); border: 1px solid var(--border-strong); border-radius: var(--r-sm); color: var(--text); font-size: 12px; }
.year-summary {
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 10px;
  padding: 6px 10px;
  background: var(--bg-elev);
  border-radius: var(--r-sm);
  border-left: 3px solid var(--accent);
}
.goal-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.goal-card {
  background: var(--bg-elev);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-md);
  padding: 14px 16px;
  transition: box-shadow 0.15s;
}
.goal-card:hover { box-shadow: var(--shadow-sm); }
.goal-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.goal-title { font-size: 15px; font-weight: 700; color: var(--text); flex: 1; min-width: 100px; }
.goal-cat {
  font-size: 11px;
  padding: 2px 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  color: var(--text-dim);
}
.goal-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.goal-status.status-active { background: rgba(160, 90, 44, 0.15); color: var(--accent); }
.goal-status.status-done { background: rgba(94, 124, 84, 0.18); color: var(--success); }
.goal-status.status-paused { background: rgba(154, 138, 114, 0.18); color: var(--text-mute); }
.goal-status.status-dropped { background: rgba(160, 64, 48, 0.18); color: var(--danger); opacity: 0.7; }
.goal-actions { display: flex; gap: 4px; }
.goal-actions button {
  padding: 4px 10px;
  font-size: 11px;
  background: var(--bg-card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}
.goal-actions button:hover { background: var(--accent-bg); border-color: var(--accent); color: var(--accent); }
.goal-desc {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
  margin-bottom: 10px;
  white-space: pre-wrap;
}
.progress-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg-card);
  border-radius: 3px;
  overflow: hidden;
  border: 1px solid var(--border);
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--accent-soft));
  transition: width 0.3s ease;
}
.progress-pct {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  min-width: 38px;
  text-align: right;
}
.kr-list { display: flex; flex-direction: column; gap: 4px; padding-top: 6px; border-top: 1px dashed var(--border); }
.kr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
}
.kr-item input[type=checkbox] { width: 15px; height: 15px; cursor: pointer; accent-color: var(--success); }
.kr-title { flex: 1; color: var(--text); }
.kr-title.done { color: var(--text-mute); text-decoration: line-through; }
.kr-progress { font-size: 11px; color: var(--text-mute); font-variant-numeric: tabular-nums; }
.kr-item button { background: transparent; border: none; color: var(--text-mute); cursor: pointer; padding: 0 6px; font-size: 14px; line-height: 1; }
.kr-item button:hover { color: var(--danger); }
.kr-add {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dotted var(--border);
}
.kr-add input {
  flex: 1;
  padding: 5px 10px;
  font-size: 12px;
}
.kr-add button {
  padding: 5px 12px;
  font-size: 13px;
  font-weight: 600;
  background: var(--bg-card);
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
}
.kr-add button:hover { background: var(--accent-bg); border-color: var(--accent); }

/* Modal */
.modal {
  position: fixed; inset: 0;
  background: rgba(45, 36, 25, 0.5);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
  padding: 20px;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.modal-card {
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-lg);
  padding: 24px 28px;
  max-width: 480px;
  width: 100%;
  box-shadow: var(--shadow-md), var(--shadow-glow);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  max-height: 90vh;
  overflow-y: auto;
}
.modal-card h3 {
  margin: 0 0 16px;
  font-size: 16px;
  color: var(--text);
  font-weight: 700;
}
.cloud-form textarea {
  padding: 8px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  resize: vertical;
  min-height: 50px;
}
.cloud-form textarea:focus { border-color: var(--accent); }
.cloud-form select {
  padding: 8px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  cursor: pointer;
}
.cloud-form select:focus { border-color: var(--accent); }
.cloud-form input[type=number],
.cloud-form input[type=date] {
  padding: 8px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-sm);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
}
.cloud-form input[type=number]:focus,
.cloud-form input[type=date]:focus { border-color: var(--accent); }
'''

with open(fp, 'ab') as f:
    f.write(new_block)
print('appended, has goal-card:', b'goal-card' in new_block)
print('new size:', len(raw) + len(new_block))
