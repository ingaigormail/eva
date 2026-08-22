"""Genera el icono de EvA a partir del logo, en todos los tamaños que usa Windows.

El logo se redibuja aquí con geometría vectorial en vez de reescalar el PNG
original: a 16x16 un reescalado queda borroso, mientras que redibujar permite
además simplificar la figura (quitar las estrellas pequeñas, que a ese tamaño
solo ensucian).

Uso:
    python tools/make_icon.py

Genera en avcars/assets/:
    EvA.ico          icono multi-resolución para el .exe y la ventana
    EvA_256.png      versión grande con fondo (webs, tiendas)
    EvA_transp.png   versión sin fondo (documentos, cabeceras)
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

# Colores tomados del logo original
CYAN = (0, 176, 239, 255)
DARK = (50, 57, 76, 255)
BG = (232, 240, 246, 255)

# Lienzo de referencia en el que están expresadas las coordenadas de abajo.
CANVAS = 300.0

# Caja que ocupa el logo en la imagen original de la que se midieron los
# vértices, y proporción del lienzo que debe ocupar. Windows recorta los
# iconos ligeramente en algunos contextos, así que se deja aire alrededor.
SOURCE_BBOX = (29.0, 31.0, 273.0, 277.0)
CONTENT_RATIO = 0.72

WING_TIP_TOP = (272, 31)      # punta superior derecha
WING_TIP_LEFT = (29, 82)      # punta izquierda del ala
WING_BOTTOM = (152, 122)      # vértice inferior del ala cyan
BODY_WAIST = (197, 152)       # punto más ancho del cuerpo hacia la izquierda
BODY_TIP_BOTTOM = (249, 277)  # punta inferior

# Estrellas: (centro_x, centro_y, radio)
STARS = [
    (115, 158, 21),
    (170, 204, 12),
    (110, 232, 6),
]

SUPERSAMPLE = 8


def _t(point: tuple[float, float], scale: float) -> tuple[float, float]:
    """Lleva un punto del sistema de coordenadas del logo original al lienzo.

    Centra el logo y lo escala para que ocupe `CONTENT_RATIO` del lienzo,
    manteniendo la proporción. `scale` convierte del lienzo al bitmap final.
    """
    x0, y0, x1, y1 = SOURCE_BBOX
    k = CANVAS * CONTENT_RATIO / max(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x, y = point
    return (
        ((x - cx) * k + CANVAS / 2) * scale,
        ((y - cy) * k + CANVAS / 2) * scale,
    )


def _quad(p0, p1, p2, steps: int = 48) -> list[tuple[float, float]]:
    """Muestrea una curva de Bézier cuadrática como lista de puntos."""
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        points.append((x, y))
    return points


def _wing(scale: float) -> list[tuple[float, float]]:
    """Contorno del ala cyan."""
    top = _t(WING_TIP_TOP, scale)
    left = _t(WING_TIP_LEFT, scale)
    bottom = _t(WING_BOTTOM, scale)

    # Los puntos de control salen de ajustar cada curva a los bordes medidos
    # sobre el logo original (ver docstring del módulo).
    leading = _quad(top, _t((148, 52), scale), left)
    lower = _quad(left, _t((80, 108), scale), bottom)
    inner = _quad(bottom, _t((202, 109), scale), top)
    return leading + lower + inner


def _body(scale: float) -> list[tuple[float, float]]:
    """Contorno del cuerpo azul oscuro."""
    top = _t(WING_TIP_TOP, scale)
    waist = _t(BODY_WAIST, scale)
    tip = _t(BODY_TIP_BOTTOM, scale)

    left_upper = _quad(top, _t((217, 92), scale), waist)
    left_lower = _quad(waist, _t((199, 211), scale), tip)
    right = _quad(tip, _t((267, 154), scale), top)
    return left_upper + left_lower + right


def _star(cx: float, cy: float, r: float, scale: float) -> list[tuple[float, float]]:
    """Estrella de cuatro puntas afiladas."""
    c = _t((cx, cy), scale)
    radius = r * scale
    # Cuanto más cerca del centro está el punto de control, más afilada es la
    # punta. 0.16 reproduce el "destello" del logo.
    k = radius * 0.16
    pts: list[tuple[float, float]] = []
    tips = [(0, -1), (1, 0), (0, 1), (-1, 0)]
    for i in range(4):
        ax, ay = tips[i]
        bx, by = tips[(i + 1) % 4]
        p0 = (c[0] + ax * radius, c[1] + ay * radius)
        p2 = (c[0] + bx * radius, c[1] + by * radius)
        p1 = (c[0] + (ax + bx) * k, c[1] + (ay + by) * k)
        pts.extend(_quad(p0, p1, p2, steps=14))
    return pts


def _rounded_rect_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255
    )
    return mask


def render(size: int, background: bool = True, stars: bool = True) -> Image.Image:
    """Dibuja el logo al tamaño pedido.

    Se dibuja a `SUPERSAMPLE` veces el tamaño final y luego se reduce: es la
    forma más simple de conseguir bordes suavizados con PIL, que no hace
    antialiasing al rellenar polígonos.
    """
    big = size * SUPERSAMPLE
    scale = big / CANVAS

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if background:
        bg = Image.new("RGBA", (big, big), BG)
        img.paste(bg, (0, 0), _rounded_rect_mask(big))

    draw.polygon(_body(scale), fill=DARK)
    draw.polygon(_wing(scale), fill=CYAN)

    if stars:
        for cx, cy, r in STARS:
            draw.polygon(_star(cx, cy, r, scale), fill=DARK)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    assets = Path(__file__).resolve().parent.parent / "avcars" / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    # A 16 y 24 px las estrellas pequeñas se convierten en manchas: se omiten.
    frames = []
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        frames.append(render(size, background=True, stars=size >= 32))

    ico_path = assets / "EvA.ico"
    frames[-1].save(ico_path, format="ICO", sizes=[(f.width, f.width) for f in frames])

    render(256, background=True).save(assets / "EvA_256.png")
    render(256, background=False).save(assets / "EvA_transp.png")

    print(f"Icono generado en {assets}")


if __name__ == "__main__":
    main()
