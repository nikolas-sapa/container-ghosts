import base64
import json
from decimal import Decimal
from pathlib import Path

import pytest

from ghosts.cost_ledger import CostCapAbort, CostLedger
from ghosts.openai_compatible import OpenAICompatibleChatEndpoint, PayloadIntegrityError, validate_prepared_payload
from ghosts.probe_harness import endpoint_payload, palindromic_schedule, sha256_bytes, utc_now, validate_schedule
from ghosts.vyce_smoke import build_plan, execute_smoke


def endpoint_definition(tmp_path):
    key_path = tmp_path / "fake-key"
    key_path.write_text("test-key-not-a-secret")
    return {
        "name": "vyce_nemotron_relay",
        "api_shape": "openai_compatible_chat_completions",
        "base_url": "https://vyceai.com/v1",
        "chat_completions_path": "/chat/completions",
        "api_key_file": str(key_path),
        "model_snapshot": "nemotron-3.5-super-vl",
        "temperature": 0,
        "max_output_tokens": 16,
    }


def test_openai_compatible_payload_uses_chat_completions_inline_image(tmp_path):
    endpoint = endpoint_definition(tmp_path)
    prepared = endpoint_payload(endpoint, b"image-bytes", "image/png", "prompt")
    body = prepared["provider_payload"]
    assert body["model"] == "nemotron-3.5-super-vl"
    assert body["max_tokens"] == 16
    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "prompt"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert validate_prepared_payload(prepared)["payload_image_sha256"]


class FakeHeaders:
    def items(self):
        return [("Content-Type", "application/json")]


class FakeResponse:
    status = 200
    headers = FakeHeaders()

    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class CaptureOpener:
    def __init__(self):
        self.request = None
        self.calls = 0

    def open(self, request, timeout):
        self.request = request
        self.calls += 1
        body = json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": "nemotron-3.5-super-vl",
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "A,B,A"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        }).encode()
        return FakeResponse(body)


def test_adapter_transmits_exact_image_bytes_and_redacts_key_from_result(tmp_path):
    endpoint = endpoint_definition(tmp_path)
    image_bytes = b"\x89PNG\r\n\x1a\nimage-bytes"
    prepared = endpoint_payload(endpoint, image_bytes, "image/png", "prompt")
    adapter = OpenAICompatibleChatEndpoint(endpoint)
    capture = CaptureOpener()
    adapter.opener = capture
    result = adapter.call(prepared)
    assert result["ok"] is True
    assert result["text"] == "A,B,A"
    assert capture.calls == 1
    sent = json.loads(capture.request.data.decode())
    url = sent["messages"][0]["content"][1]["image_url"]["url"]
    encoded = url.split(",", 1)[1]
    assert base64.b64decode(encoded) == image_bytes
    assert capture.request.headers["Authorization"] == "Bearer test-key-not-a-secret"
    assert "test-key-not-a-secret" not in json.dumps({k: v for k, v in result.items() if k not in {"request_body", "response_body"}})


def test_payload_mutation_is_fail_closed_before_network(tmp_path):
    endpoint = endpoint_definition(tmp_path)
    prepared = endpoint_payload(endpoint, b"image-bytes", "image/png", "prompt")
    url = prepared["provider_payload"]["messages"][0]["content"][1]["image_url"]["url"]
    prefix, encoded = url.split(",", 1)
    mutated = encoded[:-1] + ("A" if encoded[-1] != "A" else "B")
    prepared["provider_payload"]["messages"][0]["content"][1]["image_url"]["url"] = prefix + "," + mutated
    adapter = OpenAICompatibleChatEndpoint(endpoint)
    capture = CaptureOpener()
    adapter.opener = capture
    with pytest.raises(PayloadIntegrityError):
        adapter.call(prepared)
    assert capture.calls == 0


def test_cost_ledger_aborts_at_artificially_tiny_cap(tmp_path):
    ledger = CostLedger(tmp_path / "ledger.jsonl", "0.00001000")
    ledger.append_call(
        call_id="first", phase="test", model="m", input_tokens=10, output_tokens=2,
        usage_source="api_usage", request_sha256="a", response_sha256="b",
    )
    with pytest.raises(CostCapAbort):
        ledger.check_cap(Decimal("0.00000400"), "second")
    assert len(ledger.entries()) == 1
    assert ledger.verify() == []


