import struct
from hashlib import sha256

import piexif

APP0, APP15, COM, DQT, DHT, SOS, EOI, DRI = 0xE0, 0xEF, 0xFE, 0xDB, 0xC4, 0xDA, 0xD9, 0xDD
SOF_MARKERS = set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
MARKER_NAMES = {
    0xD8: "SOI", 0xD9: "EOI", 0xDA: "SOS", 0xDB: "DQT", 0xC4: "DHT",
    0xDD: "DRI", 0xFE: "COM", 0xC0: "SOF0", 0xC2: "SOF2",
}
for i in range(16):
    MARKER_NAMES[0xE0 + i] = f"APP{i}"


def marker_name(marker: int) -> str:
    return MARKER_NAMES.get(marker, f"0x{marker:02X}")


def make_segment(marker: int, payload: bytes) -> bytes:
    length = len(payload) + 2
    if length > 0xFFFF:
        raise ValueError("JPEG segment too large")
    return b"\xff" + bytes([marker]) + struct.pack(">H", length) + payload


def parse_jpeg(data: bytes) -> dict:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG file")
    if not data.endswith(b"\xff\xd9"):
        raise ValueError("JPEG does not end with EOI")
    segments = []
    pos = 2
    scan_start = scan_end = None
    while pos < len(data) - 2:
        start = pos
        if data[pos] != 0xFF or data[pos + 1] == 0xFF:
            raise ValueError(f"expected marker at byte {pos}")
        marker = data[pos + 1]
        if marker == EOI:
            break
        if pos + 4 > len(data):
            raise ValueError("truncated JPEG segment")
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        end = pos + 2 + length
        if end > len(data):
            raise ValueError("truncated JPEG segment payload")
        payload = data[pos + 4:end]
        segments.append({
            "marker": marker, "name": marker_name(marker), "start": start, "end": end,
            "length": length - 2, "payload": payload,
        })
        pos = end
        if marker == SOS:
            scan_start = end
            scan_end = len(data) - 2
            break
    if scan_start is None:
        raise ValueError("no SOS found")
    return {"segments": segments, "scan_start": scan_start, "scan_end": scan_end, "scan": data[scan_start:scan_end]}


def insertion_offset(data: bytes) -> int:
    info = parse_jpeg(data)
    offset = 2
    for seg in info["segments"]:
        if seg["marker"] == SOS:
            break
        if APP0 <= seg["marker"] <= APP15 or seg["marker"] == COM:
            offset = seg["end"]
        else:
            break
    return offset


def insert_segments(data: bytes, segments: list[bytes]) -> bytes:
    offset = insertion_offset(data)
    return data[:offset] + b"".join(segments) + data[offset:]


def com_segment(payload: bytes) -> bytes:
    return make_segment(COM, payload)


def pad_jpeg_to_group(data: bytes, group_target_without_padding: int) -> bytes:
    target = group_target_without_padding + 5
    payload_len = target - len(data) - 4
    if payload_len < 1:
        raise ValueError("JPEG padding target too small")
    return insert_segments(data, [com_segment(b"0" * payload_len)])


def inventory(data: bytes) -> dict:
    info = parse_jpeg(data)
    counts = {}
    lengths = {}
    app2 = app14 = False
    sof = []
    for seg in info["segments"]:
        name = seg["name"]
        counts[name] = counts.get(name, 0) + 1
        lengths[name] = lengths.get(name, 0) + seg["length"]
        app2 |= seg["marker"] == 0xE2
        app14 |= seg["marker"] == 0xEE
        if seg["marker"] in SOF_MARKERS:
            sof.append({"name": name, "payload_sha256": sha256(seg["payload"]).hexdigest()})
    dqt = b"".join(data[s["start"]:s["end"]] for s in info["segments"] if s["marker"] == DQT)
    dht = b"".join(data[s["start"]:s["end"]] for s in info["segments"] if s["marker"] == DHT)
    sof_bytes = b"".join(data[s["start"]:s["end"]] for s in info["segments"] if s["marker"] in SOF_MARKERS)
    exif_findings = inspect_exif(data)
    return {
        "segments": [{"name": s["name"], "length": s["length"]} for s in info["segments"]],
        "counts": counts,
        "payload_lengths": lengths,
        "scan_sha256": sha256(info["scan"]).hexdigest(),
        "scan_length": len(info["scan"]),
        "dqt_sha256": sha256(dqt).hexdigest(),
        "dht_sha256": sha256(dht).hexdigest(),
        "sof_sha256": sha256(sof_bytes).hexdigest(),
        "sof": sof,
        "progressive": any(s["marker"] == 0xC2 for s in info["segments"]),
        "restart_segments": counts.get("DRI", 0),
        "app2_icc_present": app2,
        "app14_adobe_present": app14,
        **exif_findings,
    }


def inspect_exif(data: bytes) -> dict:
    info = parse_jpeg(data)
    orientation = False
    thumbnail = False
    exif_present = False
    for seg in info["segments"]:
        if seg["marker"] == 0xE1 and seg["payload"].startswith(b"Exif\x00\x00"):
            exif_present = True
            try:
                exif = piexif.load(seg["payload"])
            except Exception as exc:
                return {"exif_present": True, "exif_parse_error": str(exc),
                        "exif_orientation_present": True, "exif_thumbnail_present": True}
            zeroth = exif.get("0th", {})
            first = exif.get("1st", {})
            orientation |= 274 in zeroth
            thumbnail |= bool(first) or exif.get("thumbnail") is not None or 513 in first or 514 in first
    return {
        "exif_present": exif_present,
        "exif_orientation_present": orientation,
        "exif_thumbnail_present": thumbnail,
    }


def _order(inv: dict) -> list[str]:
    return [part["name"] for part in inv["segments"]]


def inventory_diff(baseline: dict, variant: dict) -> dict:
    names = sorted(set(baseline["counts"]) | set(variant["counts"]))
    return {
        "count_delta": {n: variant["counts"].get(n, 0) - baseline["counts"].get(n, 0) for n in names},
        "payload_length_delta": {
            n: variant["payload_lengths"].get(n, 0) - baseline["payload_lengths"].get(n, 0) for n in names
        },
        "order_changed": _order(baseline) != _order(variant),
    }
