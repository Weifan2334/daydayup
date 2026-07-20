# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for FastAPI backend.

构建：cd lifemgr-pwa && python scripts/build-backend.py
产物：dist-backend/backend/backend.exe (+ _internal/)
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # scripts/.. = lifemgr-pwa/

# ---- hidden imports for uvicorn / fastapi / pydantic / aiosqlite ----
hiddenimports = [
    # uvicorn core
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    # app modules (避免漏)
    "backend",
    "backend.__main__",
    "backend.main",
    "backend.models",
    "backend.db",
    "backend.services",
    "backend.services.crypto",
    "backend.services.sftp_client",
    "backend.services.cloud",
    "backend.services.auth",
    "backend.services.keygen",
    "backend.services.today",
    "backend.services.calendar",
    "backend.services.ai",
    "httpx",
    "httpx._types",
    "backend.data_sources",
    "aiosqlite",
    "anyio",
    "anyio._backends._asyncio",
    "starlette",
    "starlette.responses",
    "starlette.staticfiles",
    "starlette.middleware.cors",
    "multipart",
    "email_validator",
    # paramiko + crypto
    "paramiko",
    "paramiko.ssh_exception",
    "paramiko.transport",
    "paramiko.auth_handler",
    "paramiko.rsakey",
    "paramiko.ecdsakey",
    "paramiko.ed25519key",
    "paramiko.kex_curve25519",
    "paramiko.kex_ecdh_nist",
    "bcrypt",
    "nacl",
    "nacl.utils",
    "nacl.bindings",
]

# ---- 数据文件：frontend/ 整包（只读），data/ 不打包（运行时由 LIFEMGR_DATA_DIR 指定）----
datas = [
    (str(ROOT / "frontend"), "backend/frontend"),
]

a = Analysis(
    [str(ROOT / "backend" / "__main__.py")],
    pathex=[str(ROOT), str(ROOT / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6", "PyQt5", "PyQt6", "tkinter", "matplotlib", "numpy",
        "pandas", "scipy", "PIL", "cv2", "pytest",
        # v0.3.4: 进一步剔除未用标准库 / 工具链，减小 _internal 体积
        "unittest", "pydoc", "pydoc_data", "doctest", "distutils",
        "setuptools", "pip", "ensurepip", "lib2to3", "curses",
        "test", "turtledemo",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # 桌面端不弹黑窗
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",
)
