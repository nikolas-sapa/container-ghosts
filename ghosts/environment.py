import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

DIRECT_DEPENDENCIES = ["pillow", "numpy", "opencv-python-headless", "scipy", "pytest", "piexif"]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def distribution_tree_hash(dist_name: str) -> str:
    dist = importlib.metadata.distribution(dist_name)
    h = hashlib.sha256()
    files = sorted(str(p) for p in (dist.files or []))
    for rel in files:
        path = Path(dist.locate_file(rel))
        if not path.is_file() or path.is_symlink():
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        h.update(file_hash(path).encode("ascii"))
        h.update(b"\x00")
    return h.hexdigest()


def write_environment(repo: Path) -> dict:
    requirements = (repo / "requirements.txt").read_bytes()
    dependencies = {}
    for name in DIRECT_DEPENDENCIES:
        dependencies[name] = {
            "version": importlib.metadata.version(name),
            "installed_tree_sha256": distribution_tree_hash(name),
        }
    env = {
        "schema": "container-ghosts.environment.v1",
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "requirements_txt_sha256": hashlib.sha256(requirements).hexdigest(),
        "dependencies": dependencies,
    }
    (repo / "environment.json").write_text(json.dumps(env, indent=2, sort_keys=True) + "\n")
    return env


if __name__ == "__main__":
    write_environment(Path(__file__).resolve().parents[1])
    print("wrote environment.json")
