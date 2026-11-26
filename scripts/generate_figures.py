#!/usr/bin/env python3
import argparse
import base64
import io
import json
import sys
import textwrap
from html import escape
from pathlib import Path

from PIL import Image

BG = "#F7F9FC"
CARD = "#FFFFFF"
INK = "#111C2E"
MUTED = "#526274"
FAINT = "#DDE5EE"
GRID = "#E9EEF5"
BLUE = "#006BFF"
BLUE_DARK = "#004FBE"
BLUE_PALE = "#E5EFFF"
TEAL = "#008B8A"
TEAL_PALE = "#E4F5F4"
PURPLE = "#6658C8"
PURPLE_PALE = "#EEEAFB"
GREEN = "#167A52"
GREEN_PALE = "#E6F4ED"
RED = "#C7355D"
RED_PALE = "#FAE8EF"
GRAY = "#8A99AD"
GRAY_PALE = "#EEF2F6"
DARK = "#243449"

FONT = "'Geist Sans',system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
MONO = "SFMono-Regular,Consolas,'Liberation Mono',monospace"


def fmt_int(value):
    return f"{int(value):,}"


def short_hash(value, head=12, tail=8):
    if len(value) <= head + tail + 3:
        return value
    return value[:head] + "..." + value[-tail:]


def load_facts(root):
    artifacts = root / "artifacts"
    required = [
        artifacts / "build_manifest.json",
        artifacts / "verification_manifest.json",
        artifacts / "dryrun" / "dryrun_report.json",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "artifact manifests are missing; run ./run.sh first: " + ", ".join(missing)
        )
    build = json.loads(required[0].read_text())
    verification = json.loads(required[1].read_text())
    dryrun = json.loads(required[2].read_text())
    return build, verification, dryrun


def validate_facts(build, verification, dryrun):
    errors = []
    if verification.get("status") != "pass" or verification.get("failures"):
        errors.append("verification manifest is not a clean pass")
    mutation = verification.get("mutation_test", {})
    if mutation.get("status") != "MUTATION_TEST_PASS":
        errors.append("one-pixel mutation control is missing or failing")
    if dryrun.get("status") != "pass" or dryrun.get("validation_errors") or dryrun.get("live_calls") != 0:
        errors.append("dry-run report is not a clean zero-live-call pass")
    for group, result in build["padding_policy"]["group_deltas"].items():
        if result["max_delta_bytes"] != 0:
            errors.append(f"{group} byte-length delta is nonzero")
    if errors:
        raise ValueError("refusing to draw presentation figures from unverified facts: " + "; ".join(errors))


