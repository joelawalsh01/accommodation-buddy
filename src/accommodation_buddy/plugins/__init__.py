from pathlib import Path
import importlib

for f in Path(__file__).parent.glob("*.py"):
    if f.name != "__init__.py" and not f.name.startswith("_"):
        importlib.import_module(f".{f.stem}", package=__name__)
