import os, sys, time, subprocess, shutil, threading, json
import httpx

EXE = r"D:\04_范伟\lifemgr-pwa\lifemgr-pwa\electron\release\win-unpacked\resources\backend\backend.exe"
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"
DATA_DIR = r"D:\04_范伟\lifemgr-pwa\lifemgr-pwa\electron\release\win-unpacked\resources\backend\_smoketest_data"
USER = f"smoke_{int(time.time())}"
PWD = "Smoke@1234"

def wait_up(timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(f"{BASE}/api/auth/me", timeout=2)
            if r.status_code in (401, 200):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False

def main():
    if os.path.isdir(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)

    env = dict(os.environ)
    env["LIFEMGR_PORT"] = str(PORT)
    env["LIFEMGR_DATA_DIR"] = DATA_DIR
    env["LIFEMGR_LOG_LEVEL"] = "warning"

    proc = subprocess.Popen([EXE], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[smoke] launched backend.exe pid={proc.pid}")
    try:
        if not wait_up():
            print("FAIL: backend did not come up")
            proc.terminate(); sys.exit(1)
        print("[smoke] backend up")

        with httpx.Client(base_url=BASE, timeout=10) as c:
            # register + login
            r = c.post("/api/auth/register", json={"username": USER, "password": PWD, "confirm_password": PWD})
            if r.status_code not in (200, 201):
                print("FAIL register:", r.status_code, r.text[:200]); proc.terminate(); sys.exit(1)
            token = r.json().get("token") or r.json().get("access_token")
            if not token:
                print("FAIL no token:", r.text[:200]); proc.terminate(); sys.exit(1)
            print(f"[smoke] registered+logged in user={USER}")

            H = {"Authorization": f"Bearer {token}"}
            date = "2026-07-15"
            # seed a record
            r = c.post("/api/actual_records", json={"date": date, "start_time": "08:00", "end_time": "09:00", "text": "smoke test"}, headers=H)
            print(f"[smoke] seed record status={r.status_code}")

            # concurrent GET — the exact scenario that 500'd before
            N = 25
            statuses = []
            errs = []
            def do_get():
                try:
                    rr = c.get(f"/api/actual_records?date={date}", headers=H)
                    statuses.append(rr.status_code)
                    if rr.status_code >= 500:
                        errs.append(rr.text[:200])
                except Exception as e:
                    errs.append(str(e))
            threads = [threading.Thread(target=do_get) for _ in range(N)]
            for t in threads: t.start()
            for t in threads: t.join()

            ok = sum(1 for s in statuses if s == 200)
            print(f"[smoke] concurrent GET results: total={len(statuses)} 200={ok} others={[s for s in statuses if s!=200]}")
            if errs:
                print("FAIL errors:", errs[:5])
                proc.terminate(); sys.exit(1)
            if ok == N:
                print("PASS: packaged backend served all concurrent requests with 200, no 500 (sqlite fix shipped)")
            else:
                print(f"WARN: only {ok}/{N} succeeded")
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
        if os.path.isdir(DATA_DIR):
            shutil.rmtree(DATA_DIR, ignore_errors=True)
        print("[smoke] cleaned up")

if __name__ == "__main__":
    main()