def image_data_uri(path, width=280):
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        ratio = width / rgb.width
        height = round(rgb.height * ratio)
        rgb = rgb.resize((width, height), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class Svg:
    def __init__(self, width, height, title, description):
        self.width = width
        self.height = height
        self.parts = []
        self.defs = []
        self.title = title
        self.description = description
        self.add_defs()

    def add_defs(self):
        for name, color in [("blue", BLUE), ("gray", GRAY), ("teal", TEAL), ("purple", PURPLE)]:
            self.defs.append(
                f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
            )

    def add(self, markup):
        self.parts.append(markup)

    def rect(self, x, y, w, h, rx=0, fill="none", stroke="none", sw=1, opacity=1):
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>'
        )

    def line(self, x1, y1, x2, y2, color=FAINT, sw=1, dash=None, marker=None, opacity=1):
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        marker_attr = f' marker-end="url(#arrow-{marker})"' if marker else ""
        self.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
            f'stroke-width="{sw}" stroke-linecap="round" opacity="{opacity}"{dash_attr}{marker_attr}/>'
        )

    def path(self, d, fill="none", stroke=INK, sw=2, opacity=1, linecap="round", linejoin="round"):
        self.add(
            f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" '
            f'stroke-linecap="{linecap}" stroke-linejoin="{linejoin}" opacity="{opacity}"/>'
        )

    def circle(self, cx, cy, r, fill="none", stroke="none", sw=1, opacity=1):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" opacity="{opacity}"/>')

    def text(self, x, y, value, size=16, weight=400, fill=INK, anchor="start", family=FONT, spacing=None, opacity=1):
        spacing_attr = f' letter-spacing="{spacing}"' if spacing else ""
        self.add(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" opacity="{opacity}"{spacing_attr}>{escape(str(value))}</text>'
        )

    def text_block(self, x, y, value, max_chars, size=15, weight=480, fill=MUTED, line_height=None, family=FONT):
        line_height = line_height or round(size * 1.45)
        lines = textwrap.wrap(str(value), width=max_chars, break_long_words=False, break_on_hyphens=False)
        for index, line in enumerate(lines):
            self.text(x, y + index * line_height, line, size=size, weight=weight, fill=fill, family=family)
        return len(lines)

    def image(self, x, y, w, h, href, opacity=1):
        self.add(f'<image x="{x}" y="{y}" width="{w}" height="{h}" href="{href}" preserveAspectRatio="xMidYMid slice" opacity="{opacity}"/>')

    def pill(self, x, y, w, label, fill, color, height=34, size=13, weight=700):
        self.rect(x, y, w, height, rx=height / 2, fill=fill)
        self.text(x + w / 2, y + height / 2 + size * 0.36, label, size=size, weight=weight, fill=color, anchor="middle")

    def panel(self, x, y, w, h, title=None, eyebrow=None):
        self.rect(x, y, w, h, rx=24, fill=CARD, stroke=FAINT, sw=1.2)
        if eyebrow:
            self.text(x + 28, y + 34, eyebrow.upper(), size=11, weight=800, fill=BLUE, spacing="1.8")
        if title:
            self.text(x + 28, y + 65, title, size=23, weight=750, fill=INK)

    def check_mark(self, x, y, color=GREEN, sw=3.2):
        self.path(f"M {x} {y + 8} L {x + 8} {y + 16} L {x + 24} {y}", stroke=color, sw=sw)

    def finish(self):
        defs = "<defs>" + "".join(self.defs) + "</defs>"
        body = "".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
            f'viewBox="0 0 {self.width} {self.height}" role="img" aria-labelledby="title desc">'
            f'<title id="title">{escape(self.title)}</title><desc id="desc">{escape(self.description)}</desc>'
            f'{defs}<rect width="{self.width}" height="{self.height}" rx="28" fill="{BG}"/>{body}</svg>\n'
        )


def header(svg, eyebrow, title, subtitle):
    svg.text(64, 58, eyebrow.upper(), size=12, weight=800, fill=BLUE, spacing="2.2")
    svg.text(64, 105, title, size=43, weight=780, fill=INK)
    svg.text(64, 139, subtitle, size=18, weight=430, fill=MUTED)


def footer(svg, text_value):
    svg.line(64, svg.height - 52, svg.width - 64, svg.height - 52, color=FAINT, sw=1)
    svg.text(64, svg.height - 22, text_value, size=12.5, weight=500, fill=MUTED)


def byte_bar(svg, x, y, w, h, total, segments):
    cursor = x
    for label, length, color in segments:
        width = max(1.5, w * length / total)
        svg.rect(cursor, y, width, h, rx=0, fill=color)
        cursor += width
    svg.rect(x, y, w, h, rx=9, fill="none", stroke=INK, sw=1.1, opacity=0.32)


