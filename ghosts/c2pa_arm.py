import json
from pathlib import Path


class C2PAArmUnavailable(RuntimeError):
    pass


def investigation_notes() -> dict:
    return {
        "tooling": "c2pa-python 0.39.0 (c2pa-rs SDK 0.92.0) signs JPEG locally through APP11/JUMBF insertion",
        "probe_result": "local signing succeeded with the upstream public Ed25519 test certificate chain and preserved scan/DQT/DHT/SOF bytes in a probe, but repeated signing is not byte-deterministic because the SDK generates a fresh manifest UUID",
        "default_status": "stubbed out of the invariant core",
        "needed_for_activation": [
            "vendor or generate a clearly labeled test certificate chain",
            "pin or otherwise control manifest UUIDs and all nondeterministic claim bytes",
            "verify JPEG scan/DQT/DHT/SOF identity after APP11 insertion",
            "treat trust validation as out of scope per the specification",
        ],
    }


def sign_jpeg_with_c2pa(source: Path, dest: Path, manifest_definition: dict,
                        cert_pem: bytes, private_key_pem: bytes) -> bytes:
    try:
        import c2pa
    except ImportError as exc:
        raise C2PAArmUnavailable("install requirements-c2pa.txt to enable experimental local C2PA signing") from exc
    info = c2pa.C2paSignerInfo(c2pa.C2paSigningAlg.ED25519, cert_pem, private_key_pem, None)
    signer = c2pa.Signer.from_info(info)
    with c2pa.Builder(json.dumps(manifest_definition)) as builder:
        with source.open("rb") as src, dest.open("w+b") as dst:
            return builder.sign(signer, "image/jpeg", src, dst)
