import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from ghosts.cost_ledger import CostCapAbort, CostLedger, usd_string
from ghosts.openai_compatible import OpenAICompatibleChatEndpoint
from ghosts.probe_harness import (
    exact_repeat_schedule,
    nonce_for,
    option_mappings,
    palindromic_schedule,
    prepare_call,
    prompt_for,
    sha256_bytes,
    validate_schedule,
)
from ghosts.score import canary_leaks, parse_three_letters, semantic_answers

PROVENANCE_MARKERS = [
    "Canon EOS R6",
    "RF24-105mm",
    "ComfyUI",
    "FLUX.1-schnell",
    "trainedAlgorithmicMedia",
    "digitalCapture",
    "flux1-schnell-fixture",
]
EXPECTED_RESPONSE_FIELDS = {"id", "object", "created", "model", "choices", "usage", "system_fingerprint"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: dict | list) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(data)
    return sha256_bytes(data)


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def safe_fragment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)


def image_for(manifest: dict, image_id: str) -> dict:
    matches = [image for image in manifest["images"] if image["image_id"] == image_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one image named {image_id}")
    return matches[0]


def add_plan_item(items: list[dict], *, image: dict, seed: str, mode: str, phase: str, variant: str, sequence_index: int, occurrence: int) -> None:
    nonce = nonce_for(seed, sequence_index)
    prompt = prompt_for(image, nonce)
    items.append({
        "call_id": f"{mode}-{sequence_index:03d}" if mode != "abba" else f"core-{sequence_index:03d}",
        "phase": phase,
        "mode": mode,
        "seed": seed,
        "image_id": image["image_id"],
        "variant": variant,
        "occurrence": occurrence,
        "sequence_index": sequence_index,
        "global_sequence_index": len(items),
        "nonce": nonce,
        "prompt": prompt,
        "prompt_sha256": sha256_bytes(prompt.encode("utf-8")),
        "option_mappings": option_mappings(image),
    })


def build_plan(config: dict, manifest: dict) -> dict:
    image = image_for(manifest, config["image_id"])
    items = []
    core_seed = config["core_seed"]
    sequence = palindromic_schedule(core_seed)
    schedule_errors = validate_schedule(sequence)
    if schedule_errors:
        raise ValueError("core smoke schedule is invalid: " + "; ".join(schedule_errors))
    seen = {}
    for index, variant in enumerate(sequence):
        seen[variant] = seen.get(variant, 0) + 1
        add_plan_item(
            items, image=image, seed=core_seed, mode="abba", phase="core_abba",
            variant=variant, sequence_index=index, occurrence=seen[variant],
        )
    for control in config["exact_repeat_controls"]:
        seed = control["seed"]
        control_sequence = exact_repeat_schedule(control["variant"], control["repetitions"])
        seen = {}
        for index, variant in enumerate(control_sequence):
            seen[variant] = seen.get(variant, 0) + 1
            add_plan_item(
                items, image=image, seed=seed, mode=control["control_id"], phase="exact_repeat_control",
                variant=variant, sequence_index=index, occurrence=seen[variant],
            )
    return {
        "schema": "container-ghosts.vyce-smoke-plan.v1",
        "scientific_status": config["scientific_status"],
        "image_id": image["image_id"],
        "image_canary": image["canary"],
        "planned_calls": len(items),
        "core_sequence": sequence,
        "exact_repeat_controls": config["exact_repeat_controls"],
        "items": items,
    }


def ledger_from_config(config: dict, out: Path) -> CostLedger:
    cost = config["cost"]
    return CostLedger(
        out / "cost_ledger.jsonl",
        cost["hard_cap_usd"],
        cost["assumed_input_price_per_million_usd"],
        cost["assumed_output_price_per_million_usd"],
    )


def token_accounting(result: dict, request_body: bytes, max_output_tokens: int, ledger: CostLedger) -> dict:
    usage = result["usage"]
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if isinstance(input_tokens, int) and isinstance(output_tokens, int) and input_tokens >= 0 and output_tokens >= 0:
        return {"input_tokens": input_tokens, "output_tokens": output_tokens, "usage_source": "api_usage"}
    return {
        "input_tokens": ledger.conservative_input_tokens(request_body),
        "output_tokens": max_output_tokens,
        "usage_source": "conservative_transport_bytes_upper_bound",
    }


def capability_assessment(record: dict, image: dict) -> dict:
    letters = parse_three_letters(record["response_text"])
    semantics = semantic_answers(record["response_text"], record["option_mappings"]) if letters else None
    labels = image["probe_labels"]
    q1_correct = bool(semantics and semantics["q1"] == labels["count_or_color_answer"])
    q2_correct = bool(semantics and semantics["q2"] == labels["caption_correct"])
    return {
        "call_id": record["call_id"],
        "http_status": record["http_status"],
        "http_success": record["http_status"] == 200,
        "nonempty_text": bool(record["response_text"]),
        "exact_grammar": letters is not None,
        "q1_semantically_correct": q1_correct,
        "q2_semantically_correct": q2_correct,
        "semantic_content_correct_count": int(q1_correct) + int(q2_correct),
        "interpretation": "HTTP 200 means the relay accepted the inline image payload shape; semantic correctness is descriptive evidence about vision behavior, not proof by itself",
    }


def raw_paths(out: Path, item: dict) -> tuple[Path, Path]:
    fragment = f"{item['global_sequence_index']:04d}_{safe_fragment(item['call_id'])}"
    return out / "raw" / f"{fragment}_request.json", out / "raw" / f"{fragment}_response.json"


def prepared_for_item(endpoint_definition: dict, artifacts: Path, image: dict, item: dict) -> dict:
    path = artifacts / image["variants"][item["variant"]]["path"]
    return prepare_call(endpoint_definition, path, item["prompt"])


def batches(items: list[dict]) -> list[tuple[str, list[dict]]]:
    grouped = []
    for item in items:
        if not grouped or grouped[-1][0] != item["phase"]:
            grouped.append((item["phase"], [item]))
        else:
            grouped[-1][1].append(item)
    return grouped


def write_state(out: Path, state: dict) -> None:
    write_json(out / "run_state.json", state)


def execute_smoke(config_path: Path, artifacts: Path, out: Path, max_calls: int | None = None) -> dict:
    config = read_json(config_path)
    manifest = read_json(artifacts / "build_manifest.json")
    image = image_for(manifest, config["image_id"])
    endpoint_definition = dict(config["endpoint"])
    endpoint = OpenAICompatibleChatEndpoint(endpoint_definition)
    ledger = ledger_from_config(config, out)
    plan = build_plan(config, manifest)
    plan["config_sha256"] = sha256_bytes((config_path).read_bytes())
    plan_hash = write_json(out / "smoke_plan.json", plan)
    records_path = out / "records.jsonl"
    existing_records = read_jsonl(records_path)
    completed_ids = {record["call_id"] for record in existing_records}
    ledger_errors = ledger.verify()
    if ledger_errors:
        raise ValueError("cost ledger failed validation before live execution: " + "; ".join(ledger_errors))

    executed = 0
    stop_status = "complete"
    stop_detail = None
    try:
        for phase, phase_items in batches(plan["items"]):
            remaining_phase = [item for item in phase_items if item["call_id"] not in completed_ids]
            if not remaining_phase:
                continue
            if max_calls is not None and executed >= max_calls:
                stop_status = "partial"
                stop_detail = "max_calls reached"
                break
            projected_batch = 0
            for item in remaining_phase:
                prepared = prepared_for_item(endpoint_definition, artifacts, image, item)
                projected_batch += ledger.projected_cost(endpoint.request_body_bytes(prepared), endpoint_definition["max_output_tokens"])
            ledger.check_cap(projected_batch, f"batch:{phase}")
            for item in phase_items:
                if item["call_id"] in completed_ids:
                    continue
                if max_calls is not None and executed >= max_calls:
                    stop_status = "partial"
                    stop_detail = "max_calls reached"
                    break
                prepared = prepared_for_item(endpoint_definition, artifacts, image, item)
                request_body = endpoint.request_body_bytes(prepared)
                projected = ledger.projected_cost(request_body, endpoint_definition["max_output_tokens"])
                ledger.check_cap(projected, item["call_id"])
                request_path, response_path = raw_paths(out, item)
                request_path.parent.mkdir(parents=True, exist_ok=True)
                request_path.write_bytes(request_body)
                result = endpoint.call(prepared)
                response_path.write_bytes(result["response_body"])
                if result["request_sha256"] != sha256_bytes(request_path.read_bytes()):
                    raise RuntimeError("transmitted request hash differs from archived request bytes")
                accounting = token_accounting(result, request_body, endpoint_definition["max_output_tokens"], ledger)
                ledger_entry = ledger.append_call(
                    call_id=item["call_id"],
                    phase=item["phase"],
                    model=result["model_snapshot"] or endpoint_definition["model_snapshot"],
                    input_tokens=accounting["input_tokens"],
                    output_tokens=accounting["output_tokens"],
                    usage_source=accounting["usage_source"],
                    http_status=result["http_status"],
                    request_sha256=result["request_sha256"],
                    response_sha256=result["response_sha256"],
                )
                record = {
                    "schema": "container-ghosts.vyce-smoke-record.v1",
                    "scientific_status": config["scientific_status"],
                    "utc": result["finished_utc"],
                    "started_utc": result["started_utc"],
                    "finished_utc": result["finished_utc"],
                    "endpoint": endpoint_definition["name"],
                    "requested_model": endpoint_definition["model_snapshot"],
                    "served_model": result["model_snapshot"],
                    "system_fingerprint": result["system_fingerprint"],
                    "call_id": item["call_id"],
                    "phase": item["phase"],
                    "mode": item["mode"],
                    "image_id": item["image_id"],
                    "variant": item["variant"],
                    "occurrence": item["occurrence"],
                    "sequence_index": item["sequence_index"],
                    "global_sequence_index": item["global_sequence_index"],
                    "nonce": item["nonce"],
                    "prompt_sha256": item["prompt_sha256"],
                    "option_mappings": item["option_mappings"],
                    "request_parameters": {
                        "temperature": endpoint_definition["temperature"],
                        "max_output_tokens": endpoint_definition["max_output_tokens"],
                    },
                    "image_sha256": sha256_bytes(prepared["image_bytes"]),
                    "image_byte_length": len(prepared["image_bytes"]),
                    "base64_sha256": prepared["base64_sha256"],
                    "provider_payload_sha256": sha256_bytes(request_body),
                    "raw_bytes_type": type(prepared["image_bytes"]).__name__,
                    "transport": endpoint_definition["transport"],
                    "raw_request_path": request_path.relative_to(out).as_posix(),
                    "raw_request_sha256": sha256_bytes(request_path.read_bytes()),
                    "raw_response_path": response_path.relative_to(out).as_posix(),
                    "raw_response_sha256": result["response_sha256"],
                    "response_text": result["text"],
                    "response_text_sha256": sha256_bytes(result["text"].encode("utf-8")),
                    "http_status": result["http_status"],
                    "response_headers": result["headers"],
                    "transport_error": result["transport_error"],
                    "json_error": result["json_error"],
                    "finish_reason": result["finish_reason"],
                    "refusal": result["refusal"],
                    "latency_ms": result["latency_ms"],
                    "usage": result["usage"],
                    "ledgered_input_tokens": accounting["input_tokens"],
                    "ledgered_output_tokens": accounting["output_tokens"],
                    "ledger_usage_source": accounting["usage_source"],
                    "ledger_entry_sha256": ledger_entry["entry_sha256"],
                    "redacted_request_headers": {
                        "Authorization": "Bearer <redacted>",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "container-ghosts-smoke/0.1",
                    },
                }
                append_jsonl(records_path, record)
                completed_ids.add(item["call_id"])
                executed += 1
                if item["global_sequence_index"] == 0:
                    write_json(out / "capability_gate.json", capability_assessment(record, image))
                if result["http_status"] != 200 or result["transport_error"]:
                    stop_status = "endpoint_error"
                    stop_detail = f"{item['call_id']} returned status={result['http_status']} error={result['transport_error']}"
                    break
            if stop_status in {"partial", "endpoint_error"}:
                break
    except CostCapAbort as exc:
        stop_status = "cost_cap_abort"
        stop_detail = str(exc)

    records = read_jsonl(records_path)
    remaining = [item["call_id"] for item in plan["items"] if item["call_id"] not in {r["call_id"] for r in records}]
    if not remaining and stop_status == "complete":
        summary = analyze_smoke(config_path, artifacts, out)
        status = "complete" if not summary["validation_errors"] else "complete_with_validation_errors"
    else:
        status = stop_status if stop_status != "complete" else "partial"
        summary = None
    state = {
        "status": status,
        "detail": stop_detail,
        "planned_calls": plan["planned_calls"],
        "completed_calls": len(records),
        "remaining_call_ids": remaining,
        "executed_this_invocation": executed,
        "smoke_plan_sha256": plan_hash,
        "summary_path": "smoke_summary.json" if summary else None,
    }
    write_state(out, state)
    if summary is not None:
        write_artifact_hashes(out)
    return state


def repeat_pairs(records: list[dict]) -> dict:
    pairs = []
    groups = defaultdict(list)
    for record in records:
        groups[(record["mode"], record["variant"])].append(record)
    for (mode, variant), rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["occurrence"])
        if len(rows) == 2:
            first, second = rows
            first_letters = parse_three_letters(first["response_text"])
            second_letters = parse_three_letters(second["response_text"])
            pairs.append({
                "mode": mode,
                "variant": variant,
                "call_ids": [first["call_id"], second["call_id"]],
                "raw_text_identical": first["response_text"] == second["response_text"],
                "parsed_letters_identical": first_letters == second_letters if first_letters and second_letters else None,
                "per_question_identical": [a == b for a, b in zip(first_letters or (), second_letters or ())] if first_letters and second_letters else None,
            })
    return {"pairs": pairs}


