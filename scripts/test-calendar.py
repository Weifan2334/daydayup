import asyncio
import httpx
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8765'
PAST = '2026-07-15'   # a past date in current month
FUTURE = '2026-07-25' # a future date in current month

async def main():
    # --- Backend seeding (deterministic: clear then seed) ---
    async with httpx.AsyncClient() as c:
        r = await c.post(f'{BASE}/api/auth/login', json={'username': 'testuser2', 'password': 'testpass123'})
        assert r.status_code == 200, f'login failed: {r.status_code}'
        token = r.json()['token']
        h = {'Authorization': f'Bearer {token}'}
        # clear prior seeded data for deterministic runs
        await c.post(f'{BASE}/api/init/clear_user_data', headers=h)
        # clear_user_data does NOT purge actual_records, so clean test dates manually
        for d in (PAST, FUTURE):
            for rec in (await c.get(f'{BASE}/api/actual_records?date={d}', headers=h)).json():
                await c.delete(f'{BASE}/api/actual_records?id={rec["id"]}', headers=h)
        # create tasks on past date
        await c.post(f'{BASE}/api/tasks?date={PAST}', json={'title': '写周报', 'anchor_time': '14:00', 'category': 'work', 'duration_min': 60}, headers=h)
        await c.post(f'{BASE}/api/tasks?date={PAST}', json={'title': '跑步', 'anchor_time': '07:00', 'category': 'health', 'duration_min': 30}, headers=h)
        tasks = await c.get(f'{BASE}/api/tasks_in_range?start={PAST}&end={PAST}', headers=h)
        for t in tasks.json():
            if t['title'] == '跑步':
                await c.post(f'{BASE}/api/tasks/{t["id"]}/toggle', headers=h)
        # actual record on past date
        await c.post(f'{BASE}/api/actual_records', json={'date': PAST, 'start_time': '20:00', 'end_time': '21:30', 'text': '看了一集纪录片'}, headers=h)
        # coins sanity
        coins = await c.get(f'{BASE}/api/coins?date={PAST}', headers=h)
        print('coins for past', coins.status_code, coins.text[:200])
        # future task
        await c.post(f'{BASE}/api/tasks?date={FUTURE}', json={'title': '体检', 'anchor_time': '09:30', 'category': 'health', 'duration_min': 90}, headers=h)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # Log in inside the page (token present before reload) — more reliable than
        # add_init_script, which races the backend still busy from seeding.
        await page.goto(BASE)
        await page.evaluate(f"""async () => {{
            const r = await fetch('/api/auth/login', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{username:'testuser2', password:'testpass123'}})}});
            const j = await r.json();
            localStorage.setItem('daydayup_token', j.token);
            localStorage.setItem('daydayup_user', JSON.stringify({{username:'testuser2'}}));
        }}""")
        # retry until the app unlocks (auth-gate hidden after /api/auth/me)
        unlocked = False
        for _ in range(3):
            await page.reload()
            try:
                await page.wait_for_selector('#auth-gate', state='hidden', timeout=8000)
                unlocked = True
                break
            except Exception:
                continue
        assert unlocked, 'app did not unlock (auth-gate still visible)'
        await page.wait_for_timeout(400)
        # JS-dispatched clicks bypass Playwright actionability (calendar entrance animation
        # makes cells "unstable" and the transiently-shown auth-gate trips occlusion checks).
        async def js_click(sel):
            await page.evaluate(f"document.querySelector({sel!r}).click()")

        # 1. Nav order
        tabs = await page.locator('.tab').all_inner_texts()
        print('NAV ORDER:', tabs)
        assert tabs == ['计划', '今日', '回顾', '日历', '设置'], f'nav order wrong: {tabs}'

        # Activate the calendar tab (app ignores ?view= URL param)
        await js_click('.tab[data-view="calendar"]')
        await page.wait_for_selector(f'.cal-day[data-date="{PAST}"]', timeout=10000)
        await page.wait_for_timeout(400)

        # 2. Click a past date cell
        await js_click(f'.cal-day[data-date="{PAST}"]')
        await page.wait_for_timeout(700)
        past_visible = await page.locator('#cal-day-past').is_visible()
        future_hidden = not await page.locator('#cal-day-future').is_visible()
        mode = await page.locator('#cal-day-mode').inner_text()
        recs = await page.locator('#cal-overview-records .ov-row').count()
        tasks_ov = await page.locator('#cal-overview-tasks .ov-row').count()
        coins_ov = await page.locator('#cal-overview-coins .coin-dist-row').count()
        print('PAST:', past_visible, future_hidden, '| mode=', mode, '| records=', recs, 'tasks=', tasks_ov, 'coins=', coins_ov)
        assert past_visible and future_hidden, 'past section not shown'
        assert recs >= 1 and tasks_ov >= 1 and coins_ov >= 1, 'overview incomplete'

        # 3. Click daily report button (no key -> graceful error)
        await js_click('#ai-report-btn')
        await page.wait_for_timeout(900)
        status = await page.locator('#ai-report-status').inner_text()
        print('REPORT STATUS:', status)
        assert '失败' in status or '未配置' in status, 'should show graceful failure without key'

        # 4. Click a future date cell
        await js_click(f'.cal-day[data-date="{FUTURE}"]')
        await page.wait_for_timeout(700)
        future_visible = await page.locator('#cal-day-future').is_visible()
        past_hidden = not await page.locator('#cal-day-past').is_visible()
        mode_f = await page.locator('#cal-day-mode').inner_text()
        fut_tasks = await page.locator('#cal-day-tasks li').count()
        print('FUTURE:', future_visible, past_hidden, '| mode=', mode_f, '| tasks=', fut_tasks)
        assert future_visible and past_hidden, 'future section not shown'
        assert fut_tasks >= 1, 'future tasks empty'

        await page.screenshot(path='D:/04_范伟/lifemgr-pwa/.workbuddy/test-calendar.png')
        print('ALL CHECKS PASSED')
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