def fig1(build, verification, root):
    image_id = "document_like" if any(im["image_id"] == "document_like" for im in build["images"]) else build["images"][0]["image_id"]
    image = next(im for im in build["images"] if im["image_id"] == image_id)
    vim = verification["images"][image_id]
    jc = image["variants"]["JC"]
    ja = image["variants"]["JA"]
    vjc = vim["variants"]["JC"]
    vja = vim["variants"]["JA"]
    raster_hash = image["canonical_raster_sha256"]
    thumb_path = root / "artifacts" / image["variants"]["J0"]["path"]
    thumb = image_data_uri(thumb_path, width=300)
    thumb_small = image_data_uri(thumb_path, width=176)

    svg = Svg(1600, 940, "Same decoded pixels, different container bytes", "Experimental logic of the container-ghosts paired variant design")
    header(
        svg,
        "Container Ghosts / experimental logic",
        "Same decoded pixels. Different container bytes.",
        "The treatment is non-rendering file structure; the decoded raster is held constant.",
    )

    svg.panel(64, 178, 356, 586, title="Canonical raster", eyebrow="Held constant")
    svg.rect(98, 246, 288, 288, rx=22, fill=GRAY_PALE, stroke=FAINT, sw=1)
    svg.image(104, 252, 276, 276, thumb)
    svg.text(112, 568, f"development stimulus: {image_id}", size=14, weight=650, fill=INK)
    svg.text(112, 596, "448 x 448 RGB, decoded from canonical J0", size=13.5, fill=MUTED)
    svg.text(112, 635, "raster SHA-256", size=11, weight=800, fill=MUTED, spacing="1.4")
    svg.text(112, 662, short_hash(raster_hash, 18, 12), size=15, family=MONO, weight=650, fill=BLUE_DARK)
    svg.pill(98, 699, 172, "PIXELS INVARIANT", BLUE_PALE, BLUE_DARK, height=36)

    junction_x = 462
    svg.line(420, 396, junction_x, 396, color=BLUE, sw=3, opacity=0.8)
    svg.line(junction_x, 396, 510, 315, color=BLUE, sw=3, marker="blue")
    svg.line(junction_x, 396, 510, 595, color=BLUE, sw=3, marker="blue")
    svg.circle(junction_x, 396, 7, fill=BLUE)

    def variant_card(y, code, title, semantic, meta, vmeta, meta_color, meta_pale):
        svg.panel(520, y, 1016, 286, eyebrow="Container variant", title=f"{code} / {title}")
        svg.text(548, y + 100, semantic, size=15, weight=500, fill=MUTED)
        total = meta["byte_length"]
        inv = vmeta["inventory"]
        app1 = inv["payload_lengths"].get("APP1", 0)
        com = inv["payload_lengths"].get("COM", 0)
        segment_count = inv["counts"].get("APP1", 0) + inv["counts"].get("COM", 0)
        insertion = app1 + com + 4 * segment_count
        critical = total - insertion
        baseline_len = image["variants"]["J0"]["byte_length"]
        if critical != baseline_len:
            raise ValueError(f"{code} insertion accounting differs from J0 baseline: {critical} != {baseline_len}")

        svg.rect(544, y + 116, 96, 96, rx=16, fill=GRAY_PALE, stroke=FAINT, sw=1)
        svg.image(548, y + 120, 88, 88, thumb_small)
        svg.circle(632, y + 204, 12, fill=GREEN)
        svg.check_mark(623, y + 196, color=CARD, sw=2.4)
        svg.text(592, y + 233, "decodes to the", size=10.5, weight=650, fill=GREEN, anchor="middle")
        svg.text(592, y + 248, "identical raster", size=10.5, weight=650, fill=GREEN, anchor="middle")

        byte_bar(
            svg,
            668,
            y + 132,
            570,
            48,
            total,
            [
                ("decode-critical structure + scan", critical, BLUE),
                ("metadata + padding", insertion, meta_color),
            ],
        )
        svg.text(668, y + 210, "JPEG bytes, linear scale", size=11.5, weight=700, fill=MUTED, spacing="1.1")
        svg.text(668, y + 235, f"{fmt_int(critical)} B critical structure + entropy-coded scan", size=13, fill=BLUE_DARK, weight=650)
        svg.text(1238, y + 235, f"{fmt_int(insertion)} B inserted segments/padding", size=13, fill=meta_color, weight=650, anchor="end")

        zoom_x = 1258
        svg.line(1238, y + 156, zoom_x, y + 128, color=GRAY, sw=1.4, dash="4 5")
        svg.line(1238, y + 156, zoom_x, y + 226, color=GRAY, sw=1.4, dash="4 5")
        svg.rect(zoom_x, y + 120, 248, 116, rx=16, fill=meta_pale, stroke=meta_color, sw=1.3)
        svg.text(zoom_x + 18, y + 150, "inserted region", size=11, weight=800, fill=meta_color, spacing="1.2")
        overhead = 4 * segment_count
        app_width = 206 * (app1 / max(insertion, 1))
        com_width = 206 * (com / max(insertion, 1))
        overhead_width = max(1.5, 206 - app_width - com_width)
        svg.rect(zoom_x + 18, y + 166, max(2, app_width), 26, rx=5, fill=meta_color)
        if com_width > 1:
            svg.rect(zoom_x + 18 + app_width, y + 166, max(2, com_width), 26, rx=5, fill=GRAY)
        svg.rect(zoom_x + 18 + app_width + com_width, y + 166, overhead_width, 26, rx=5, fill=FAINT)
        svg.text(zoom_x + 18, y + 211, f"APP1 {fmt_int(app1)} B    COM {fmt_int(com)} B", size=11.5, weight=650, fill=DARK)
        svg.text(zoom_x + 18, y + 228, f"segment headers {fmt_int(overhead)} B", size=10.5, weight=600, fill=MUTED)
        svg.text(668, y + 265, "file SHA-256", size=11, weight=800, fill=MUTED, spacing="1.2")
        svg.text(782, y + 265, short_hash(meta["sha256"], 18, 12), size=13.5, family=MONO, weight=650, fill=INK)
        svg.pill(1320, y + 33, 164, f"{fmt_int(total)} BYTES", GRAY_PALE, DARK, height=34)

    variant_card(178, "JC", "camera provenance", "EXIF/XMP camera fixture inserted by binary segment splicing.", jc, vjc, PURPLE, PURPLE_PALE)
    variant_card(478, "JA", "AI provenance", "Parallel AI-generation fixture; same canary, controlled semantics.", ja, vja, TEAL, TEAL_PALE)

    strip_y = 796
    svg.rect(64, strip_y, 1472, 92, rx=22, fill=DARK)
    svg.text(96, strip_y + 35, "verification outcome", size=11, weight=800, fill="#B9C6D6", spacing="1.8")
    svg.check_mark(96, strip_y + 48, color="#63D6A8", sw=3)
    svg.text(132, strip_y + 66, "raster hash identical", size=17, weight=720, fill=CARD)
    svg.text(408, strip_y + 66, "file hashes distinct", size=17, weight=720, fill=CARD)
    svg.text(670, strip_y + 66, "JPEG scan/DQT/DHT/SOF byte-identical", size=17, weight=720, fill=CARD)
    svg.text(1166, strip_y + 66, f"length delta {vjc['byte_length'] - vja['byte_length']} B", size=17, weight=760, fill="#8EBDFF")
    footer(svg, "Generated from artifacts/build_manifest.json and artifacts/verification_manifest.json. Image shown is a project-generated development stimulus, not final study corpus.")
    return svg.finish()