def semantic_summary(records: list[dict], image: dict) -> dict:
    labels = image["probe_labels"]
    rows = []
    for record in records:
        letters = parse_three_letters(record["response_text"])
        semantics = semantic_answers(record["response_text"], record["option_mappings"]) if letters else None
        rows.append({
            "call_id": record["call_id"],
            "variant": record["variant"],
            "letters": list(letters) if letters else None,
            "semantics": semantics,
            "q1_correct": bool(semantics and semantics["q1"] == labels["count_or_color_answer"]),
            "q2_correct": bool(semantics and semantics["q2"] == labels["caption_correct"]),
            "q3_semantic_answer": semantics["q3"] if semantics else None,
        })
    valid = sum(1 for row in rows if row["letters"] is not None)
    return {
        "rows": rows,
        "valid_exact_grammar": valid,
        "invalid_exact_grammar": len(rows) - valid,
        "q1_correct_count": sum(1 for row in rows if row["q1_correct"]),
        "q2_correct_count": sum(1 for row in rows if row["q2_correct"]),
    }


def contrast_summary(records: list[dict]) -> dict:
    contrasts = {"pngrepr": ("P0", "P1"), "jpegcam": ("J0", "JC"), "jpegai": ("J0", "JA"), "prov": ("JC", "JA")}
    by_variant_occurrence = {(r["variant"], r["occurrence"]): r for r in records if r["mode"] == "abba"}
    output = {}
    for name, (left, right) in contrasts.items():
        rows = []
        for occurrence in (1, 2):
            a = by_variant_occurrence.get((left, occurrence))
            b = by_variant_occurrence.get((right, occurrence))
            if not a or not b:
                continue
            la = parse_three_letters(a["response_text"])
            lb = parse_three_letters(b["response_text"])
            rows.append({
                "occurrence": occurrence,
                "call_ids": [a["call_id"], b["call_id"]],
                "letters": [list(la) if la else None, list(lb) if lb else None],
                "any_letter_difference": la != lb if la and lb else None,
                "per_question_difference": [x != y for x, y in zip(la or (), lb or ())] if la and lb else None,
            })
        output[name] = {"pair": [left, right], "occurrence_matched_observations": rows}
    return output


