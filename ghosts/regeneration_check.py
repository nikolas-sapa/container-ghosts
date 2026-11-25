import argparse
from hashlib import sha256
from pathlib import Path

from ghosts.build_variants import build

TRACKED_DIRS = ("base", "reference", "variants")
TRACKED_FILES = ("build_manifest.json",)


def snapshot(root: Path) -> dict[str, str]:
    result = {}
    for dirname in TRACKED_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                result[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    for name in TRACKED_FILES:
        path = root / name
        if path.exists():
            result[name] = sha256(path.read_bytes()).hexdigest()
    return result


def check(root: Path) -> tuple[bool, list[str]]:
    before = snapshot(root)
    build(root)
    after = snapshot(root)
    errors = []
    for path in sorted(set(before) | set(after)):
        if before.get(path) != after.get(path):
            errors.append(path)
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path)
    args = parser.parse_args()
    ok, errors = check(args.artifacts)
    if not ok:
        print(f"REGENERATION_CHECK_FAIL: {len(errors)} files changed")
        for path in errors[:20]:
            print(" - " + path)
        return 1
    print("REGENERATION_CHECK_PASS: all tracked input/variant hashes regenerate deterministically")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