def fig2(build, verification):
    from ghosts.probe_harness import palindromic_schedule

    sequence = palindromic_schedule("dryrun|openai|abba|color_fields")
    svg = Svg(1600, 980, "Paired measurement design", "Palindromic order, exact-repeat baseline, decision logic, and exact statistics")
    header(
        svg,
        "Container Ghosts / measurement design",
        "A paired measurement, not a vibe test.",
        "Cross-container divergence is meaningful only after subtracting exact-byte-repeat instability.",
    )

    svg.panel(64, 172, 1472, 254, eyebrow="Ordering control", title="Seeded palindromic sequence")
    start_x = 102
    tile_w = 104
    gap = 16
    colors = {
        "J0": (BLUE_PALE, BLUE_DARK), "JXMP": (BLUE_PALE, BLUE_DARK), "JCOM": (BLUE_PALE, BLUE_DARK),
        "P0": (TEAL_PALE, TEAL), "P1": (TEAL_PALE, TEAL), "PT": (TEAL_PALE, TEAL),
        "JC": (PURPLE_PALE, PURPLE), "JA": (GREEN_PALE, GREEN),
    }
    y = 260
    centers = []
    for i, variant in enumerate(sequence):
        x = start_x + i * (tile_w + gap)
        centers.append(x + tile_w / 2)
        fill, stroke = colors.get(variant, (GRAY_PALE, GRAY))
        svg.rect(x, y, tile_w, 68, rx=14, fill=fill, stroke=stroke, sw=1.4)
        svg.text(x + tile_w / 2, y + 32, variant, size=20, weight=800, fill=stroke, anchor="middle")
        svg.text(x + tile_w / 2, y + 53, f"call {i + 1}", size=10.5, weight=650, fill=MUTED, anchor="middle")
    tile_bottom = y + 68
    for pair in range(6):
        left = centers[pair]
        right = centers[11 - pair]
        depth = tile_bottom + 10 + (5 - pair) * 9
        svg.path(f"M {left} {tile_bottom + 3} L {left} {depth} L {right} {depth} L {right} {tile_bottom + 3}", stroke=GRAY, sw=1.7, opacity=0.62, linejoin="round")
    svg.text(784, 412, "example sequence used by the dry-run harness — nested brackets connect exact-byte mirror repetitions", size=12.5, fill=MUTED, anchor="middle")
    svg.pill(1210, 205, 278, "JC/JA ADJACENT IN FIRST HALF", PURPLE_PALE, PURPLE, height=32, size=11.5)

    row_y = 444
    card_w = 466
    cards = [
        (64, "X / cross-container flip", "Compare occurrence-matched answers across two raster-identical container variants.", "Does changing only container bytes change behavior?", BLUE),
        (567, "R / exact-repeat flip", "Compare two transmissions of the exact same file in mirrored positions.", "How unstable is the endpoint without any treatment?", TEAL),
        (1070, "Delta / excess flip", "Paired discordance: (n10 - n01) / n. Positive means container-associated excess.", "The primary confirmatory quantity.", PURPLE),
    ]
    for x, title, body, question, color in cards:
        svg.panel(x, row_y, card_w, 222)
        svg.rect(x + 24, row_y + 26, 7, 58, rx=3.5, fill=color)
        svg.text(x + 48, row_y + 49, title, size=21, weight=770, fill=INK)
        svg.text_block(x + 48, row_y + 86, body, 39, size=13.6, weight=480, fill=MUTED, line_height=20)
        svg.text_block(x + 48, row_y + 154, question, 42, size=13.2, weight=650, fill=color, line_height=19)
        if x == 64:
            svg.text(x + 48, row_y + 202, "Y(JC,r) != Y(JA,r)", size=18, weight=700, family=MONO, fill=DARK)
        elif x == 567:
            svg.text(x + 48, row_y + 202, "Y(v,1) != Y(v,2)", size=18, weight=700, family=MONO, fill=DARK)
        else:
            svg.text(x + 48, row_y + 202, "exact one-sided McNemar", size=17, weight=700, family=MONO, fill=DARK)

    svg.text(64, 710, "Decision logic", size=26, weight=780, fill=INK)
    outcomes = [
        (64, "Positive", "Excess paired flips, provenance shift, or exact canary emission.", "Evidence that a production ingestion pipeline exposes non-rendering bytes.", GREEN, GREEN_PALE),
        (567, "Bounded null", "Effect bounded inside the frozen equivalence margin; positive controls pass.", "Evidence consistent with stripping or ignoring metadata at the stated sensitivity.", BLUE, BLUE_PALE),
        (1070, "Inconclusive", "Positive controls fail, parse validity collapses, or exact-repeat noise is too high.", "An instrument limitation. Not evidence of absence.", RED, RED_PALE),
    ]
    for x, label, criterion, meaning, color, pale in outcomes:
        svg.panel(x, 738, 466, 174)
        svg.pill(x + 28, 762, 142, label.upper(), pale, color, height=32, size=11.5)
        criterion_lines = svg.text_block(x + 28, 818, criterion, 43, size=13.2, weight=650, fill=INK, line_height=18)
        meaning_y = 818 + criterion_lines * 18 + 9
        svg.text_block(x + 28, meaning_y, meaning, 48, size=12.2, weight=470, fill=MUTED, line_height=16)

    footer(svg, "Statistics in scope: exact McNemar discordance, paired bootstrap intervals, Clopper-Pearson canary bounds, Holm multiplicity control. No LLM judge.")
    return svg.finish()