def canary_and_provenance(records: list[dict], image: dict) -> dict:
    canary_rows = []
    marker_rows = []
    for record in records:
        text = record["response_text"]
        if canary_leaks(text, image["canary"]):
            canary_rows.append(record["call_id"])
        found = [marker for marker in PROVENANCE_MARKERS if marker in text]
        if found:
            marker_rows.append({"call_id": record["call_id"], "markers": found})
    return {
        "canary": image["canary"],
        "exact_canary_emission_call_ids": canary_rows,
        "exact_canary_emission_count": len(canary_rows),
        "provenance_marker_rows": marker_rows,
        "provenance_marker_count": len(marker_rows),
    }


def relay_artifacts(records: list[dict], out: Path) -> dict:
    rows = []
    for record in records:
        response_path = out / record["raw_response_path"]
        response_json = None
        if response_path.read_bytes():
            try:
                response_json = json.loads(response_path.read_text())
            except (UnicodeDecodeError, json.JSONDecodeError):
                response_json = None
        top_level = sorted(response_json.keys()) if isinstance(response_json, dict) else []
        extra_top_level = sorted(set(top_level) - EXPECTED_RESPONSE_FIELDS)
        choice = response_json.get("choices", [{}])[0] if isinstance(response_json, dict) and response_json.get("choices") else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        lower_headers = {str(k).lower(): v for k, v in record.get("response_headers", {}).items()}
        rate_limit_headers = {
            k: v for k, v in lower_headers.items()
            if k.startswith("x-ratelimit") or k in {"retry-after", "x-request-id"}
        }
        rows.append({
            "call_id": record["call_id"],
            "http_status": record["http_status"],
            "latency_ms": record["latency_ms"],
            "served_model": record["served_model"],
            "system_fingerprint": record["system_fingerprint"],
            "finish_reason": record["finish_reason"],
            "refusal": record["refusal"],
            "transport_error": record["transport_error"],
            "json_error": record["json_error"],
            "rate_limit_and_request_headers": rate_limit_headers,
            "extra_top_level_response_fields": extra_top_level,
            "message_fields": sorted(message.keys()) if isinstance(message, dict) else [],
            "response_text_byte_length": len(record["response_text"].encode("utf-8")),
        })
    latencies = [row["latency_ms"] for row in rows]
    return {
        "rows": rows,
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "mean": sum(latencies) / len(latencies) if latencies else None,
        },
        "distinct_served_models": sorted({row["served_model"] for row in rows if row["served_model"] is not None}),
        "distinct_system_fingerprints": sorted({row["system_fingerprint"] for row in rows if row["system_fingerprint"] is not None}),
    }


