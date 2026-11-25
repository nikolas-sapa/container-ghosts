import argparse
import io
import json
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from ghosts.c2pa_arm import investigation_notes
from ghosts.jpegcodec import com_segment, insert_segments, make_segment, pad_jpeg_to_group
from ghosts.metadata import (
    a1111_parameters, ai_exif, camera_exif, canary_for, comfy_workflow, xmp_app1_payload,
    xmp_packet,
)
from ghosts.pngcodec import encode_png, insert_chunks, itxt_chunk, pad_png_to_group, text_chunk, ztxt_chunk
from ghosts.stimuli import PROBE_LABELS, SIZE, generate_all

PNG_CORE_GROUP = ["P0", "P1", "PT", "PTC", "PTA"]
JPEG_PROVENANCE_GROUP = ["JC", "JA"]


def sha256_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def write_bytes(path: Path, data: bytes, root: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_bytes(data), "byte_length": len(data)}


def encode_canonical_jpeg(rgb: np.ndarray) -> bytes:
    out = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(
        out, format="JPEG", quality=95, subsampling=0, progressive=False,
        optimize=False, exif=b"", icc_profile=None,
    )
    return out.getvalue()


def decode_pillow_bytes(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def png_metadata_variants(p0: bytes, canary: str) -> dict[str, bytes]:
    neutral_xmp = xmp_packet("neutral", canary).decode("utf-8")
    camera_xmp = xmp_packet("camera", canary).decode("utf-8")
    ai_xmp = xmp_packet("ai", canary).decode("utf-8")
    neutral = [
        text_chunk("Comment", "neutral ancillary filler; canary " + canary),
        ztxt_chunk("Filler", "neutral compressed ancillary filler; canary " + canary),
        itxt_chunk("XML:com.adobe.xmp", neutral_xmp),
    ]
    camera = [
        text_chunk("Make", "Canon"),
        text_chunk("Model", "Canon EOS R6"),
        ztxt_chunk("CameraNotes", "digitalCapture fixture; RF24-105mm; ISO 200; canary " + canary),
        itxt_chunk("XML:com.adobe.xmp", camera_xmp),
    ]
    ai = [
        text_chunk("parameters", a1111_parameters(canary)),
        ztxt_chunk("workflow", comfy_workflow(canary)),
        itxt_chunk("XML:com.adobe.xmp", ai_xmp),
    ]
    return {
        "PT": insert_chunks(p0, neutral),
        "PTC": insert_chunks(p0, camera),
        "PTA": insert_chunks(p0, ai),
    }


def jpeg_metadata_variants(j0: bytes, canary: str) -> dict[str, bytes]:
    camera = [
        make_segment(0xE1, camera_exif(canary)),
        make_segment(0xE1, xmp_app1_payload("camera", canary)),
    ]
    ai = [
        make_segment(0xE1, ai_exif(canary)),
        make_segment(0xE1, xmp_app1_payload("ai", canary)),
    ]
    neutral_xmp = [make_segment(0xE1, xmp_app1_payload("neutral", canary))]
    neutral_com = [com_segment(("neutral COM fixture; canary " + canary).encode("ascii"))]
    return {
        "JC": insert_segments(j0, camera),
        "JA": insert_segments(j0, ai),
        "JXMP": insert_segments(j0, neutral_xmp),
        "JCOM": insert_segments(j0, neutral_com),
    }


def arm_for(name: str) -> str:
    if name == "P0":
        return "png_baseline_deflate6_filter_none_single_idat"
    if name == "P1":
        return "png_representation_deflate9_filter_paeth_split4096"
    if name.startswith("PC"):
        return "png_deflate_level_arm"
    if name.startswith("PF"):
        return "png_filter_strategy_arm"
    if name.startswith("PS"):
        return "png_idat_split_arm"
    if name in {"PT", "PTC", "PTA"}:
        return "png_ancillary_metadata_arm"
    if name in {"JC", "JA"}:
        return "jpeg_provenance_polarity_arm"
    if name == "JXMP":
        return "jpeg_xmp_insertion_arm"
    if name == "JCOM":
        return "jpeg_com_insertion_arm"
    return "jpeg_baseline_arm"


def apply_length_control(variants: dict[str, bytes]) -> dict[str, dict]:
    notes = {name: {"length_control_group": None, "byte_length_factor": True} for name in variants}
    png_target = max(len(variants[n]) for n in PNG_CORE_GROUP)
    for name in PNG_CORE_GROUP:
        variants[name] = pad_png_to_group(variants[name], png_target)
        notes[name]["length_control_group"] = "png_core_exact"
        notes[name]["byte_length_factor"] = False
    jpeg_target = max(len(variants[n]) for n in JPEG_PROVENANCE_GROUP)
    for name in JPEG_PROVENANCE_GROUP:
        variants[name] = pad_jpeg_to_group(variants[name], jpeg_target)
        notes[name]["length_control_group"] = "jpeg_provenance_exact"
        notes[name]["byte_length_factor"] = False
    return notes


def fallback_labels(image_id: str) -> dict:
    return {
        "q1": "object",
        "count_or_color_answer": "the most salient object or dominant color",
        "caption_correct": f"A scene containing the subject of {image_id}",
        "caption_wrong": "A blank featureless color field",
    }


def build_image(image_id: str, source_rgb: np.ndarray, out: Path) -> dict:
    canary = canary_for(image_id)
    source_png = encode_png(source_rgb, compress_level=6, filter_type=0)
    j0 = encode_canonical_jpeg(source_rgb)
    canonical_rgb = decode_pillow_bytes(j0)
    p0_unpadded = encode_png(canonical_rgb, compress_level=6, filter_type=0)

    variants = {
        "J0": j0,
        "P0": p0_unpadded,
        "P1": encode_png(canonical_rgb, compress_level=9, filter_type=4, idat_chunk_size=4096),
        "PC0": encode_png(canonical_rgb, compress_level=0, filter_type=0),
        "PC9": encode_png(canonical_rgb, compress_level=9, filter_type=0),
        "PF1": encode_png(canonical_rgb, compress_level=6, filter_type=1),
        "PF2": encode_png(canonical_rgb, compress_level=6, filter_type=2),
        "PF3": encode_png(canonical_rgb, compress_level=6, filter_type=3),
        "PF4": encode_png(canonical_rgb, compress_level=6, filter_type=4),
        "PS2K": encode_png(canonical_rgb, compress_level=6, filter_type=0, idat_chunk_size=2048),
    }
    variants.update(png_metadata_variants(p0_unpadded, canary))
    variants.update(jpeg_metadata_variants(j0, canary))
    length_notes = apply_length_control(variants)

    base_info = write_bytes(out / "base" / f"{image_id}.source.png", source_png, out)
    reference = {
        "J0_unpadded": write_bytes(out / "reference" / f"{image_id}.J0.unpadded.jpg", j0, out),
        "P0_unpadded": write_bytes(out / "reference" / f"{image_id}.P0.unpadded.png", p0_unpadded, out),
    }
    variant_info = {}
    for name, data in sorted(variants.items()):
        ext = "png" if data.startswith(b"\x89PNG") else "jpg"
        info = write_bytes(out / "variants" / f"{image_id}__{name}.{ext}", data, out)
        info.update({
            "format": ext,
            "arm": arm_for(name),
            **length_notes[name],
        })
        variant_info[name] = info

    return {
        "image_id": image_id,
        "width": SIZE,
        "height": SIZE,
        "canary": canary,
        "source_png": base_info,
        "reference": reference,
        "canonical_raster_sha256": sha256_bytes(canonical_rgb.tobytes()),
        "probe_labels": PROBE_LABELS.get(image_id, fallback_labels(image_id)),
        "variants": variant_info,
    }


def group_deltas(images: list[dict]) -> dict:
    deltas = {}
    for group, names in {"png_core_exact": PNG_CORE_GROUP, "jpeg_provenance_exact": JPEG_PROVENANCE_GROUP}.items():
        values = []
        for image in images:
            lengths = [image["variants"][n]["byte_length"] for n in names]
            values.append(max(lengths) - min(lengths))
        deltas[group] = {"max_delta_bytes": max(values), "images_checked": len(values)}
    return deltas


def load_corpus_images(corpus: Path) -> dict[str, np.ndarray]:
    loaded = {}
    for path in sorted(corpus.iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        with Image.open(path) as im:
            if "A" in im.getbands() or "transparency" in im.info:
                raise ValueError(f"alpha/transparency image excluded from invariant pipeline: {path}")
            rgb = ImageOps.exif_transpose(im).convert("RGB")
        width, height = rgb.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        rgb = rgb.crop((left, top, left + side, top + side)).resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        loaded[path.stem] = np.asarray(rgb, dtype=np.uint8).copy()
    if not loaded:
        raise ValueError(f"no PNG/JPEG corpus images found in {corpus}")
    return loaded


def build(out: Path, corpus: Path | None = None) -> dict:
    inputs = load_corpus_images(corpus) if corpus else generate_all()
    images = [build_image(image_id, arr, out) for image_id, arr in sorted(inputs.items())]
    manifest = {
        "schema": "container-ghosts.build-manifest.v1",
        "stimulus_kind": "licensed corpus drop-in" if corpus else "procedural development stimuli; replace with licensed corpus later",
        "stimulus_license": "corpus-supplied; audit required" if corpus else "project-generated synthetic development stimuli",
        "dimensions": {"width": SIZE, "height": SIZE, "color": "RGB", "bit_depth": 8},
        "canonical_raster_definition": "RGB bytes decoded from canonical J0 by pinned Pillow; source PNGs are development inputs, not the scientific raster",
        "canonical_jpeg": {
            "quality": 95, "subsampling": "4:4:4", "progressive": False,
            "optimize": False, "metadata": "stripped at encode; scientific JPEG inserts are byte-spliced",
        },
        "padding_policy": {
            "png_core_exact": PNG_CORE_GROUP,
            "jpeg_provenance_exact": JPEG_PROVENANCE_GROUP,
            "uncontrolled_size_factor": [
                "J0-vs-metadata insertion contrasts retain insertion byte length as an explicit experimental factor",
                "PC/PF/PS representation exploration arms are outside the exact-length core and retain byte length as an experimental factor",
            ],
            "group_deltas": group_deltas(images),
        },
        "c2pa_arm": investigation_notes(),
        "images": images,
    }
    path = out / "build_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    parser.add_argument("--corpus", type=Path, default=None, help="optional directory of licensed PNG/JPEG inputs; development stimuli are used when omitted")
    args = parser.parse_args()
    manifest = build(args.out, args.corpus)
    count = sum(len(image["variants"]) for image in manifest["images"])
    print(f"built {len(manifest['images'])} base images, {count} variants")
    for group, result in manifest["padding_policy"]["group_deltas"].items():
        print(f"{group}: max byte-length delta {result['max_delta_bytes']} bytes")


if __name__ == "__main__":
    main()
