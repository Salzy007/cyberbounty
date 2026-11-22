"""Единый цветокор для фото с Unsplash (лицензия Unsplash, атрибуция не обязательна) -> web/img/*.jpg
Исходники лежат в tools/raw (в git не нужны). Запуск: .venv\Scripts\python tools\grade_photos.py
"""
from pathlib import Path
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

RAW = Path(__file__).resolve().parent / "raw"
OUT = Path(__file__).resolve().parent.parent / "web" / "img"
# имя: (файл Unsplash, область обрезки в долях (л, в, п, н), ширина результата)
JOBS = {
    "hero": ("fK5Oomnc-Wk", (0, 0, 1, 1), 1800),
    "about": ("GVbd5btrqeA", (0, 0, 1, 1), 1200),
    "standard": ("2rQoMZLVXHc", (0, 0.05, 1, 0.95), 1400),
    "vip": ("GVbd5btrqeA", (0.5, 0.08, 1.0, 0.96), 1000),
    "tournament": ("ecB66ugFE0I", (0, 0, 1, 1), 1200),
    "lounge": ("caNzzoxls8Q", (0, 0, 1, 1), 900),
    "hookah": ("Exvx8zTojVQ", (0, 0, 1, 1), 900),
    "bar": ("07RXPZnWe60", (0, 0, 1, 1), 1400),
}
STOPS = [(0.0, (4, 5, 14)), (0.35, (30, 22, 120)), (0.7, (70, 110, 235)), (1.0, (150, 245, 255))]  # тени -> фиолет -> синий -> циан


def gradient_lut():
    lut = []
    for i in range(256):
        t = i / 255
        for (a, ca), (b, cb) in zip(STOPS, STOPS[1:]):
            if t <= b:
                k = (t - a) / (b - a)
                lut.append(tuple(int(ca[j] + (cb[j] - ca[j]) * k) for j in range(3)))
                break
    return lut


def grade(im: Image.Image) -> Image.Image:
    im = ImageOps.autocontrast(im.convert("RGB"), cutoff=1)
    lum = ImageOps.autocontrast(im.convert("L"), cutoff=1)
    lut = gradient_lut()
    mapped = Image.merge("RGB", [lum.point([c[j] for c in lut]) for j in range(3)])
    mixed = Image.blend(ImageEnhance.Color(im).enhance(1.15), mapped, 0.62)          # единый тон + живые цвета
    mixed = ImageEnhance.Contrast(mixed).enhance(1.12)
    w, h = mixed.size                                                                    # лёгкая виньетка
    vig = Image.radial_gradient("L").resize((w, h)).point(lambda v: 255 - int(max(0, v - 90) * 0.9))
    mixed = ImageChops.multiply(mixed, Image.merge("RGB", [vig] * 3))
    return mixed.filter(ImageFilter.UnsharpMask(1.2, 60, 3))


for name, (src, (l, t, r, b), width) in JOBS.items():
    im = Image.open(RAW / f"{src}.jpg")
    W, H = im.size
    im = im.crop((int(W * l), int(H * t), int(W * r), int(H * b)))
    if im.width > width:
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    grade(im).save(OUT / f"{name}.jpg", quality=80, optimize=True, progressive=True)
    print(name, im.size)
