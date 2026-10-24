"""Build code.zip from approved submission files while excluding data/secrets."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "code.zip"
SKIP_DIRS = {"dataset", ".venv", "venv", ".git", "node_modules", "__pycache__", ".cache", "cache", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIXES = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".bz2", ".xz", ".pyc", ".pyo", ".pem", ".p12", ".pfx", ".key"}
SECRET_NAME = re.compile(r"(^\.env($|\.)|secret|credential|token|private.?key|\.pem$|\.p12$|\.pfx$|\.key$)", re.I)
ALLOW_ROOT = {"README.md", "requirements.txt", "DECISIONS.md"}
PRIVATE_KEY_MARKER = b"-----BEGIN " + b"PRIVATE KEY-----"


def included_files() -> list[Path]:
    candidates: list[Path] = [ROOT / name for name in ALLOW_ROOT if (ROOT / name).is_file()]
    for dirname in ("code", "evaluation"):
        folder = ROOT / dirname
        if folder.exists():
            candidates.extend(path for path in folder.rglob("*") if path.is_file())
    result = []
    for path in candidates:
        relative = path.relative_to(ROOT)
        if any(part.casefold() in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        if path.suffix.casefold() in SKIP_SUFFIXES or SECRET_NAME.search(path.name):
            continue
        if path.resolve() == ARCHIVE.resolve():
            continue
        result.append(path)
    return sorted(set(result))


def main() -> None:
    files = included_files()
    for path in files:
        if PRIVATE_KEY_MARKER in path.read_bytes():
            raise SystemExit(f"Refusing to package possible private key in {path.relative_to(ROOT)}")
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    print(f"Created {ARCHIVE} with {len(files)} files; dataset, environments, caches, archives, and secret-like files excluded")


if __name__ == "__main__":
    main()
