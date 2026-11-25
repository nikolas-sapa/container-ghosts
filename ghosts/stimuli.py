import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = 448


def _noise(rng, shape, amplitude=5):
    return rng.integers(-amplitude, amplitude + 1, shape, dtype=np.int16)


def _finish(arr):
    return np.clip(arr, 0, 255).astype(np.uint8)


def controlled_text() -> np.ndarray:
    rng = np.random.default_rng(101)
    arr = np.full((SIZE, SIZE, 3), (232, 229, 218), dtype=np.int16)
    arr += _noise(rng, arr.shape, 4)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    font_big = ImageFont.load_default(size=42)
    font_small = ImageFont.load_default(size=22)
    d.rectangle((34, 34, 414, 130), fill=(245, 244, 238), outline=(50, 50, 50), width=3)
    d.text((58, 55), "SPECIMEN 042", font=font_big, fill=(24, 28, 34))
    d.text((60, 145), "controlled rendering", font=font_small, fill=(70, 70, 70))
    for y in (205, 242, 279, 316):
        d.line((58, y, 390, y), fill=(80, 80, 80), width=3)
    d.rectangle((58, 345, 180, 405), fill=(24, 94, 160))
    d.ellipse((220, 345, 300, 425), fill=(190, 45, 48))
    d.polygon([(335, 405), (390, 345), (425, 405)], fill=(28, 130, 82))
    return np.asarray(im).copy()


def color_fields() -> np.ndarray:
    rng = np.random.default_rng(202)
    arr = np.zeros((SIZE, SIZE, 3), dtype=np.int16)
    arr[:, :, 0] = 38
    arr[:, :, 1] = 112
    arr[:, :, 2] = 150
    xgrad = np.linspace(-18, 18, SIZE, dtype=np.int16)[None, :, None]
    arr += xgrad + _noise(rng, arr.shape, 3)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    d.rectangle((42, 52, 210, 224), fill=(205, 55, 52))
    d.rectangle((238, 52, 406, 224), fill=(232, 196, 48))
    d.rectangle((42, 252, 406, 392), fill=(38, 138, 86))
    for x in range(58, 390, 24):
        d.line((x, 252, x + 34, 392), fill=(25, 100, 66), width=5)
    return np.asarray(im).copy()


def geometric_scene() -> np.ndarray:
    rng = np.random.default_rng(303)
    arr = np.zeros((SIZE, SIZE, 3), dtype=np.int16)
    arr[:250] = (170, 205, 220)
    arr[250:] = (92, 132, 92)
    arr += _noise(rng, arr.shape, 2)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    d.ellipse((318, 34, 398, 114), fill=(238, 190, 64))
    d.polygon([(0, 252), (120, 118), (245, 252)], fill=(95, 105, 112))
    d.polygon([(128, 252), (260, 146), (410, 252)], fill=(75, 88, 98))
    d.rectangle((58, 280, 170, 410), fill=(155, 82, 58))
    d.rectangle((92, 310, 134, 354), fill=(210, 222, 225))
    d.ellipse((250, 292, 372, 414), fill=(64, 62, 126))
    d.line((0, 252, SIZE, 252), fill=(52, 95, 55), width=4)
    return np.asarray(im).copy()


def document_like() -> np.ndarray:
    rng = np.random.default_rng(404)
    arr = np.full((SIZE, SIZE, 3), (196, 198, 196), dtype=np.int16)
    arr += _noise(rng, arr.shape, 3)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    d.rectangle((62, 22, 386, 426), fill=(244, 244, 240), outline=(110, 110, 110), width=2)
    d.rectangle((88, 52, 260, 72), fill=(65, 68, 72))
    for i, width in enumerate((270, 250, 278, 198)):
        d.rectangle((88, 102 + i * 24, 88 + width, 112 + i * 24), fill=(150, 152, 150))
    for row in range(5):
        y = 226 + row * 30
        d.line((88, y, 360, y), fill=(120, 120, 120), width=2)
    for x in (88, 178, 268, 360):
        d.line((x, 226, x, 376), fill=(120, 120, 120), width=2)
    d.rectangle((88, 392, 178, 406), fill=(42, 96, 150))
    return np.asarray(im).copy()