def horizontal_bar(svg, x, y, max_w, value, max_value, color, label, value_label, height=42):
    svg.text(x, y - 10, label, size=14, weight=680, fill=INK)
    width = max(2, max_w * value / max_value)
    svg.rect(x, y, max_w, height, rx=9, fill=GRAY_PALE)
    svg.rect(x, y, width, height, rx=9, fill=color)
    svg.text(x + max_w + 14, y + height / 2 + 5, value_label, size=14, weight=750, fill=color)


def fig3(build, verification):
    ratios = []
    for image in build["images"]:
        pc0 = image["variants"]["PC0"]["byte_length"]
        pc9 = image["variants"]["PC9"]["byte_length"]
        ratios.append((pc0 / pc9, image["image_id"], pc0, pc9))
    max_ratio, ratio_id, pc0_len, pc9_len = max(ratios)
    min_ratio = min(r[0] for r in ratios)
    example = next(im for im in build["images"] if im["image_id"] == "color_fields") if any(im["image_id"] == "color_fields" for im in build["images"]) else build["images"][0]
    png_len = example["variants"]["P0"]["byte_length"]
    jc_len = example["variants"]["JC"]["byte_length"]
    ja_len = example["variants"]["JA"]["byte_length"]
    deltas = build["padding_policy"]["group_deltas"]
    image_count = len(build["images"])
    zero_png = sum(
        1 for item in verification["images"].values()
        if item["group_byte_length_deltas"]["png_core_exact"] == 0
    )
    zero_jpeg = sum(
        1 for item in verification["images"].values()
        if item["group_byte_length_deltas"]["jpeg_provenance_exact"] == 0
    )

    svg = Svg(1600, 960, "Byte-length control", "Why byte-length matching is required and the zero-delta result achieved by the artifact")
    header(
        svg,
        "Container Ghosts / confound control",
        "Lossless bytes are not neutral unless length is controlled.",
        "A pipeline can react to file size even when every decoded pixel is unchanged.",
    )

    panel_y = 184
    panel_h = 622
    svg.panel(64, panel_y, 456, panel_h, eyebrow="Failure mode", title="Representation changes size")
    svg.text(92, 340, "129x", size=56, weight=820, fill=RED)
    svg.text(92, 374, "same pixels, lossless re-encode", size=15, weight=650, fill=INK)
    svg.text(92, 404, "forensics guardrail example", size=13, fill=MUTED)
    svg.line(92, 438, 456, 438, color=GRID, sw=1)
    svg.text(92, 468, "same pixels, linear byte scale", size=11.5, weight=700, fill=MUTED, spacing="1.1")
    svg.rect(92, 482, 3, 26, rx=1.5, fill=RED)
    svg.text(104, 500, "477 B compact lossless encoding", size=13, weight=680, fill=RED)
    svg.rect(92, 522, 368, 26, rx=6, fill=RED, opacity=0.82)
    svg.text(104, 540, "~61 KB different lossless encoding", size=13, weight=680, fill=CARD)
    svg.rect(92, 646, 368, 104, rx=18, fill=RED_PALE)
    svg.text(116, 683, "If length differs, size-dependent", size=15, weight=700, fill=RED)
    svg.text(116, 710, "preprocessing becomes a treatment.", size=15, weight=700, fill=RED)

    svg.panel(544, panel_y, 456, panel_h, eyebrow="Observed artifact behavior", title="Re-encoding swings bytes")
    svg.text(572, 340, f"{max_ratio:.2f}x", size=50, weight=820, fill=BLUE)
    svg.text(572, 374, f"maximum deflate-0 / deflate-9 ratio ({ratio_id})", size=14.5, weight=650, fill=INK)
    svg.text(572, 404, f"range across six development images: {min_ratio:.2f}x to {max_ratio:.2f}x", size=13, fill=MUTED)
    horizontal_bar(svg, 572, 472, 244, pc0_len, pc0_len, BLUE, "PC0 / deflate level 0", fmt_int(pc0_len) + " B", height=44)
    horizontal_bar(svg, 572, 588, 244, pc9_len, pc0_len, TEAL, "PC9 / deflate level 9", fmt_int(pc9_len) + " B", height=44)
    svg.text_block(572, 704, "These PC/PF/PS exploration arms are explicitly marked byte_length_factor=true; they are not hidden as pure representation-only contrasts.", 46, size=13.2, weight=600, fill=MUTED, line_height=21)

    svg.panel(1024, panel_y, 512, panel_h, eyebrow="Primary control", title="Exact padding removes the confound")
    svg.text(1052, 340, "0 B", size=56, weight=820, fill=GREEN)
    svg.text(1052, 374, "maximum byte-length delta in both exact groups", size=15, weight=650, fill=INK)

    svg.text(1052, 418, "example image: " + example["image_id"], size=12.5, weight=800, fill=MUTED, spacing="1.1")
    pngs = ["P0", "P1", "PT", "PTC", "PTA"]
    x0 = 1052
    for i, name in enumerate(pngs):
        x = x0 + i * 91
        svg.rect(x, 442, 78, 58, rx=12, fill=TEAL_PALE, stroke=TEAL, sw=1.2)
        svg.text(x + 39, 467, name, size=16, weight=800, fill=TEAL, anchor="middle")
        svg.text(x + 39, 488, fmt_int(png_len), size=9.5, weight=700, fill=DARK, anchor="middle")
    svg.text(1052, 534, "PNG core group: five containers, one exact length", size=13, weight=600, fill=MUTED)

    for i, (name, length, color, pale) in enumerate([
        ("JC", jc_len, PURPLE, PURPLE_PALE),
        ("JA", ja_len, GREEN, GREEN_PALE),
    ]):
        x = 1052 + i * 154
        svg.rect(x, 572, 136, 64, rx=12, fill=pale, stroke=color, sw=1.2)
        svg.text(x + 68, 599, name, size=17, weight=800, fill=color, anchor="middle")
        svg.text(x + 68, 621, fmt_int(length) + " B", size=10.5, weight=700, fill=DARK, anchor="middle")
    svg.rect(1362, 572, 128, 64, rx=12, fill=GREEN_PALE, stroke=GREEN, sw=1.2)
    svg.text(1426, 599, f"delta {jc_len - ja_len} B", size=13.5, weight=800, fill=GREEN, anchor="middle")
    svg.text(1426, 621, "camera vs AI", size=10.5, weight=650, fill=MUTED, anchor="middle")

    svg.rect(1052, 674, 456, 104, rx=18, fill=GREEN_PALE)
    svg.text(1076, 706, f"{zero_png}/{image_count} PNG and {zero_jpeg}/{image_count} JPEG groups at zero delta", size=14, weight=760, fill=GREEN)
    svg.text(1076, 734, f"{len(pngs) * image_count} exact-group PNG files and {2 * image_count} provenance JPEG files", size=13.5, weight=620, fill=DARK)
    svg.text(1076, 760, "padding uses neutral PNG tEXt or JPEG COM filler", size=13.5, weight=620, fill=DARK)

    svg.rect(64, 838, 1472, 66, rx=18, fill=CARD, stroke=FAINT, sw=1.2)
    svg.text(92, 879, "Honest boundary: stripped-J0 insertion contrasts retain inserted byte length as an explicit experimental factor; exact matching is enforced where the claim requires it.", size=14.5, weight=620, fill=INK)
    footer(svg, "Sources: docs/EXTRACTIONS.md guardrail; artifacts/build_manifest.json and artifacts/verification_manifest.json for all artifact measurements.")
    return svg.finish()


