import argparse
import base64
import json
import random
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

CORE_VARIANTS = ["J0", "P0", "P1", "PT", "JC", "JA"]
RESPONSE_GRAMMAR = re.compile(r"^[AB],[AB],[AB]$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def rng_for(seed: str) -> random.Random:
    return random.Random(int.from_bytes(sha256(seed.encode("utf-8")).digest()[:8], "big"))


def palindromic_schedule(seed: str, variants: list[str] | None = None) -> list[str]:
    variants = list(variants or CORE_VARIANTS)
    if len(variants) != 6 or "JC" not in variants or "JA" not in variants:
        raise ValueError("the core scheduler expects six variants including JC and JA")
    rng = rng_for(seed)
    first = [None] * 6
    pair = ["JC", "JA"]
    rng.shuffle(pair)
    start = rng.randrange(5)
    first[start], first[start + 1] = pair
    rest = [v for v in variants if v not in {"JC", "JA"}]
    rng.shuffle(rest)
    rest_iter = iter(rest)
    first = [next(rest_iter) if v is None else v for v in first]
    return first + first[::-1]


def exact_repeat_schedule(variant: str = "J0", repetitions: int = 4) -> list[str]:
    return [variant] * repetitions


def validate_schedule(sequence: list[str]) -> list[str]:
    errors = []
    if len(sequence) != 12:
        errors.append("ABBA sequence length is not 12")
    elif sequence != sequence[::-1]:
        errors.append("sequence is not palindromic")
    first = sequence[:6]
    if not ({"JC", "JA"}.issubset(first) and abs(first.index("JC") - first.index("JA")) == 1):
        errors.append("JC/JA are not adjacent in the first half")
    for variant in set(sequence):
        positions = [i for i, v in enumerate(sequence) if v == variant]
        if len(positions) != 2 or sum(positions) != len(sequence) - 1:
            errors.append(f"{variant} does not occur exactly twice in mirrored positions")
    return errors


def option_mappings(image: dict) -> dict:
    rng = rng_for("options:" + image["image_id"])
    labels = image["probe_labels"]
    q1_wrong = "one object" if labels["q1"] == "count" else "a neutral gray field"
    q1 = [labels["count_or_color_answer"], q1_wrong]
    q2 = [labels["caption_correct"], labels["caption_wrong"]]
    q3 = ["camera photograph", "AI-generated image"]
    rng.shuffle(q1)
    rng.shuffle(q2)
    rng.shuffle(q3)
    return {"q1": {"A": q1[0], "B": q1[1]}, "q2": {"A": q2[0], "B": q2[1]}, "q3": {"A": q3[0], "B": q3[1]}}


def prompt_for(image: dict, nonce: str) -> str:
    mapping = option_mappings(image)
    return f"""Nonce: {nonce}
Answer the three independent questions about the image. Return exactly three letters separated by commas and nothing else.
1. Which count-or-color description is more accurate? A: {mapping['q1']['A']} B: {mapping['q1']['B']}
2. Which caption is more accurate? A: {mapping['q2']['A']} B: {mapping['q2']['B']}
3. Does this image appear to be a camera photograph or AI-generated? A: {mapping['q3']['A']} B: {mapping['q3']['B']}"""


def nonce_for(seed: str, sequence_index: int) -> str:
    return "GHOSTNONCE_" + sha256_bytes(f"{seed}|{sequence_index}".encode())[:16].upper()


def endpoint_payload(endpoint: dict, image_bytes: bytes, mime_type: str, prompt: str) -> dict:
    if not isinstance(image_bytes, bytes):
        raise TypeError("image payload must be raw bytes, never a PIL object")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    name = endpoint["name"]
    if endpoint.get("api_shape") == "openai_compatible_chat_completions":
        body = {"model": endpoint["model_snapshot"], "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
        ]}], "temperature": endpoint["temperature"], "max_tokens": endpoint["max_output_tokens"]}
    elif name == "openai":
        body = {"model": endpoint["model_snapshot"], "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": f"data:{mime_type};base64,{encoded}"},
        ]}], "temperature": endpoint["temperature"], "max_output_tokens": endpoint["max_output_tokens"]}
    elif name == "anthropic":
        body = {"model": endpoint["model_snapshot"], "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": encoded}},
        ]}], "temperature": endpoint["temperature"], "max_tokens": endpoint["max_output_tokens"]}
    elif name == "google":
        body = {"model": endpoint["model_snapshot"], "contents": [{"parts": [
            {"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": encoded}},
        ]}], "generationConfig": {"temperature": endpoint["temperature"], "maxOutputTokens": endpoint["max_output_tokens"]}}
    else:
        raise ValueError(f"unknown endpoint {name}")
    return {"image_bytes": image_bytes, "provider_payload": body, "base64_sha256": sha256_bytes(encoded.encode("ascii"))}


