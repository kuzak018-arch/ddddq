# PyInstaller spec for the bundled backend: python -m PyInstaller backend/drafter-backend.spec
# Output: build/backend/dist/drafter-backend/ (one folder: faster start than a single exe).
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
DATA = ROOT / "data"

datas = [(str(ROOT / "shared"), "shared")]
# seed data for a fresh install: constants, hero/item icons, the trained model, Stratz builds
for name in ("constants", "icons", "model", "stratz"):
    src = DATA / name
    if not src.exists():
        raise SystemExit(f"нет {src}: сначала обнови данные (drafter.cli constants/train/stratz)")
    datas.append((str(src), f"seed/{name}"))

binaries, hiddenimports = [], []
for pkg in ("lightgbm", "windows_capture", "duckdb", "polars"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("uvicorn") + collect_submodules("drafter") + [
    "sklearn.linear_model", "sklearn.metrics", "scipy.special", "scipy.sparse",
]

a = Analysis(
    [str(ROOT / "backend" / "run_backend.py")],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "PyInstaller"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="drafter-backend", console=False,
          icon=str(ROOT / "app" / "src-tauri" / "icons" / "icon.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="drafter-backend")
