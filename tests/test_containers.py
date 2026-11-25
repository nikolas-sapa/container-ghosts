import io

import numpy as np
import piexif
from PIL import Image

from ghosts.jpegcodec import com_segment, insert_segments, make_segment, inventory as jpeg_inventory, pad_jpeg_to_group
from ghosts.pngcodec import (
    encode_png, insert_chunks, inventory as png_inventory, itxt_chunk,
    pad_png_to_group, text_chunk,
)


def fixture_array():
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)


def pillow_rgb(data):
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def jpeg_fixture(arr):
    out = io.BytesIO()
    Image.fromarray(arr, "RGB").save(out, format="JPEG", quality=95, subsampling=0, progressive=False, optimize=False)
    return out.getvalue()


def test_png_filter_strategies_decode_bit_identically():
    arr = fixture_array()
    for filter_type in range(5):
        encoded = encode_png(arr, compress_level=6, filter_type=filter_type)
        assert np.array_equal(pillow_rgb(encoded), arr)


def test_png_chunk_insertion_xmp_and_contiguous_idat():
    arr = fixture_array()
    base = encode_png(arr)
    inserted = insert_chunks(base, [
        text_chunk("Comment", "neutral"),
        itxt_chunk("XML:com.adobe.xmp", "<x:xmpmeta xmlns:x='adobe:ns:meta/'/>"),
    ])
    inv = png_inventory(inserted)
    assert inv["counts"]["tEXt"] == 1
    assert inv["counts"]["iTXt"] == 1
    assert inv["idat_contiguous"] is True
    assert np.array_equal(pillow_rgb(inserted), arr)


def test_png_padding_exact_length():
    arr = fixture_array()
    a = encode_png(arr, compress_level=6)
    b = insert_chunks(encode_png(arr, compress_level=9), [text_chunk("Comment", "x" * 100)])
    target = max(len(a), len(b))
    assert len(pad_png_to_group(a, target)) == len(pad_png_to_group(b, target))


def test_jpeg_byte_splice_preserves_scan_critical_bytes():
    arr = fixture_array()
    j0 = jpeg_fixture(arr)
    j1 = insert_segments(j0, [com_segment(b"neutral container test")])
    i0 = jpeg_inventory(j0)
    i1 = jpeg_inventory(j1)
    for key in ("scan_sha256", "dqt_sha256", "dht_sha256", "sof_sha256"):
        assert i0[key] == i1[key]
    assert i1["counts"]["COM"] == 1
    assert i1["progressive"] is False
    assert i1["restart_segments"] == 0
    assert i1["app2_icc_present"] is False
    assert i1["app14_adobe_present"] is False
    assert i1["exif_orientation_present"] is False
    assert i1["exif_thumbnail_present"] is False


def test_jpeg_padding_exact_length():
    arr = fixture_array()
    j0 = jpeg_fixture(arr)
    short = insert_segments(j0, [com_segment(b"a")])
    long = insert_segments(j0, [com_segment(b"a" * 100)])
    target = max(len(short), len(long))
    assert len(pad_jpeg_to_group(short, target)) == len(pad_jpeg_to_group(long, target))


def test_orientation_exclusion_check_can_fire():
    arr = fixture_array()
    j0 = jpeg_fixture(arr)
    exif = piexif.dump({"0th": {piexif.ImageIFD.Orientation: 6}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None})
    tagged = insert_segments(j0, [make_segment(0xE1, exif)])
    assert jpeg_inventory(tagged)["exif_orientation_present"] is True


def test_png_forbidden_chunk_check_can_fire():
    arr = fixture_array()
    bad = insert_chunks(encode_png(arr), [(b"eXIf", b"II*\x00\x08\x00\x00\x00\x00\x00")])
    assert "eXIf" in png_inventory(bad)["forbidden_present"]


def test_scan_mutation_changes_scan_hash():
    arr = fixture_array()
    j0 = bytearray(jpeg_fixture(arr))
    inv0 = jpeg_inventory(bytes(j0))
    pos = len(j0) - 10
    j0[pos] ^= 1
    inv1 = jpeg_inventory(bytes(j0))
    assert inv0["scan_sha256"] != inv1["scan_sha256"]
