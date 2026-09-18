"""
renderer.py - Turn CarouselContent into 1080x1350 JPEG slides.

The slides are an HTML/CSS template (templates/carousel.html.j2) screenshotted
by headless Chromium. Fonts and images load from local files, so the output
doesn't depend on network access or on which fonts the server has installed.

Instagram accepts JPEG only, so Chromium writes JPEG directly.
"""
import base64
import io
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.async_api import async_playwright

from instagram.models import CarouselContent
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
ASSETS = HERE / "assets"
SLIDE_W, SLIDE_H = 1080, 1350


def _find_asset(stem: str) -> Optional[Path]:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = ASSETS / f"{stem}{ext}"
        if p.exists():
            return p
    return None


LOGO_HEIGHT = 52  # px on the 1080-wide slide


def _png_size(path: Path) -> Optional[tuple[int, int]]:
    """Width/height from a PNG's IHDR chunk, without an imaging library."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def render_html(content: CarouselContent) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["j2", "html"]))
    headshot = _find_asset("headshot")
    logo = _find_asset("logo")
    size = _png_size(logo) if logo else None
    logo_w = round(LOGO_HEIGHT * size[0] / size[1]) if size else LOGO_HEIGHT * 4
    return env.get_template("carousel.html.j2").render(
        logo_w=logo_w,
        logo_h=LOGO_HEIGHT,
        c=content,
        fonts=(ASSETS / "fonts").as_uri(),
        headshot=headshot.as_uri() if headshot else "",
        # Inlined, not file://: CSS masks are fetched in CORS mode, which
        # Chromium refuses for local files, so a file:// mask renders blank.
        logo=f"data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}" if logo else "",
        firm=settings.instagram_firm_name,
    )


async def render_slides(content: CarouselContent, out_dir: Path, quality: int = 95) -> List[Path]:
    """Render every slide to out_dir/slide-N.jpg and return the paths in order."""
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "carousel.html"
    html_path.write_text(render_html(content), encoding="utf-8")

    paths: List[Path] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H}, device_scale_factor=1)
            await page.goto(html_path.as_uri())
            await page.evaluate("document.fonts.ready")
            await page.evaluate("window.fitText()")
            slides = page.locator("section.slide")
            for i in range(await slides.count()):
                path = out_dir / f"slide-{i + 1}.jpg"
                # Screenshot lossless, then encode JPEG ourselves with chroma
                # subsampling off. Chromium's encoder uses 4:2:0, which smears
                # small colored detail (the logo, navy-on-gold text).
                png = await slides.nth(i).screenshot(type="png")
                Image.open(io.BytesIO(png)).convert("RGB").save(
                    path, "JPEG", quality=quality, subsampling=0, optimize=True
                )
                paths.append(path)
        finally:
            await browser.close()

    logger.info("Rendered %d slides to %s", len(paths), out_dir)
    return paths
