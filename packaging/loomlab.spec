# PyInstaller recipe for the one-file desktop app.
#
#   cd frontend && npm ci && npm run build      # the UI goes inside the app
#   pip install -r backend/requirements.txt -r packaging/requirements-build.txt
#   pyinstaller packaging/loomlab.spec          # -> dist/LoomLab-Studio(.exe)
#
# PyInstaller builds for the OS it runs on, so the Windows .exe is built on
# Windows (see .github/workflows/windows-app.yml).
import os
from PIL import Image, ImageDraw
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
UI = os.path.join(ROOT, 'frontend', 'dist')
if not os.path.isfile(os.path.join(UI, 'index.html')):
    raise SystemExit('frontend/dist is missing -- run "npm ci && npm run build" in frontend/ first.')

# App icon: the LoomLab "L" on amber, drawn here so no binary lives in the repo.
ICON = os.path.join(workpath, 'loomlab.ico')
os.makedirs(workpath, exist_ok=True)
art = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(art)
d.rounded_rectangle((8, 8, 248, 248), radius=36, fill=(228, 169, 56, 255))
d.rectangle((76, 52, 116, 204), fill=(28, 27, 22, 255))     # the L's stem
d.rectangle((76, 166, 184, 204), fill=(28, 27, 22, 255))    # and its foot
art.save(ICON, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

a = Analysis(
    [os.path.join(ROOT, 'backend', 'launcher.py')],
    pathex=[os.path.join(ROOT, 'backend')],
    datas=[(UI, 'ui')] + collect_data_files('psd_tools'),
    # uvicorn and psd-tools load parts of themselves by name at runtime
    hiddenimports=['app.main'] + collect_submodules('uvicorn') + collect_submodules('psd_tools'),
    excludes=['tkinter', 'matplotlib', 'IPython', 'pytest', 'httpx'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='LoomLab-Studio',
    icon=ICON,
    console=True,   # the window shows the address and closing it quits the app
    upx=False,
    debug=False,
    strip=False,
)