def write_artifact_hashes(out: Path) -> None:
    artifact_hashes = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "artifact_hashes.json":
            data = path.read_bytes()
            artifact_hashes[path.relative_to(out).as_posix()] = {
                "sha256": sha256_bytes(data),
                "byte_length": len(data),
            }
    write_json(out / "artifact_hashes.json", {"schema": "container-ghosts.artifact-hashes.v1", "artifacts": artifact_hashes})


def analyze_smoke(config_path: Path, artifacts: Path, out: Path) -> dict:
    config = read_json(config_path)
    manifest = read_json(artifacts / "build_manifest.json")
    image = image_for(manifest, config["image_id"])
    plan = read_json(out / "smoke_plan.json")
    records = read_jsonl(out / "records.jsonl")
    ledger = ledger_from_config(config, out)
    errors = ledger.verify()
    if len(records) != plan["planned_calls"]:
        errors.append(f"record count {len(records)} does not match planned calls {plan['planned_calls']}")
    if len({record["nonce"] for record in records}) != len(records):
        errors.append("nonces are not unique")
    if len({record["call_id"] for record in records}) != len(records):
        errors.append("call_ids are not unique")
    for record in records:
        want_image_hash = image["variants"][record["variant"]]["sha256"]
        if record["image_sha256"] != want_image_hash:
            errors.append(f"transmitted hash mismatch for {record['call_id']}")
        for key in ("raw_request_path", "raw_response_path"):
            path = out / record[key]
            if not path.exists():
                errors.append(f"missing raw artifact {record[key]}")
                continue
            digest = sha256_bytes(path.read_bytes())
            want = record["raw_request_sha256"] if key.startswith("raw_request") else record["raw_response_sha256"]
            if digest != want:
                errors.append(f"raw artifact hash mismatch for {record[key]}")
        if record["raw_bytes_type"] != "bytes":
            errors.append(f"{record['call_id']} was not prepared from raw bytes")
    core = sorted((r for r in records if r["mode"] == "abba"), key=lambda r: r["sequence_index"])
    if core:
        errors.extend("core: " + error for error in validate_schedule([r["variant"] for r in core]))
    control_groups = defaultdict(list)
    for record in records:
        if record["phase"] == "exact_repeat_control":
            control_groups[record["mode"]].append(record)
    for mode, rows in control_groups.items():
        if len({row["variant"] for row in rows}) != 1:
            errors.append(f"{mode} mixed variants")

    semantic = semantic_summary(records, image)
    repeats = repeat_pairs(records)
    repeats["raw_text_identical_count"] = sum(1 for pair in repeats["pairs"] if pair["raw_text_identical"])
    repeats["parsed_letters_identical_count"] = sum(1 for pair in repeats["pairs"] if pair["parsed_letters_identical"] is True)
    repeats["pair_count"] = len(repeats["pairs"])
    relay = relay_artifacts(records, out)
    write_json(out / "relay_artifacts.json", relay)
    entries = ledger.entries()
    total_cost = entries[-1]["cumulative_cost_usd"] if entries else usd_string(ledger.cumulative_cost())
    summary = {
        "schema": "container-ghosts.vyce-smoke-summary.v1",
        "scientific_status": config["scientific_status"],
        "validation_errors": errors,
        "planned_calls": plan["planned_calls"],
        "completed_calls": len(records),
        "endpoint": config["endpoint"]["name"],
        "requested_model": config["endpoint"]["model_snapshot"],
        "served_models": relay["distinct_served_models"],
        "system_fingerprints": relay["distinct_system_fingerprints"],
        "cost": {
            "ledger_path": "cost_ledger.jsonl",
            "ledger_entries": len(entries),
            "total_cost_usd_under_assumed_prices": total_cost,
            "hard_cap_usd": usd_string(ledger.hard_cap_usd),
            "assumed_input_price_per_million_usd": str(ledger.input_price),
            "assumed_output_price_per_million_usd": str(ledger.output_price),
            "ledgered_input_tokens": sum(entry["input_tokens"] for entry in entries),
            "ledgered_output_tokens": sum(entry["output_tokens"] for entry in entries),
            "usage_sources": sorted({entry["usage_source"] for entry in entries}),
        },
        "semantic_summary": semantic,
        "exact_repeat_summary": repeats,
        "cross_container_descriptive": contrast_summary(records),
        "canary_and_provenance_scan": canary_and_provenance(records, image),
        "relay_artifacts_path": "relay_artifacts.json",
    }
    write_json(out / "smoke_summary.json", summary)
    write_artifact_hashes(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/vyce_smoke.json"))
    parser.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    parser.add_argument("--out", type=Path, default=Path("results/vyce-smoke"))
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    if args.analyze_only:
        summary = analyze_smoke(args.config, args.artifacts, args.out)
        print(
            "vyce smoke analysis: "
            f"{summary['completed_calls']}/{summary['planned_calls']} calls, "
            f"validation_errors={len(summary['validation_errors'])}"
        )
        return 0 if not summary["validation_errors"] else 1
    state = execute_smoke(args.config, args.artifacts, args.out, args.max_calls)
    print(
        f"vyce smoke {state['status']}: {state['completed_calls']}/{state['planned_calls']} calls"
        + (f" ({state['detail']})" if state.get("detail") else "")
    )
    return 0 if state["status"] in {"partial", "complete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