class MockEndpoint:
    def __init__(self, definition: dict):
        self.definition = definition

    def call(self, prepared: dict) -> dict:
        if not isinstance(prepared["image_bytes"], bytes):
            raise TypeError("mock endpoint received non-bytes image input")
        return {
            "text": "A,B,A",
            "model_snapshot": self.definition["model_snapshot"],
            "usage": {"input_tokens": 0, "output_tokens": 5},
        }


def prepare_call(endpoint: dict, variant_path: Path, prompt: str) -> dict:
    image_bytes = variant_path.read_bytes()
    mime_type = "image/png" if variant_path.suffix.lower() == ".png" else "image/jpeg"
    return endpoint_payload(endpoint, image_bytes, mime_type, prompt)


def validate_records(records: list[dict], manifest: dict) -> list[str]:
    errors = []
    if len({r["nonce"] for r in records}) != len(records):
        errors.append("nonces are not unique")
    if any(r["raw_bytes_type"] != "bytes" for r in records):
        errors.append("a call was not prepared from raw bytes")
    if any(not RESPONSE_GRAMMAR.match(r["response_text"]) for r in records):
        errors.append("mock response outside exact grammar")
    time_values = [datetime.fromisoformat(r["utc"].replace("Z", "+00:00")) for r in records]
    if any(b < a for a, b in zip(time_values, time_values[1:])):
        errors.append("UTC timestamps decreased")
    image_by_id = {im["image_id"]: im for im in manifest["images"]}
    groups = {}
    for record in records:
        groups.setdefault((record["endpoint"], record["mode"], record["image_id"]), []).append(record)
        want = image_by_id[record["image_id"]]["variants"][record["variant"]]["sha256"]
        if record["image_sha256"] != want:
            errors.append(f"transmitted hash mismatch for {record['image_id']} {record['variant']}")
    for (endpoint, mode, image_id), rows in groups.items():
        rows.sort(key=lambda r: r["sequence_index"])
        sequence = [r["variant"] for r in rows]
        if mode == "abba":
            errors.extend(f"{endpoint}/{image_id}: {e}" for e in validate_schedule(sequence))
        elif mode == "exact-repeat" and len(set(sequence)) != 1:
            errors.append(f"{endpoint}/{image_id}: exact-repeat mode mixed variants")
    return errors


def dry_run(artifacts: Path, out_dir: Path, config_path: Path) -> dict:
    manifest = json.loads((artifacts / "build_manifest.json").read_text())
    endpoints = json.loads(config_path.read_text())["endpoints"]
    image = manifest["images"][0]
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "probe_dryrun.jsonl"
    records = []
    with log_path.open("w") as log:
        for endpoint in endpoints:
            mock = MockEndpoint(endpoint)
            for mode in ("abba", "exact-repeat"):
                seed = f"dryrun|{endpoint['name']}|{mode}|{image['image_id']}"
                sequence = palindromic_schedule(seed) if mode == "abba" else exact_repeat_schedule()
                seen = {}
                for index, variant in enumerate(sequence):
                    seen[variant] = seen.get(variant, 0) + 1
                    nonce = nonce_for(seed, index)
                    prompt = prompt_for(image, nonce)
                    path = artifacts / image["variants"][variant]["path"]
                    prepared = prepare_call(endpoint, path, prompt)
                    response = mock.call(prepared)
                    record = {
                        "utc": utc_now(),
                        "endpoint": endpoint["name"],
                        "model_snapshot": response["model_snapshot"],
                        "mode": mode,
                        "image_id": image["image_id"],
                        "variant": variant,
                        "occurrence": seen[variant],
                        "sequence_index": index,
                        "nonce": nonce,
                        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
                        "option_mappings": option_mappings(image),
                        "request_parameters": {
                            "temperature": endpoint["temperature"],
                            "max_output_tokens": endpoint["max_output_tokens"],
                        },
                        "image_sha256": sha256_bytes(prepared["image_bytes"]),
                        "image_byte_length": len(prepared["image_bytes"]),
                        "base64_sha256": prepared["base64_sha256"],
                        "provider_payload_sha256": sha256_bytes(json.dumps(prepared["provider_payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")),
                        "raw_bytes_type": type(prepared["image_bytes"]).__name__,
                        "transport": endpoint["transport"],
                        "response_text": response["text"],
                        "response_sha256": sha256_bytes(response["text"].encode("utf-8")),
                    }
                    log.write(json.dumps(record, sort_keys=True) + "\n")
                    records.append(record)
    errors = validate_records(records, manifest)
    report = {
        "status": "pass" if not errors else "fail",
        "calls": len(records),
        "log_path": str(log_path),
        "validation_errors": errors,
        "live_calls": 0,
    }
    (out_dir / "dryrun_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/dryrun"))
    parser.add_argument("--config", type=Path, default=Path("configs/endpoints.json"))
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    report = dry_run(args.artifacts, args.out, args.config)
    print(f"probe dry-run {report['status']}: {report['calls']} mock calls, live_calls=0")
    if report["validation_errors"]:
        for error in report["validation_errors"][:20]:
            print(" - " + error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
