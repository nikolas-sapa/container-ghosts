import argparse
import itertools
import json
import sys
from hashlib import sha256
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, features

from ghosts.jpegcodec import inventory as jpeg_inventory
from ghosts.jpegcodec import inventory_diff as jpeg_inventory_diff
from ghosts.pngcodec import encode_png
from ghosts.pngcodec import inventory as png_inventory
from ghosts.pngcodec import inventory_diff as png_inventory_diff

JPEG_GROUP = ["J0", "JC", "JA", "JXMP", "JCOM"]
PNG_CORE_GROUP = ["P0", "P1", "PT", "PTC", "PTA"]
JPEG_PROVENANCE_GROUP = ["JC", "JA"]


class InvarianceFailure(AssertionError):
    pass


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def decode_pillow(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        return np.asarray(im, dtype=np.uint8).copy()


def decode_opencv(path: Path) -> np.ndarray:
    encoded = np.fromfile(path, dtype=np.uint8)
    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None:
        raise InvarianceFailure(f"OpenCV failed to decode {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def raster_sha(arr: np.ndarray) -> str:
    return sha256(arr.tobytes()).hexdigest()


def assert_same_raster(a: np.ndarray, b: np.ndarray, label: str) -> None:
    if a.shape != b.shape:
        raise InvarianceFailure(f"{label}: shape mismatch {a.shape} vs {b.shape}")
    if not np.array_equal(a, b):
        mismatched = int(np.sum(np.any(a != b, axis=2)))
        raise InvarianceFailure(f"{label}: {mismatched} pixels differ")


def run_length_order(items: list[dict], key: str) -> list[list]:
    out = []
    for item in items:
        value = item["type"] if key == "type" else item["name"]
        if out and out[-1][0] == value:
            out[-1][1] += 1
        else:
            out.append([value, 1])
    return out


def compact_png_inventory(inv: dict) -> dict:
    return {
        "counts": inv["counts"],
        "payload_lengths": inv["payload_lengths"],
        "order_rle": run_length_order(inv["chunks"], "type"),
        "ihdr": inv["ihdr"],
        "idat_count": inv["idat_count"],
        "idat_contiguous": inv["idat_contiguous"],
        "idat_compressed_sha256": inv["idat_compressed_sha256"],
        "forbidden_present": inv["forbidden_present"],
    }


def compact_jpeg_inventory(inv: dict) -> dict:
    return {
        "counts": inv["counts"],
        "payload_lengths": inv["payload_lengths"],
        "order_rle": run_length_order(inv["segments"], "name"),
        "scan_sha256": inv["scan_sha256"],
        "scan_length": inv["scan_length"],
        "dqt_sha256": inv["dqt_sha256"],
        "dht_sha256": inv["dht_sha256"],
        "sof_sha256": inv["sof_sha256"],
        "progressive": inv["progressive"],
        "restart_segments": inv["restart_segments"],
        "app2_icc_present": inv["app2_icc_present"],
        "app14_adobe_present": inv["app14_adobe_present"],
        "exif_orientation_present": inv["exif_orientation_present"],
        "exif_thumbnail_present": inv["exif_thumbnail_present"],
    }


def verify_pairwise(results: dict, arrays: dict, image_id: str, failures: list[str]) -> dict:
    names = sorted(results)
    pillow_pairs = 0
    png_cv_pairs = 0
    jpeg_cv_pairs = 0
    mismatches = []
    for a, b in itertools.combinations(names, 2):
        pillow_pairs += 1
        if not np.array_equal(arrays[a]["pillow"], arrays[b]["pillow"]):
            mismatches.append(f"{image_id} Pillow {a}/{b}")
        same_format = results[a]["format"] == results[b]["format"]
        if same_format and results[a]["format"] == "png":
            png_cv_pairs += 1
            if not np.array_equal(arrays[a]["opencv"], arrays[b]["opencv"]):
                mismatches.append(f"{image_id} OpenCV-PNG {a}/{b}")
        if a in JPEG_GROUP and b in JPEG_GROUP:
            jpeg_cv_pairs += 1
            if not np.array_equal(arrays[a]["opencv"], arrays[b]["opencv"]):
                mismatches.append(f"{image_id} OpenCV-JPEG {a}/{b}")
    if mismatches:
        failures.extend(mismatches)
    return {
        "pillow_pairs_compared": pillow_pairs,
        "png_opencv_pairs_compared": png_cv_pairs,
        "jpeg_opencv_pairs_compared": jpeg_cv_pairs,
        "mismatch_count": len(mismatches),
    }


def verify_image(image: dict, root: Path) -> tuple[dict, list[str]]:
    failures = []
    results = {}
    arrays = {}
    for name, meta in sorted(image["variants"].items()):
        path = root / meta["path"]
        data = path.read_bytes()
        file_sha = sha256_bytes(data)
        if file_sha != meta["sha256"]:
            failures.append(f"{image['image_id']} {name}: file sha differs from build manifest")
        if len(data) != meta["byte_length"]:
            failures.append(f"{image['image_id']} {name}: byte length differs from build manifest")
        try:
            pillow_arr = decode_pillow(path)
            cv_arr = decode_opencv(path)
        except Exception as exc:
            failures.append(f"{image['image_id']} {name}: decode failure {exc}")
            continue
        if meta["format"] == "png":
            inv = png_inventory(data)
            compact = compact_png_inventory(inv)
            diff = None
            critical = {
                "forbidden_present": inv["forbidden_present"],
                "idat_contiguous": inv["idat_contiguous"],
            }
            if inv["forbidden_present"]:
                failures.append(f"{image['image_id']} {name}: forbidden PNG chunks {inv['forbidden_present']}")
            if not inv["idat_contiguous"]:
                failures.append(f"{image['image_id']} {name}: non-contiguous IDAT sequence")
        else:
            inv = jpeg_inventory(data)
            compact = compact_jpeg_inventory(inv)
            diff = None
            critical = {
                "scan_sha256": inv["scan_sha256"],
                "dqt_sha256": inv["dqt_sha256"],
                "dht_sha256": inv["dht_sha256"],
                "sof_sha256": inv["sof_sha256"],
            }
            forbidden_hit = (
                inv["progressive"] or inv["restart_segments"] or inv["app2_icc_present"]
                or inv["app14_adobe_present"] or inv["exif_orientation_present"]
                or inv["exif_thumbnail_present"]
            )
            if forbidden_hit:
                failures.append(f"{image['image_id']} {name}: forbidden JPEG rendering/structure metadata present")
        arrays[name] = {"pillow": pillow_arr, "opencv": cv_arr}
        results[name] = {
            "path": meta["path"],
            "format": meta["format"],
            "file_sha256": file_sha,
            "byte_length": len(data),
            "pillow_raster_sha256": raster_sha(pillow_arr),
            "opencv_raster_sha256": raster_sha(cv_arr),
            "pillow_opencv_identical": bool(np.array_equal(pillow_arr, cv_arr)),
            "shape": list(pillow_arr.shape),
            "inventory": compact,
            "critical": critical,
            "inventory_diff_vs_baseline": diff,
            "length_control_group": meta.get("length_control_group"),
            "byte_length_factor": meta.get("byte_length_factor"),
        }
    if not results:
        return {"variants": results}, failures

    for name, result in results.items():
        data = (root / result["path"]).read_bytes()
        if result["format"] == "png":
            base_data = (root / results["P0"]["path"]).read_bytes()
            result["inventory_diff_vs_baseline"] = png_inventory_diff(png_inventory(base_data), png_inventory(data))
        else:
            base_data = (root / results["J0"]["path"]).read_bytes()
            result["inventory_diff_vs_baseline"] = jpeg_inventory_diff(jpeg_inventory(base_data), jpeg_inventory(data))

    canary = image["canary"].encode("ascii")
    for name in ("PT", "PTC", "PTA", "JC", "JA", "JXMP", "JCOM"):
        if name in results and canary not in (root / results[name]["path"]).read_bytes():
            failures.append(f"{image['image_id']} {name}: expected canary bytes missing")
    semantic_markers = {
        "JC": b"Canon", "PTC": b"Canon",
        "JA": b"trainedAlgorithmicMedia", "PTA": b"trainedAlgorithmicMedia",
    }
    for name, marker in semantic_markers.items():
        if name in results and marker not in (root / results[name]["path"]).read_bytes():
            failures.append(f"{image['image_id']} {name}: expected provenance marker missing")

    hashes = {}
    for name, result in results.items():
        hashes.setdefault(result["file_sha256"], []).append(name)
    for digest, names in hashes.items():
        if len(names) > 1:
            failures.append(f"{image['image_id']}: duplicate file sha256 across {names}")

    canonical = results["J0"]["pillow_raster_sha256"]
    if canonical != image["canonical_raster_sha256"]:
        failures.append(f"{image['image_id']}: J0 Pillow raster differs from build canonical raster")
    for name, result in results.items():
        if result["pillow_raster_sha256"] != canonical:
            failures.append(f"{image['image_id']} {name}: Pillow raster hash mismatch")
        if result["format"] == "png" and result["opencv_raster_sha256"] != canonical:
            failures.append(f"{image['image_id']} {name}: OpenCV PNG raster differs from canonical")

    png_ihdr = {name: r["inventory"]["ihdr"]["sha256"] for name, r in results.items() if r["format"] == "png"}
    if len(set(png_ihdr.values())) != 1:
        failures.append(f"{image['image_id']}: PNG IHDR mismatch")
    for name in ("PT", "PTC", "PTA"):
        if name in results and results[name]["inventory"]["idat_compressed_sha256"] != results["P0"]["inventory"]["idat_compressed_sha256"]:
            failures.append(f"{image['image_id']} {name}: metadata insertion changed compressed IDAT bytes")

    jpeg_critical_fields = ["scan_sha256", "dqt_sha256", "dht_sha256", "sof_sha256"]
    for field in jpeg_critical_fields:
        values = {name: results[name]["inventory"][field] for name in JPEG_GROUP if name in results}
        if len(set(values.values())) != 1:
            failures.append(f"{image['image_id']}: JPEG critical {field} mismatch")

    pair_summary = verify_pairwise(results, arrays, image["image_id"], failures)
    group_deltas = {}
    for group, names in {"png_core_exact": PNG_CORE_GROUP, "jpeg_provenance_exact": JPEG_PROVENANCE_GROUP}.items():
        lengths = [results[n]["byte_length"] for n in names]
        group_deltas[group] = max(lengths) - min(lengths)
        if group_deltas[group] != 0:
            failures.append(f"{image['image_id']}: {group} byte-length delta {group_deltas[group]}")

    return {
        "variants": results,
        "pairwise": pair_summary,
        "group_byte_length_deltas": group_deltas,
    }, failures


def mutation_test(root: Path) -> dict:
    manifest = json.loads((root / "build_manifest.json").read_text())
    image = manifest["images"][0]
    p0 = root / image["variants"]["P0"]["path"]
    arr = decode_pillow(p0)
    mutated = arr.copy()
    mutated[0, 0, 0] ^= 1
    mutation_dir = root / "mutation"
    mutation_dir.mkdir(parents=True, exist_ok=True)
    mutated_path = mutation_dir / "one_pixel_mutated.png"
    mutated_path.write_bytes(encode_png(mutated, compress_level=6, filter_type=0))
    catches = {}
    for decoder_name, decoder in {"pillow": decode_pillow, "opencv": decode_opencv}.items():
        mutated_arr = decoder(mutated_path)
        try:
            assert_same_raster(arr, mutated_arr, "one-pixel mutation")
            catches[decoder_name] = False
        except InvarianceFailure as exc:
            catches[decoder_name] = str(exc)
    if not all(catches.values()):
        raise InvarianceFailure("mutation self-test failed: verifier accepted a one-pixel mutation")
    return {
        "status": "MUTATION_TEST_PASS",
        "mutated_file": mutated_path.relative_to(root).as_posix(),
        "mutated_pixel_xy": [0, 0],
        "decoder_catches": catches,
    }


def verify(root: Path, run_mutation: bool = False) -> tuple[dict, list[str]]:
    build_manifest = json.loads((root / "build_manifest.json").read_text())
    failures = []
    images = {}
    totals = {"pillow_pairs_compared": 0, "png_opencv_pairs_compared": 0, "jpeg_opencv_pairs_compared": 0}
    for image in build_manifest["images"]:
        result, image_failures = verify_image(image, root)
        images[image["image_id"]] = result
        failures.extend(image_failures)
        for key in totals:
            totals[key] += result["pairwise"][key]
    report = {
        "schema": "container-ghosts.verification-manifest.v1",
        "status": "pass" if not failures else "fail",
        "decode_paths": {
            "pinned": f"Pillow {Image.__version__} Image.open RGB conversion",
            "second": f"OpenCV {cv2.__version__} cv2.imdecode(IMREAD_COLOR) + BGR-to-RGB",
            "jpeg_note": "JPEG is fixed-decoder invariance; scan/DQT/DHT/SOF byte identity is the cross-variant container guarantee. Cross-decoder equality is recorded but not assumed.",
            "pillow_jpeg_features": {
                "jpg": features.check("jpg"),
                "libjpeg_turbo": features.check("libjpeg_turbo"),
                "libjpeg_turbo_version": features.version("libjpeg_turbo"),
            },
        },
        "pairwise_totals": totals,
        "images": images,
        "failures": failures,
    }
    if run_mutation:
        report["mutation_test"] = mutation_test(root)
    out = root / "verification_manifest.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--mutation-test", action="store_true")
    args = parser.parse_args()
    report, failures = verify(args.artifacts, args.mutation_test)
    if args.mutation_test:
        print(report["mutation_test"]["status"] + ": verifier rejected a one-pixel mutation under Pillow and OpenCV")
    if failures:
        print(f"VERIFY_REAL: FAIL ({len(failures)} invariance failures)", file=sys.stderr)
        for failure in failures[:20]:
            print(" - " + failure, file=sys.stderr)
        return 1
    print("VERIFY_REAL: PASS all raster/container invariance checks")
    print(f"verification manifest: {args.artifacts / 'verification_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
