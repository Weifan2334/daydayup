"""build-backend.py — PyInstaller 打包 FastAPI 后端为可独立运行的 .exe

输入：lifemgr-pwa/ 项目根
输出：lifemgr-pwa/dist-backend/backend/{backend.exe, _internal/...}
      frontend/ 被打包进 _internal/backend/frontend/（只读，OK）
      data/ 不打包 — 由 LIFEMGR_DATA_DIR 在运行时指定（需可写）
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist-backend"
SPEC = ROOT / "scripts" / "backend.spec"

if OUT.exists():
    shutil.rmtree(OUT, ignore_errors=True)

# --distpath 写到 dist-backend/，让 electron-builder 的 extraResources 直接指
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean",
    "--distpath", str(OUT),
    "--workpath", str(ROOT / "build-backend"),
    str(SPEC),
]
print("[build-backend]", " ".join(cmd))
res = subprocess.run(cmd, cwd=ROOT)
sys.exit(res.returncode)
