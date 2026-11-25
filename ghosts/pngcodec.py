import binascii
import struct
import zlib
from hashlib import sha256

import numpy as np

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FILTER_NAMES = {0: "none", 1: "sub", 2: "up", 3: "average", 4: "paeth"}
FORBIDDEN_CHUNKS = {
    "gAMA", "cHRM", "iCCP", "sRGB", "cICP", "sBIT", "tRNS", "bKGD",
    "pHYs", "acTL", "fcTL", "fdAT", "eXIf", "oFFs", "sCAL",
}


def chunk(chunk_type: bytes, payload: bytes) -> bytes:
    if len(chunk_type) != 4 or not all(65 <= c <= 90 or 97 <= c <= 122 for c in chunk_type):
        raise ValueError("PNG chunk type must be four ASCII letters")
    crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", crc)


def parse_chunks(data: bytes):
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    out = []
    pos = len(PNG_SIGNATURE)
    while pos + 12 <= len(data):
        start = pos
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("truncated PNG chunk")
        payload = data[pos + 8:pos + 8 + length]
        got_crc = struct.unpack(">I", data[pos + 8 + length:end])[0]
        want_crc = binascii.crc32(ctype + payload) & 0xFFFFFFFF
        if got_crc != want_crc:
            raise ValueError(f"CRC mismatch in {ctype.decode('ascii', 'replace')}")
        out.append({
            "type": ctype.decode("ascii"), "length": length, "start": start,
            "end": end, "payload": payload,
        })
        pos = end
        if ctype == b"IEND":
            break
    if not out or out[-1]["type"] != "IEND" or pos != len(data):
        raise ValueError("PNG does not end exactly at IEND")
    return out


def _left(row: bytes, bpp: int) -> np.ndarray:
    arr = np.frombuffer(row, dtype=np.uint8)
    left = np.zeros_like(arr)
    left[bpp:] = arr[:-bpp]
    return left


def _paeth(a, b, c):
    p = a.astype(np.int16) + b.astype(np.int16) - c.astype(np.int16)
    pa = np.abs(p - a.astype(np.int16))
    pb = np.abs(p - b.astype(np.int16))
    pc = np.abs(p - c.astype(np.int16))
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c)).astype(np.uint8)


