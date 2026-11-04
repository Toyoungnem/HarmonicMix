"""Prepare the app logo and Windows icon from the supplied source image."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "harmonic-mix-logo-source.jpg"
PNG = ROOT / "HarmonicMix.png"
ICO = ROOT / "HarmonicMix.ico"


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    if source.width != source.height:
        raise ValueError("Le logo source doit être carré.")

    # L'image reçue contient un carré noir arrondi au milieu d'un fond blanc.
    # Un masque suréchantillonné conserve ce carré et rend le blanc extérieur
    # transparent avec un contour lissé.
    width, height = source.size
    scale = 4
    mask = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(mask)
    inset = 128 * scale
    extent = (width - 128) * scale - 1
    radius = 54 * scale
    draw.rounded_rectangle((inset, inset, extent, extent), radius=radius, fill=255)
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)

    # Retire la frange blanche de compression JPEG sur les pixels semi-transparents.
    result = source.convert("RGBA")
    result.putalpha(mask)
    source_pixels = source.load()
    result_pixels = result.load()
    mask_pixels = mask.load()
    for y in range(height):
        for x in range(width):
            alpha = mask_pixels[x, y]
            if 0 < alpha < 255:
                # Décontamine seulement le contour anti-crénelé, sans dépendance
                # de calcul supplémentaire comme NumPy.
                red, green, blue = source_pixels[x, y]
                result_pixels[x, y] = (
                    min(255, max(0, round((red - 255 + alpha) * 255 / alpha))),
                    min(255, max(0, round((green - 255 + alpha) * 255 / alpha))),
                    min(255, max(0, round((blue - 255 + alpha) * 255 / alpha))),
                    alpha,
                )
    result.save(PNG, optimize=True)
    result.save(
        ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Logo généré : {PNG}")
    print(f"Icône générée : {ICO}")


if __name__ == "__main__":
    main()