def object_arrangement() -> np.ndarray:
    rng = np.random.default_rng(505)
    arr = np.zeros((SIZE, SIZE, 3), dtype=np.int16)
    arr[:] = (168, 154, 132)
    arr[285:] = (105, 82, 62)
    arr += _noise(rng, arr.shape, 3)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    d.ellipse((62, 252, 176, 370), fill=(38, 92, 152))
    d.ellipse((82, 230, 156, 278), fill=(70, 130, 190))
    d.rectangle((218, 150, 292, 344), fill=(185, 46, 52))
    d.ellipse((218, 128, 292, 172), fill=(220, 86, 88))
    d.ellipse((218, 322, 292, 366), fill=(128, 32, 38))
    d.polygon([(330, 335), (376, 160), (420, 335)], fill=(38, 122, 80))
    d.ellipse((338, 310, 412, 382), fill=(30, 92, 62))
    d.line((0, 285, SIZE, 285), fill=(84, 63, 46), width=5)
    return np.asarray(im).copy()


def woven_texture() -> np.ndarray:
    x = np.arange(SIZE, dtype=np.float64)[None, :]
    y = np.arange(SIZE, dtype=np.float64)[:, None]
    red = 128 + 72 * np.sin(x / 19.0) + 24 * np.sin((x + y) / 43.0)
    green = 128 + 68 * np.cos(y / 23.0) + 20 * np.sin((x - y) / 37.0)
    blue = 128 + 55 * np.sin((x + 2 * y) / 31.0)
    arr = np.stack(np.broadcast_arrays(red, green, blue), axis=2)
    rng = np.random.default_rng(606)
    arr += rng.normal(0, 2.0, arr.shape)
    im = Image.fromarray(_finish(arr), "RGB")
    d = ImageDraw.Draw(im)
    for pos in range(-SIZE, SIZE * 2, 56):
        d.line((pos, 0, pos + SIZE, SIZE), fill=(42, 48, 58), width=7)
    d.rectangle((148, 148, 300, 300), outline=(238, 230, 210), width=8)
    return np.asarray(im).copy()


GENERATORS = {
    "controlled_text": controlled_text,
    "color_fields": color_fields,
    "geometric_scene": geometric_scene,
    "document_like": document_like,
    "object_arrangement": object_arrangement,
    "woven_texture": woven_texture,
}

PROBE_LABELS = {
    "controlled_text": {"q1": "color", "count_or_color_answer": "blue rectangle", "caption_correct": "A rendered specimen card with text and colored shapes", "caption_wrong": "A natural outdoor landscape with people"},
    "color_fields": {"q1": "color", "count_or_color_answer": "red rectangle", "caption_correct": "Large flat color fields with diagonal green striping", "caption_wrong": "A close-up photograph of a face"},
    "geometric_scene": {"q1": "count", "count_or_color_answer": "two buildings or large foreground objects", "caption_correct": "A stylized geometric landscape with mountains and objects", "caption_wrong": "A dense crowd in a city street"},
    "document_like": {"q1": "count", "count_or_color_answer": "five table rows", "caption_correct": "A document-like page with lines and a table", "caption_wrong": "A forest trail in heavy fog"},
    "object_arrangement": {"q1": "count", "count_or_color_answer": "three arranged objects", "caption_correct": "Three face-free stylized objects on a surface", "caption_wrong": "A plate of food on a table"},
    "woven_texture": {"q1": "color", "count_or_color_answer": "multicolored woven texture", "caption_correct": "A woven multicolored texture with a pale square outline", "caption_wrong": "A handwritten letter on white paper"},
}


def generate_all() -> dict[str, np.ndarray]:
    return {name: fn() for name, fn in GENERATORS.items()}