def fig4(build, verification, dryrun):
    svg = Svg(1600, 930, "Validated instrument pipeline", "End-to-end artifact pipeline and validation status before live model execution")
    header(
        svg,
        "Container Ghosts / instrument",
        "The artifact is built as a measurement instrument.",
        "Every stage is file-based, hash-audited, deterministic, and executable without hosted API credentials.",
    )

    stages = [
        ("1", "Select / generate", ["six deterministic", "development stimuli", "licensed corpus drop-in"], BLUE, BLUE_PALE),
        ("2", "Canonicalize", ["JPEG q95, 4:4:4", "non-progressive", "decode once -> raster R"], TEAL, TEAL_PALE),
        ("3", "Container surgery", ["PNG chunk insertion", "JPEG segment splicing", "neutral byte padding"], PURPLE, PURPLE_PALE),
        ("4", "Verify invariance", ["Pillow + OpenCV", "inventory exclusions", "mutation self-test"], GREEN, GREEN_PALE),
        ("5", "Probe harness", ["raw bytes only", "ABBA order + nonces", "dry-run mock endpoint"], BLUE, BLUE_PALE),
        ("6", "Score exactly", ["strict grammar", "McNemar + bootstrap", "Holm correction"], TEAL, TEAL_PALE),
    ]
    x_positions = [64, 314, 564, 814, 1064, 1314]
    y = 204
    w = 222
    h = 278
    for idx, ((num, title, lines, color, pale), x) in enumerate(zip(stages, x_positions)):
        svg.rect(x, y, w, h, rx=22, fill=CARD, stroke=FAINT, sw=1.2)
        svg.circle(x + 38, y + 42, 22, fill=pale, stroke=color, sw=1.3)
        svg.text(x + 38, y + 49, num, size=17, weight=800, fill=color, anchor="middle")
        svg.text(x + 24, y + 94, title, size=19, weight=780, fill=INK)
        for j, line in enumerate(lines):
            svg.text(x + 24, y + 139 + j * 31, line, size=13.5, weight=520, fill=MUTED)
        svg.rect(x + 22, y + 230, 76, 24, rx=12, fill=pale)
        svg.text(x + 60, y + 247, "local", size=10.5, weight=800, fill=color, anchor="middle")
        if idx < len(stages) - 1:
            svg.line(x + w + 8, y + 139, x + w + 42, y + 139, color=BLUE, sw=2.4, marker="blue")

    total_images = len(build["images"])
    total_variants = sum(len(im["variants"]) for im in build["images"])
    pairwise = verification["pairwise_totals"]
    mutation = verification.get("mutation_test", {})
    metrics = [
        ("artifact scope", f"{total_images} images / {total_variants} variants", BLUE),
        ("raster comparisons", f"{fmt_int(pairwise['pillow_pairs_compared'])} Pillow pairs / 0 failures", GREEN),
        ("second decoder", f"{fmt_int(pairwise['png_opencv_pairs_compared'])} PNG + {fmt_int(pairwise['jpeg_opencv_pairs_compared'])} JPEG pairs", TEAL),
        ("negative control", "one-pixel mutation caught", PURPLE),
        ("mock harness", f"{dryrun['calls']} calls / {dryrun['live_calls']} live", BLUE),
    ]
    svg.text(64, 558, "VERIFICATION LEDGER", size=13, weight=800, fill=BLUE, spacing="1.8")
    metric_y = 586
    metric_w = 278
    for i, (label, value, color) in enumerate(metrics):
        x = 64 + i * 300
        svg.rect(x, metric_y, metric_w, 112, rx=20, fill=CARD, stroke=FAINT, sw=1.2)
        svg.rect(x + 20, metric_y + 22, 6, 46, rx=3, fill=color)
        svg.text(x + 42, metric_y + 39, label.upper(), size=10.5, weight=800, fill=MUTED, spacing="1.2")
        svg.text(x + 42, metric_y + 75, value, size=16, weight=760, fill=INK)

    status_y = 744
    svg.rect(64, status_y, 1472, 110, rx=24, fill=DARK)
    svg.text(96, status_y + 39, "CURRENT STATUS", size=11, weight=850, fill="#B9C6D6", spacing="2")
    svg.text(96, status_y + 76, "Instrument validated locally. No production model calls have been executed.", size=23, weight=760, fill=CARD)
    svg.pill(1220, status_y + 33, 272, "PRE-RESULTS ARTIFACT", BLUE_PALE, BLUE_DARK, height=42, size=12.5)
    svg.text(96, status_y + 98, "Execution awaits paid API access, frozen endpoint snapshots, and final pre-execution locks.", size=13.5, weight=500, fill="#C9D5E4")
    footer(svg, f"Verification status: {verification['status']}; mutation control: {mutation.get('status', 'not run')}; dry run: {dryrun['status']}. Generated from repository manifests.")
    return svg.finish()


def generate(root, out_dir):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    build, verification, dryrun = load_facts(root)
    validate_facts(build, verification, dryrun)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures = {
        "fig1-experimental-logic.svg": fig1(build, verification, root),
        "fig2-measurement-design.svg": fig2(build, verification),
        "fig3-byte-length-control.svg": fig3(build, verification),
        "fig4-instrument-pipeline.svg": fig4(build, verification, dryrun),
    }
    for name, content in figures.items():
        (out_dir / name).write_text(content)
    return sorted(figures)


def main():
    parser = argparse.ArgumentParser(description="Generate repository infographics from verified artifact manifests.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.out or root / "docs" / "figures"
    try:
        names = generate(root, out)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for name in names:
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
