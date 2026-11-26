import base64
import binascii
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ghosts.probe_harness import sha256_bytes, utc_now

DATA_URL_RE = re.compile(r"^data:([^;,]+);base64,(.+)$", re.DOTALL)


class PayloadIntegrityError(ValueError):
    pass


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def image_url_parts(provider_payload: dict) -> list[dict]:
    parts = []
    for message in provider_payload.get("messages", []):
        content = message.get("content")
        if isinstance(content, list):
            parts.extend(part for part in content if part.get("type") == "image_url")
    return parts


def validate_prepared_payload(prepared: dict) -> dict:
    image_bytes = prepared.get("image_bytes")
    if not isinstance(image_bytes, bytes):
        raise TypeError("image payload must be raw bytes, never a PIL object")
    parts = image_url_parts(prepared.get("provider_payload", {}))
    if len(parts) != 1:
        raise PayloadIntegrityError(f"expected exactly one inline image part, found {len(parts)}")
    url = parts[0].get("image_url", {}).get("url")
    if not isinstance(url, str):
        raise PayloadIntegrityError("inline image part has no image_url.url string")
    match = DATA_URL_RE.match(url)
    if not match:
        raise PayloadIntegrityError("inline image part is not a base64 data URL")
    mime_type, encoded = match.groups()
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise PayloadIntegrityError("inline image base64 does not decode strictly") from exc
    if decoded != image_bytes:
        raise PayloadIntegrityError("provider payload image bytes do not match prepared raw image bytes")
    return {
        "mime_type": mime_type,
        "payload_image_sha256": sha256_bytes(decoded),
        "payload_base64_sha256": sha256_bytes(encoded.encode("ascii")),
    }


def content_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
        return "".join(texts)
    return ""


def normalize_usage(usage: dict | None) -> dict:
    usage = usage or {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": usage.get("total_tokens"),
        "raw_usage": usage,
    }


class OpenAICompatibleChatEndpoint:
    def __init__(self, definition: dict):
        self.definition = definition
        self.base_url = definition["base_url"].rstrip("/")
        parsed = urllib.parse.urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("live endpoint base_url must be an https URL")
        self.path = definition.get("chat_completions_path", "/chat/completions")
        self.timeout_seconds = definition.get("timeout_seconds", 120)
        self.opener = urllib.request.build_opener(NoRedirectHandler())

    def api_key_at_call_time(self) -> str:
        key_path = Path(self.definition["api_key_file"]).expanduser()
        key = key_path.read_text(encoding="utf-8").strip()
        if not key:
            raise ValueError("API key file is empty")
        return key

    def request_body_bytes(self, prepared: dict) -> bytes:
        validate_prepared_payload(prepared)
        return canonical_json_bytes(prepared["provider_payload"])

    def call(self, prepared: dict) -> dict:
        body = self.request_body_bytes(prepared)
        url = self.base_url + self.path
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + self.api_key_at_call_time(),
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "container-ghosts-smoke/0.1",
            },
        )
        started_utc = utc_now()
        start = time.monotonic()
        status = None
        headers = {}
        response_body = b""
        transport_error = None
        try:
            with self.opener.open(request, timeout=self.timeout_seconds) as response:
                status = response.status
                headers = dict(response.headers.items())
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            headers = dict(exc.headers.items()) if exc.headers else {}
            response_body = exc.read()
            transport_error = f"http_status_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            transport_error = type(exc).__name__ + ": " + str(exc)
        latency_ms = round((time.monotonic() - start) * 1000, 3)
        finished_utc = utc_now()

        response_json = None
        json_error = None
        if response_body:
            try:
                response_json = json.loads(response_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                json_error = str(exc)
        choice = {}
        message = {}
        if isinstance(response_json, dict) and response_json.get("choices"):
            choice = response_json["choices"][0] or {}
            message = choice.get("message") or {}
        text = content_text(message) if message else ""
        return {
            "ok": status == 200 and response_json is not None and transport_error is None,
            "http_status": status,
            "headers": headers,
            "transport_error": transport_error,
            "json_error": json_error,
            "started_utc": started_utc,
            "finished_utc": finished_utc,
            "latency_ms": latency_ms,
            "request_body": body,
            "request_sha256": sha256_bytes(body),
            "response_body": response_body,
            "response_sha256": sha256_bytes(response_body),
            "response_json": response_json,
            "text": text,
            "model_snapshot": response_json.get("model") if isinstance(response_json, dict) else None,
            "system_fingerprint": response_json.get("system_fingerprint") if isinstance(response_json, dict) else None,
            "finish_reason": choice.get("finish_reason"),
            "refusal": message.get("refusal"),
            "usage": normalize_usage(response_json.get("usage") if isinstance(response_json, dict) else None),
        }
