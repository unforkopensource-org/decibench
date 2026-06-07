import pathlib, sys
# Resolve the project root (parent of this package's directory) and then the src/decibench package.
_project_root = pathlib.Path(__file__).resolve().parents[1]
_src_path = _project_root / "src" / "decibench"
if not _src_path.is_dir():
    raise RuntimeError(f"Source directory not found: {_src_path}")
# Ensure the src directory is on sys.path for imports.
if str(_project_root / "src") not in sys.path:
    sys.path.insert(0, str(_project_root / "src"))
# Extend this package's __path__ to include the source package.
__path__.append(str(_src_path))

# Re-export version from source package
from src.decibench import __version__
__all__ = ["__version__"]