def test_cost_ledger_hash_chain_detects_tampering(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = CostLedger(path, "0.01")
    ledger.append_call(
        call_id="first", phase="test", model="m", input_tokens=10, output_tokens=2,
        usage_source="api_usage", request_sha256="a", response_sha256="b",
    )
    text = path.read_text()
    path.write_text(text.replace('"input_tokens":10', '"input_tokens":11'))
    assert ledger.verify()


def write_mini_manifest(tmp_path):
    artifacts = tmp_path / "artifacts"
    variant_dir = artifacts / "variants"
    variant_dir.mkdir(parents=True)
    variants = {}
    for variant in ["J0", "P0", "P1", "PT", "JC", "JA"]:
        suffix = "png" if variant.startswith("P") else "jpg"
        data = f"fake-image-{variant}".encode()
        relative = f"variants/object_arrangement__{variant}.{suffix}"
        (artifacts / relative).write_bytes(data)
        variants[variant] = {"path": relative, "sha256": sha256_bytes(data), "byte_length": len(data)}
    manifest = {
        "images": [{
            "image_id": "object_arrangement",
            "canary": "GHOSTCANARY_TEST",
            "probe_labels": {
                "q1": "count",
                "count_or_color_answer": "three arranged objects",
                "caption_correct": "Three face-free stylized objects on a surface",
                "caption_wrong": "A plate of food on a table",
            },
            "variants": variants,
        }]
    }
    (artifacts / "build_manifest.json").write_text(json.dumps(manifest))
    return artifacts, manifest


def test_smoke_plan_has_sixteen_calls_and_embeds_exact_repeat_controls(tmp_path):
    config = json.loads(Path("configs/vyce_smoke.json").read_text())
    _, manifest = write_mini_manifest(tmp_path)
    plan = build_plan(config, manifest)
    assert plan["planned_calls"] == 16
    assert len(plan["items"]) == 16
    core = [item["variant"] for item in plan["items"] if item["mode"] == "abba"]
    assert core == palindromic_schedule(config["core_seed"])
    assert validate_schedule(core) == []
    assert [item["variant"] for item in plan["items"] if item["mode"] == "exact-repeat-j0"] == ["J0", "J0"]
    assert [item["variant"] for item in plan["items"] if item["mode"] == "exact-repeat-p0"] == ["P0", "P0"]
    assert len({item["nonce"] for item in plan["items"]}) == 16


def install_fake_successful_endpoint(monkeypatch):
    def fake_call(self, prepared):
        request_body = self.request_body_bytes(prepared)
        response_json = {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "model": self.definition["model_snapshot"],
            "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "A,B,A"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 3, "total_tokens": 103},
        }
        response_body = json.dumps(response_json, separators=(",", ":")).encode()
        return {
            "ok": True,
            "http_status": 200,
            "headers": {"Content-Type": "application/json"},
            "transport_error": None,
            "json_error": None,
            "started_utc": utc_now(),
            "finished_utc": utc_now(),
            "latency_ms": 1.0,
            "request_body": request_body,
            "request_sha256": sha256_bytes(request_body),
            "response_body": response_body,
            "response_sha256": sha256_bytes(response_body),
            "response_json": response_json,
            "text": "A,B,A",
            "model_snapshot": self.definition["model_snapshot"],
            "system_fingerprint": "fake-fingerprint",
            "finish_reason": "stop",
            "refusal": None,
            "usage": {"input_tokens": 100, "output_tokens": 3, "total_tokens": 103, "raw_usage": response_json["usage"]},
        }
    monkeypatch.setattr(OpenAICompatibleChatEndpoint, "call", fake_call)


def test_execute_smoke_end_to_end_with_fake_transport(monkeypatch, tmp_path):
    install_fake_successful_endpoint(monkeypatch)
    artifacts, _ = write_mini_manifest(tmp_path)
    state = execute_smoke(Path("configs/vyce_smoke.json"), artifacts, tmp_path / "smoke")
    assert state["status"] == "complete"
    assert state["completed_calls"] == 16
    summary = json.loads((tmp_path / "smoke" / "smoke_summary.json").read_text())
    assert summary["validation_errors"] == []
    assert summary["exact_repeat_summary"]["pair_count"] == 8
    assert summary["exact_repeat_summary"]["parsed_letters_identical_count"] == 8
    ledger = CostLedger(tmp_path / "smoke" / "cost_ledger.jsonl", "4.00")
    assert len(ledger.entries()) == 16
    assert ledger.verify() == []


def test_execute_smoke_batch_cap_abort_before_any_fake_transport_call(monkeypatch, tmp_path):
    install_fake_successful_endpoint(monkeypatch)
    config = json.loads(Path("configs/vyce_smoke.json").read_text())
    config["cost"]["hard_cap_usd"] = "0.00000100"
    config_path = tmp_path / "tiny-cap-config.json"
    config_path.write_text(json.dumps(config))
    artifacts, _ = write_mini_manifest(tmp_path)
    state = execute_smoke(config_path, artifacts, tmp_path / "smoke")
    assert state["status"] == "cost_cap_abort"
    assert state["completed_calls"] == 0
    assert not (tmp_path / "smoke" / "records.jsonl").exists()