def filter_scanlines(rgb: np.ndarray, filter_type: int) -> bytes:
    if filter_type not in FILTER_NAMES:
        raise ValueError("filter_type must be 0..4")
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("expected uint8 RGB array")
    bpp = 3
    rows = []
    previous = np.zeros(rgb.shape[1] * 3, dtype=np.uint8)
    for y in range(rgb.shape[0]):
        row_arr = rgb[y].reshape(-1)
        row = row_arr.tobytes()
        if filter_type == 0:
            filtered = row_arr
        elif filter_type == 1:
            filtered = row_arr.copy()
            filtered[bpp:] = row_arr[bpp:] - row_arr[:-bpp]
        else:
            left = _left(row, bpp)
            up = previous
            if filter_type == 2:
                pred = up
            elif filter_type == 3:
                pred = ((left.astype(np.uint16) + up.astype(np.uint16)) // 2).astype(np.uint8)
            else:
                up_left = np.zeros_like(left)
                if y:
                    up_left[bpp:] = previous[:-bpp]
                pred = _paeth(left, up, up_left)
            filtered = row_arr - pred
        rows.append(bytes([filter_type]) + np.asarray(filtered, dtype=np.uint8).tobytes())
        previous = row_arr
    return b"".join(rows)


def text_chunk(keyword: str, text: str) -> tuple[bytes, bytes]:
    key = keyword.encode("latin-1")
    if not 1 <= len(key) <= 79 or b"\x00" in key:
        raise ValueError("invalid PNG text keyword")
    return b"tEXt", key + b"\x00" + text.encode("latin-1")


def ztxt_chunk(keyword: str, text: str) -> tuple[bytes, bytes]:
    key = keyword.encode("latin-1")
    payload = key + b"\x00\x00" + zlib.compress(text.encode("latin-1"), 6)
    return b"zTXt", payload


def itxt_chunk(keyword: str, text: str, compressed: bool = False) -> tuple[bytes, bytes]:
    key = keyword.encode("latin-1")
    raw = text.encode("utf-8")
    if compressed:
        raw = zlib.compress(raw, 6)
    payload = key + b"\x00" + bytes([1 if compressed else 0, 0]) + b"\x00\x00" + raw
    return b"iTXt", payload


def encode_png(rgb: np.ndarray, compress_level: int = 6, filter_type: int = 0,
               idat_chunk_size: int | None = None) -> bytes:
    height, width = rgb.shape[:2]
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanlines = filter_scanlines(rgb, filter_type)
    compressed = zlib.compress(scanlines, compress_level)
    if idat_chunk_size is None or idat_chunk_size <= 0:
        pieces = [compressed]
    else:
        pieces = [compressed[i:i + idat_chunk_size] for i in range(0, len(compressed), idat_chunk_size)]
    out = bytearray(PNG_SIGNATURE)
    out += chunk(b"IHDR", ihdr)
    for piece in pieces:
        out += chunk(b"IDAT", piece)
    out += chunk(b"IEND", b"")
    return bytes(out)


def insert_chunks(data: bytes, chunks_to_add: list[tuple[bytes, bytes]]) -> bytes:
    parsed = parse_chunks(data)
    iend = parsed[-1]
    insertion = b"".join(chunk(ctype, payload) for ctype, payload in chunks_to_add)
    return data[:iend["start"]] + insertion + data[iend["start"]:]


def png_padding_chunk(pad_payload_bytes: int) -> tuple[bytes, bytes]:
    if pad_payload_bytes < 4:
        raise ValueError("tEXt padding payload must fit keyword and separator")
    return b"tEXt", b"Pad\x00" + b"0" * (pad_payload_bytes - 4)


def pad_png_to_group(data: bytes, group_target_without_padding: int) -> bytes:
    target = group_target_without_padding + 16
    payload_len = target - len(data) - 12
    if payload_len < 4:
        raise ValueError("PNG padding target too small")
    return insert_chunks(data, [png_padding_chunk(payload_len)])


def inventory(data: bytes) -> dict:
    parsed = parse_chunks(data)
    idat_payload = b"".join(p["payload"] for p in parsed if p["type"] == "IDAT")
    counts = {}
    lengths = {}
    idat_contiguous = True
    seen_idat = False
    closed_idat = False
    ihdr = {}
    for part in parsed:
        ctype = part["type"]
        counts[ctype] = counts.get(ctype, 0) + 1
        lengths[ctype] = lengths.get(ctype, 0) + part["length"]
        if ctype == "IDAT":
            if closed_idat:
                idat_contiguous = False
            seen_idat = True
        elif seen_idat:
            closed_idat = True
        if ctype == "IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", part["payload"]
            )
            ihdr = {
                "width": width, "height": height, "bit_depth": bit_depth,
                "color_type": color_type, "compression": compression,
                "filter_method": filter_method, "interlace": interlace,
                "sha256": sha256(part["payload"]).hexdigest(),
            }
    forbidden = sorted(FORBIDDEN_CHUNKS.intersection(counts))
    return {
        "chunks": [{"type": p["type"], "length": p["length"]} for p in parsed],
        "counts": counts,
        "payload_lengths": lengths,
        "ihdr": ihdr,
        "idat_count": counts.get("IDAT", 0),
        "idat_contiguous": idat_contiguous,
        "idat_compressed_sha256": sha256(idat_payload).hexdigest(),
        "forbidden_present": forbidden,
    }


def _order(inv: dict) -> list[str]:
    return [part["type"] for part in inv["chunks"]]


def inventory_diff(baseline: dict, variant: dict) -> dict:
    types = sorted(set(baseline["counts"]) | set(variant["counts"]))
    return {
        "count_delta": {t: variant["counts"].get(t, 0) - baseline["counts"].get(t, 0) for t in types},
        "payload_length_delta": {
            t: variant["payload_lengths"].get(t, 0) - baseline["payload_lengths"].get(t, 0) for t in types
        },
        "order_changed": _order(baseline) != _order(variant),
    }
