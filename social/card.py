"""
card.py - Render a one-image social card (currently Facebook) to JPEG.

Same approach as instagram/renderer.py - an HTML template screenshotted by
headless Chromium - and it reuses that package's fonts, headshot and logo so
every channel stays on brand. Portrait 1080x1350 gets the most feed space on a
phone, and Facebook shows it uncropped.
"""
import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import List

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from playwright.async_api import async_playwright

from instagram.renderer import ASSETS, LOGO_HEIGHT, _find_asset, _png_size
from util.loggerfactory import LoggerFactory
from util.settings import settings

logger = LoggerFactory.create_logger(__name__)

TEMPLATES = Path(__file__).resolve().parent / "cards"
CARD_W, CARD_H = 1080, 1350


@dataclass
class CardContent:
    eyebrow: str      # e.g. "TEXAS FAMILY LAW" or the topic
    headline: str     # the client-facing hook, ideally a question
    points: List[str] # 2-3 plain-English takeaways


async def render_card(content: CardContent, out_path: Path, template: str = "facebook_card.html.j2",
                      quality: int = 95) -> Path:
    """Render one card and return the written JPEG path."""
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    headshot = _find_asset("headshot")
    logo = _find_asset("logo")
    size = _png_size(logo) if logo else None
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["j2", "html"]))
    html = env.get_template(template).render(
        c=content,
        fonts=(ASSETS / "fonts").as_uri(),
        headshot=headshot.as_uri() if headshot else "",
        # Inlined: Chromium refuses file:// images as CSS masks.
        logo=f"data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}" if logo else "",
        logo_w=round(LOGO_HEIGHT * size[0] / size[1]) if size else LOGO_HEIGHT * 4,
        logo_h=LOGO_HEIGHT,
        firm=settings.instagram_firm_name,
    )
    html_path = out_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": CARD_W, "height": CARD_H}, device_scale_factor=1)
            await page.goto(html_path.as_uri())
            await page.evaluate("document.fonts.ready")
            await page.evaluate("window.fitText()")
            png = await page.locator(".card").screenshot(type="png")
        finally:
            await browser.close()

    Image.open(io.BytesIO(png)).convert("RGB").save(out_path, "JPEG", quality=quality, subsampling=0, optimize=True)
    logger.info("Rendered card to %s", out_path)
    return out_path
