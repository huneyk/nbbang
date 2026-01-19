# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Tour Expense macOS App
"""

import os
import sys

block_cipher = None

# 프로젝트 경로
project_path = os.path.dirname(os.path.abspath(SPEC))
backend_path = os.path.join(project_path, 'backend')
frontend_build_path = os.path.join(project_path, 'frontend', 'build')

# 숨겨진 임포트 (PyInstaller가 자동 감지하지 못하는 모듈들)
hidden_imports = [
    'flask',
    'flask_cors',
    'werkzeug',
    'jinja2',
    'markupsafe',
    'click',
    'itsdangerous',
    'dotenv',
    'PIL',
    'PIL.Image',
    'pytesseract',
    'openai',
    'pymongo',
    'openpyxl',
    'json',
    'datetime',
    'uuid',
    'io',
    'base64',
    'bson',
    'bson.objectid',
]

# 데이터 파일 (React 빌드 결과물 포함)
datas = [
    (frontend_build_path, 'static'),  # React 빌드 파일
    (os.path.join(backend_path, 'data'), 'data'),  # 데이터 폴더
]

# 바이너리 파일
binaries = []

a = Analysis(
    [os.path.join(backend_path, 'app_desktop.py')],
    pathex=[backend_path],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'numpy.testing',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TourExpense',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 앱이므로 콘솔 숨김
    disable_windowed_traceback=False,
    argv_emulation=True,  # macOS에서 필요
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TourExpense',
)

app = BUNDLE(
    coll,
    name='TourExpense.app',
    icon='resources/icon.icns',
    bundle_identifier='com.tourexpense.app',
    info_plist={
        'CFBundleName': 'TourExpense',
        'CFBundleDisplayName': '여행 경비 정산',
        'CFBundleGetInfoString': '여행 경비 정산 앱',
        'CFBundleIdentifier': 'com.tourexpense.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '10.15.0',
        'NSRequiresAquaSystemAppearance': False,  # 다크 모드 지원
    },
)
