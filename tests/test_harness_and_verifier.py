import json

import numpy as np
import pytest

from ghosts.probe_harness import endpoint_payload, palindromic_schedule, validate_schedule
from ghosts.pngcodec import encode_png
from ghosts.verify_invariance import mutation_test


def test_palindromic_schedule_constraints_across_seeds():
    for i in range(50):
        sequence = palindromic_schedule(f"seed-{i}")
        assert validate_schedule(sequence) == []
        first = sequence[:6]
        assert abs(first.index("JC") - first.index("JA")) == 1


def test_endpoint_payload_uses_raw_bytes_and_rejects_pil_like_objects():
    endpoint = {"name": "google", "model_snapshot": "m", "temperature": 0, "max_output_tokens": 16}
    prepared = endpoint_payload(endpoint, b"abc", "image/png", "prompt")
    assert prepared["image_bytes"] == b"abc"
    assert "inline_data" in json.dumps(prepared["provider_payload"])
    with pytest.raises(TypeError):
        endpoint_payload(endpoint, object(), "image/png", "prompt")


def test_verifier_mutation_test_catches_one_pixel(tmp_path):
    arr = np.zeros((8, 8, 3), dtype=np.uint8)
    data = encode_png(arr)
    variant_path = tmp_path / "variants" / "tiny__P0.png"
    variant_path.parent.mkdir()
    variant_path.write_bytes(data)
    manifest = {
        "images": [{
            "image_id": "tiny",
            "variants": {"P0": {"path": "variants/tiny__P0.png"}},
        }]
    }
    (tmp_path / "build_manifest.json").write_text(json.dumps(manifest))
    result = mutation_test(tmp_path)
    assert result["status"] == "MUTATION_TEST_PASS"
    assert "1 pixels differ" in result["decoder_catches"]["pillow"]
    assert "1 pixels differ" in result["decoder_catches"]["opencv"]
