import asyncio
import httpx
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8765'

async def main():
    async with httpx.AsyncClient() as c:
        r = await c.post(f'{BASE}/api/auth/login', json={'username': 'testuser2', 'password': 'testpass123'})
        token = r.json()['token']

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        msgs = []
        page.on('console', lambda m: msgs.append(f"{m.type}: {m.text}"))
        page.on('pageerror', lambda e: msgs.append(f"PAGEERROR: {e}"))

        await page.goto(BASE)
        await page.evaluate("""async () => {
            const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:'testuser2', password:'testpass123'})});
            const j = await r.json();
            localStorage.setItem('daydayup_token', j.token);
            localStorage.setItem('daydayup_user', JSON.stringify({username:'testuser2'}));
        }""")
        await page.reload()
        await page.wait_for_selector('#auth-gate', state='hidden', timeout=10000)
        await page.locator('.tab[data-view="settings"]').click()
        await page.wait_for_timeout(800)
        await page.screenshot(path='D:/04_范伟/lifemgr-pwa/.workbuddy/test-settings.png')
        print('screenshot saved')

        # Verify new card present; old cards absent
        has_backup = await page.locator('h2:has-text("备份与同步")').count() > 0
        has_old_backup = await page.locator('h2:has-text("备份密钥")').count() > 0
        has_old_cloud = await page.locator('h2:has-text("加密备份")').count() > 0
        has_footer = await page.locator('footer:has-text("腾讯云自动备份")').count() > 0
        print('backup-sync card:', has_backup)
        print('old backup-key card:', has_old_backup)
        print('old encrypted-backup card:', has_old_cloud)
        print('footer text:', has_footer)
        assert has_backup and not has_old_backup and not has_old_cloud and has_footer, 'UI mismatch'
        print('SETTINGS UI OK')
        for m in msgs[-10:]:
            print('  ', m)
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
