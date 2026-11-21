import asyncio
import json
from http import HTTPStatus
from io import BytesIO
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps


_BOT_DIR = Path(__file__).resolve().parents[1]
_PHOTO_DIR = _BOT_DIR / "assets" / "httpbird"
_FALLBACK_PHOTO = _BOT_DIR.parent / "docs" / "images" / "birdvirus.webp"
_PHOTO_CREDITS = json.loads((_PHOTO_DIR / "credits.json").read_text(encoding="utf-8"))
_LICENSE_URLS = {
    "CC0 1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "CC BY 2.0": "https://creativecommons.org/licenses/by/2.0/",
    "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
    "CC BY-SA 3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "CC BY-SA 4.0": "https://creativecommons.org/licenses/by-sa/4.0/",
}
_STATUS_STYLES = {
    1: ("informational", "#93c5fd"),
    2: ("success", "#bef264"),
    3: ("redirect", "#c4b5fd"),
    4: ("client error", "#fcd34d"),
    5: ("server error", "#fda4af"),
}


def _wrap_phrase(phrase: str, font: ImageFont.FreeTypeFont) -> str:
    lines = [""]
    for word in phrase.split():
        candidate = f"{lines[-1]} {word}".lstrip()
        if lines[-1] and font.getlength(candidate) > 316:
            lines.append(word)
        else:
            lines[-1] = candidate
    return "\n".join(lines)


def _render_card(status: HTTPStatus) -> BytesIO:
    family, accent = _STATUS_STYLES[status.value // 100]
    card = Image.new("RGB", (800, 420), "#101511")
    code = str(status.value)
    photo_path = _PHOTO_DIR / f"{code}.jpg" if code in _PHOTO_CREDITS else _FALLBACK_PHOTO
    with Image.open(photo_path) as photo:
        card.paste(ImageOps.fit(photo.convert("RGB"), (420, 420)), (380, 0))

    draw = ImageDraw.Draw(card)
    draw.rectangle((380, 0, 383, 419), fill=accent)
    draw.line((32, 376, 348, 376), fill="#3e4a40")
    draw.text((32, 28), "birdvirus / httpbird", font=ImageFont.load_default(20), fill=accent)
    draw.text((28, 65), str(status.value), font=ImageFont.load_default(124), fill=accent)
    phrase_font = ImageFont.load_default(31)
    draw.multiline_text(
        (32, 230),
        _wrap_phrase(status.phrase.lower(), phrase_font),
        font=phrase_font,
        fill="#f3f8ed",
        spacing=5,
    )
    draw.text((32, 389), family, font=ImageFont.load_default(17), fill="#b3c4b2")

    buffer = BytesIO()
    card.save(buffer, format="JPEG", quality=90)
    buffer.seek(0)
    return buffer


def _photo_credit(photo: dict[str, str]) -> str:
    license_name = photo["license"]
    license_url = _LICENSE_URLS.get(license_name)
    license_text = f"[{license_name}](<{license_url}>)" if license_url else license_name
    return (
        f'-# [image](<{photo["source"]}>) by {photo["author"]} · {license_text}'
        " · reframed and resized"
    )


def setup_httpbird(client: commands.Bot):
    @client.hybrid_command(name="httpbird", description="get a bird for an http status code")
    @app_commands.describe(code="the three-digit http status code, like 404")
    async def httpbird_cmd(ctx: commands.Context, code: str):
        if len(code) != 3 or not code.isascii() or not code.isdecimal():
            await ctx.reply("give me a three-digit http status code like `404`", ephemeral=True)
            return

        try:
            status = HTTPStatus(int(code))
        except ValueError:
            await ctx.reply(f"no bird for http status `{code}`", ephemeral=True)
            return

        image = await asyncio.to_thread(_render_card, status)
        caption = f"{status.value} {status.phrase.lower()}"
        description = caption
        photo = _PHOTO_CREDITS.get(str(status.value))
        if photo:
            caption += f"\n{_photo_credit(photo)}"
            description += f' — {photo["alt"]}'
        else:
            description += " — a crow perched on a rock"

        with image:
            attachment = discord.File(
                image,
                filename=f"httpbird-{status.value}.jpg",
                description=description,
            )
            try:
                await ctx.reply(
                    caption,
                    file=attachment,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            finally:
                attachment.close()
