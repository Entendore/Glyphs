"""
Glyph Generator Core - Procedural glyph generation with symmetry and style options.
Supports optional Numba acceleration for PNG rendering.
"""

import copy
import io
import json
import logging
import math
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Callable

import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import svgwrite
    SVGWRITE_AVAILABLE = True
except ImportError:
    SVGWRITE_AVAILABLE = False

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

logger = logging.getLogger("glyph")


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class ColorPalette(Enum):
    MONOCHROME = "monochrome"
    VIBRANT = "vibrant"
    PASTEL = "pastel"
    NEON = "neon"
    EARTH = "earth"
    OCEAN = "ocean"
    SUNSET = "sunset"
    GRAYSCALE = "grayscale"
    CUSTOM = "custom"


class SymmetryMode(Enum):
    NONE = "none"
    MIRROR_X = "mirror_x"
    MIRROR_XY = "mirror_xy"
    RADIAL = "radial"
    KALEIDOSCOPE = "kaleidoscope"


class OutputFormat(Enum):
    PNG = "png"
    SVG = "svg"


CUSTOM_PALETTE = [
    "#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#9D4EDD",
    "#FF8C32", "#00D2FF", "#FF0099", "#7FFF00", "#FF4500"
]

PALETTE_GENERATORS: dict[ColorPalette, Callable[[], Tuple[int, int, int]]] = {
    ColorPalette.MONOCHROME: lambda: (
        random.randint(0, 60), random.randint(0, 60), random.randint(0, 60)
    ),
    ColorPalette.VIBRANT: lambda: (
        random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)
    ),
    ColorPalette.PASTEL: lambda: (
        random.randint(150, 230), random.randint(150, 230), random.randint(150, 230)
    ),
    ColorPalette.NEON: lambda: random.choice([
        (255, 0, 255), (0, 255, 255), (255, 0, 128),
        (0, 255, 0), (255, 255, 0), (128, 0, 255),
        (255, 100, 0), (0, 200, 255)
    ]),
    ColorPalette.EARTH: lambda: (
        random.randint(100, 180), random.randint(70, 130), random.randint(30, 80)
    ),
    ColorPalette.OCEAN: lambda: (
        random.randint(0, 80), random.randint(80, 180), random.randint(150, 255)
    ),
    ColorPalette.SUNSET: lambda: (
        random.randint(200, 255), random.randint(50, 150), random.randint(0, 100)
    ),
    ColorPalette.GRAYSCALE: lambda: (
        random.randint(20, 235), random.randint(20, 235), random.randint(20, 235)
    ),
    ColorPalette.CUSTOM: lambda: (
        random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
    ),
}

VALID_SHAPES = ['rect', 'circle', 'line', 'triangle', 'diamond', 'arc', 'ring']

SHAPE_TYPE_INT = {
    'rect': 0, 'circle': 1, 'line': 2, 'triangle': 3,
    'diamond': 4, 'arc': 5, 'ring': 6,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f'#{r:02x}{g:02x}{b:02x}'


def rgb_to_svg(r: int, g: int, b: int, opacity: float = 1.0) -> str:
    if opacity < 1.0:
        return f'rgba({r},{g},{b},{opacity})'
    return f'rgb({r},{g},{b})'


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def parse_color(color_str: str) -> Tuple[int, int, int]:
    if color_str.startswith('rgb('):
        values = color_str[4:-1].split(',')
        return tuple(int(v.strip()) for v in values)
    elif color_str.startswith('#'):
        return hex_to_rgb(color_str)
    elif color_str.startswith('rgba('):
        values = color_str[5:-1].split(',')
        return tuple(int(v.strip()) for v in values[:3])
    return (128, 128, 128)


def validate_shapes(shapes: List[str]) -> List[str]:
    valid = []
    invalid = []
    for s in shapes:
        if s in VALID_SHAPES:
            valid.append(s)
        else:
            invalid.append(s)
    if invalid:
        logger.warning("Ignoring invalid shapes: %s", invalid)
    return valid if valid else ['rect', 'circle', 'line']


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class GlyphConfig:
    width: int = 512
    height: int = 512
    grid_size: int = 16
    max_shapes_per_cell: int = 3
    min_shapes_per_cell: int = 1
    symmetry: SymmetryMode = SymmetryMode.KALEIDOSCOPE
    rotation_segments: int = 8
    color_palette: ColorPalette = ColorPalette.MONOCHROME
    background_color: str = "white"
    shape_types: List[str] = field(default_factory=lambda: ['rect', 'circle', 'line', 'triangle'])
    output_format: OutputFormat = OutputFormat.SVG
    seed: Optional[int] = None
    opacity: float = 1.0
    stroke_width: int = 1
    custom_palette: List[str] = field(default_factory=lambda: CUSTOM_PALETTE.copy())

    def to_dict(self) -> dict:
        return {
            'width': self.width, 'height': self.height,
            'grid_size': self.grid_size,
            'max_shapes_per_cell': self.max_shapes_per_cell,
            'min_shapes_per_cell': self.min_shapes_per_cell,
            'symmetry': self.symmetry.value,
            'rotation_segments': self.rotation_segments,
            'color_palette': self.color_palette.value,
            'background_color': self.background_color,
            'shape_types': list(self.shape_types),
            'output_format': self.output_format.value,
            'seed': self.seed, 'opacity': self.opacity,
            'stroke_width': self.stroke_width,
            'custom_palette': list(self.custom_palette),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'GlyphConfig':
        data = data.copy()
        data['symmetry'] = SymmetryMode(data['symmetry'])
        data['color_palette'] = ColorPalette(data['color_palette'])
        data['output_format'] = OutputFormat(data['output_format'])
        return cls(**data)


# =============================================================================
# NUMBA ACCELERATED DRAWING FUNCTIONS
# =============================================================================

if NUMBA_AVAILABLE:
    @njit(cache=True)
    def _nb_fill_rect(img, x1, y1, x2, y2, r, g, b, h, w):
        y1c = max(0, y1); y2c = min(h, y2)
        x1c = max(0, x1); x2c = min(w, x2)
        for y in range(y1c, y2c):
            for x in range(x1c, x2c):
                img[y, x, 0] = r
                img[y, x, 1] = g
                img[y, x, 2] = b

    @njit(cache=True)
    def _nb_fill_circle(img, cx, cy, radius, r, g, b, h, w):
        r2 = radius * radius
        y0 = max(0, cy - radius); y1 = min(h, cy + radius + 1)
        x0 = max(0, cx - radius); x1 = min(w, cx + radius + 1)
        for y in range(y0, y1):
            dy = y - cy
            for x in range(x0, x1):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    img[y, x, 0] = r
                    img[y, x, 1] = g
                    img[y, x, 2] = b

    @njit(cache=True)
    def _nb_draw_line(img, x1, y1, x2, y2, r, g, b, lw, h, w):
        dx = x2 - x1; dy = y2 - y1
        steps = max(abs(dx), abs(dy), 1)
        hw = lw // 2
        for i in range(steps + 1):
            t = i / steps
            px = int(x1 + t * dx)
            py = int(y1 + t * dy)
            for wy in range(-hw, hw + 1):
                for wx in range(-hw, hw + 1):
                    nx = px + wx; ny = py + wy
                    if 0 <= nx < w and 0 <= ny < h:
                        img[ny, nx, 0] = r
                        img[ny, nx, 1] = g
                        img[ny, nx, 2] = b

    @njit(cache=True)
    def _nb_fill_triangle(img, x0, y0, x1, y1, x2, y2, r, g, b, h, w):
        min_y = max(0, min(y0, y1, y2))
        max_y = min(h - 1, max(y0, y1, y2))
        min_x = max(0, min(x0, x1, x2))
        max_x = min(w - 1, max(x0, x1, x2))
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if denom == 0:
            return
        inv = 1.0 / denom
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                a = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) * inv
                bb = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) * inv
                cc = 1.0 - a - bb
                if a >= 0 and bb >= 0 and cc >= 0:
                    img[y, x, 0] = r
                    img[y, x, 1] = g
                    img[y, x, 2] = b

    @njit(cache=True)
    def _nb_fill_diamond(img, cx, cy, hw, hh, r, g, b, h, w):
        y0 = max(0, cy - hh); y1 = min(h, cy + hh + 1)
        x0 = max(0, cx - hw); x1 = min(w, cx + hw + 1)
        if hw == 0 or hh == 0:
            return
        inv_hw = 1.0 / hw; inv_hh = 1.0 / hh
        for y in range(y0, y1):
            for x in range(x0, x1):
                if abs(x - cx) * inv_hw + abs(y - cy) * inv_hh <= 1.0:
                    img[y, x, 0] = r
                    img[y, x, 1] = g
                    img[y, x, 2] = b

    @njit(cache=True)
    def _nb_draw_arc(img, cx, cy, rx, ry, start_deg, end_deg, r, g, b, lw, h, w):
        arc_len = abs(end_deg - start_deg)
        if arc_len < 1:
            return
        steps = max(int(arc_len * 0.5), 12)
        hw = max(lw // 2, 1)
        pi = 3.141592653589793
        for i in range(steps + 1):
            t = start_deg + arc_len * i / steps
            rad = t * pi / 180.0
            px = int(cx + rx * math.cos(rad))
            py = int(cy + ry * math.sin(rad))
            for wy in range(-hw, hw + 1):
                for wx in range(-hw, hw + 1):
                    nx = px + wx; ny = py + wy
                    if 0 <= nx < w and 0 <= ny < h:
                        img[ny, nx, 0] = r
                        img[ny, nx, 1] = g
                        img[ny, nx, 2] = b

    @njit(cache=True)
    def _nb_draw_ring(img, cx, cy, r_out, r_in, r, g, b, bg_r, bg_g, bg_b, h, w):
        _nb_fill_circle(img, cx, cy, r_out, r, g, b, h, w)
        if r_in > 0:
            _nb_fill_circle(img, cx, cy, r_in, bg_r, bg_g, bg_b, h, w)

    @njit(cache=True)
    def _nb_draw_shapes(img, shapes, n_shapes, h, w, bg_r, bg_g, bg_b, stroke_w):
        for i in range(n_shapes):
            st = shapes[i, 0]
            p0 = shapes[i, 1]; p1 = shapes[i, 2]
            p2 = shapes[i, 3]; p3 = shapes[i, 4]
            p4 = shapes[i, 5]; p5 = shapes[i, 6]; p6 = shapes[i, 7]
            cr = shapes[i, 8]; cg = shapes[i, 9]; cb = shapes[i, 10]
            if st == 0:
                _nb_fill_rect(img, p0, p1, p2, p3, cr, cg, cb, h, w)
            elif st == 1:
                _nb_fill_circle(img, p0, p1, p2, cr, cg, cb, h, w)
            elif st == 2:
                _nb_draw_line(img, p0, p1, p2, p3, cr, cg, cb, p4, h, w)
            elif st == 3:
                _nb_fill_triangle(img, p0, p1, p2, p3, p4, p5, cr, cg, cb, h, w)
            elif st == 4:
                _nb_fill_diamond(img, p0, p1, p2, p3, cr, cg, cb, h, w)
            elif st == 5:
                _nb_draw_arc(img, p0, p1, p2, p3, p4, p5, cr, cg, cb, p6, h, w)
            elif st == 6:
                _nb_draw_ring(img, p0, p1, p2, p3, cr, cg, cb, p4, p5, p6, h, w)

    @njit(cache=True)
    def _nb_rotated_size(block_w, block_h, angle_deg):
        rad = angle_deg * 3.141592653589793 / 180.0
        ca = abs(math.cos(rad)); sa = abs(math.sin(rad))
        new_w = int(math.ceil(block_w * ca + block_h * sa))
        new_h = int(math.ceil(block_h * ca + block_w * sa))
        return new_w, new_h

    @njit(cache=True, parallel=True)
    def _nb_rotate_block(src, dst, src_h, src_w, dst_h, dst_w,
                         angle_deg, flip_x, flip_y):
        rad = -angle_deg * 3.141592653589793 / 180.0
        cos_a = math.cos(rad); sin_a = math.sin(rad)
        src_cx = src_w * 0.5; src_cy = src_h * 0.5
        dst_cx = dst_w * 0.5; dst_cy = dst_h * 0.5
        for dy in prange(dst_h):
            for dx in range(dst_w):
                rx = dx - dst_cx; ry = dy - dst_cy
                sx = rx * cos_a + ry * sin_a + src_cx
                sy = -rx * sin_a + ry * cos_a + src_cy
                if flip_x:
                    sx = src_w - 1.0 - sx
                if flip_y:
                    sy = src_h - 1.0 - sy
                ix = int(sx); iy = int(sy)
                if 0 <= ix < src_w and 0 <= iy < src_h:
                    dst[dy, dx, 0] = src[iy, ix, 0]
                    dst[dy, dx, 1] = src[iy, ix, 1]
                    dst[dy, dx, 2] = src[iy, ix, 2]

    @njit(cache=True, parallel=True)
    def _nb_paste_block(img, block, bh, bw, px, py, ih, iw):
        for by in prange(bh):
            for bx in range(bw):
                tx = px + bx; ty = py + by
                if 0 <= tx < iw and 0 <= ty < ih:
                    img[ty, tx, 0] = block[by, bx, 0]
                    img[ty, tx, 1] = block[by, bx, 1]
                    img[ty, tx, 2] = block[by, bx, 2]

    @njit(cache=True, parallel=True)
    def _nb_smooth(img, dst, h, w):
        for y in prange(1, h - 1):
            for x in range(1, w - 1):
                for c in range(3):
                    v = (img[y-1,x-1,c] + 2*img[y-1,x,c] + img[y-1,x+1,c] +
                         2*img[y,x-1,c] + 4*img[y,x,c] + 2*img[y,x+1,c] +
                         img[y+1,x-1,c] + 2*img[y+1,x,c] + img[y+1,x+1,c])
                    dst[y, x, c] = v // 16

    _numba_warmed_up = False

    def warmup_numba():
        global _numba_warmed_up
        if _numba_warmed_up:
            return
        logger.info("Warming up Numba JIT compilation...")
        tmp = np.zeros((8, 8, 3), dtype=np.uint8)
        _nb_fill_rect(tmp, 0, 0, 7, 7, 255, 0, 0, 8, 8)
        _nb_fill_circle(tmp, 4, 4, 3, 0, 255, 0, 8, 8)
        _nb_draw_line(tmp, 0, 0, 7, 7, 128, 128, 128, 1, 8, 8)
        _nb_fill_triangle(tmp, 4, 0, 0, 7, 7, 7, 0, 0, 255, 8, 8)
        _nb_fill_diamond(tmp, 4, 4, 3, 3, 255, 255, 0, 8, 8)
        _nb_draw_arc(tmp, 4, 4, 3, 3, 0, 180, 100, 100, 100, 1, 8, 8)
        _nb_draw_ring(tmp, 4, 4, 3, 1, 128, 0, 128, 255, 255, 255, 8, 8)
        shapes = np.zeros((1, 11), dtype=np.int32)
        shapes[0] = [0, 0, 0, 7, 7, 0, 0, 0, 255, 0, 0]
        _nb_draw_shapes(tmp, shapes, 1, 8, 8, 255, 255, 255, 1)
        rw, rh = _nb_rotated_size(8, 8, 45.0)
        dst = np.zeros((rh, rw, 3), dtype=np.uint8)
        _nb_rotate_block(tmp, dst, 8, 8, rh, rw, 45.0, False, False)
        _nb_paste_block(tmp, dst, rh, rw, 0, 0, 8, 8)
        out = np.zeros_like(tmp)
        _nb_smooth(tmp, out, 8, 8)
        _numba_warmed_up = True
        logger.info("Numba JIT warmup complete")

else:
    def warmup_numba():
        pass


# =============================================================================
# GLYPH GENERATOR
# =============================================================================

class GlyphGenerator:
    def __init__(self, config: GlyphConfig):
        self.config = config
        if config.seed is not None:
            random.seed(config.seed)
            logger.debug("Seeded RNG with %d", config.seed)
        self._custom_palette_rgb = [hex_to_rgb(c) for c in config.custom_palette]
        logger.debug(
            "GlyphGenerator: %s %s %s %dx%d grid=%d",
            config.output_format.value, config.symmetry.value,
            config.color_palette.value, config.width, config.height,
            config.grid_size,
        )

    def _get_color(self) -> Tuple[int, int, int]:
        if self.config.color_palette == ColorPalette.CUSTOM:
            return random.choice(self._custom_palette_rgb)
        return PALETTE_GENERATORS[self.config.color_palette]()

    def _get_color_svg(self) -> str:
        r, g, b = self._get_color()
        return rgb_to_svg(r, g, b, self.config.opacity)

    def _get_transforms(self) -> List[Tuple[float, float, float]]:
        symmetry = self.config.symmetry
        segments = self.config.rotation_segments
        transforms = []
        if symmetry == SymmetryMode.NONE:
            transforms = [(1, 1, 0)]
        elif symmetry == SymmetryMode.MIRROR_X:
            transforms = [(1, 1, 0), (-1, 1, 0)]
        elif symmetry == SymmetryMode.MIRROR_XY:
            transforms = [(1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0)]
        elif symmetry == SymmetryMode.RADIAL:
            for k in range(segments):
                transforms.append((1, 1, (360 / segments) * k))
        elif symmetry == SymmetryMode.KALEIDOSCOPE:
            for mx, my in [(1, 1), (-1, 1), (1, -1), (-1, -1)]:
                for k in range(segments):
                    transforms.append((mx, my, (360 / segments) * k))
        logger.debug("Symmetry %s → %d transform(s)", symmetry.value, len(transforms))
        return transforms

    def _get_source_cells(self, cols: int, rows: int) -> List[Tuple[int, int]]:
        symmetry = self.config.symmetry
        if symmetry in [SymmetryMode.KALEIDOSCOPE, SymmetryMode.MIRROR_XY]:
            cells = [(i, j) for i in range(cols // 2) for j in range(rows // 2)]
        elif symmetry == SymmetryMode.MIRROR_X:
            cells = [(i, j) for i in range(cols // 2) for j in range(rows)]
        else:
            cells = [(i, j) for i in range(cols) for j in range(rows)]
        logger.debug("Source cells: %d", len(cells))
        return cells

    def _parse_bg_color(self) -> Tuple[int, int, int]:
        bg = self.config.background_color
        if bg == "white": return (255, 255, 255)
        elif bg == "black": return (0, 0, 0)
        else:
            try: return parse_color(bg)
            except Exception: return (255, 255, 255)

    def _precompute_shapes_np(self, num_shapes: int, cell_x: int, cell_y: int,
                               cell_size: int) -> np.ndarray:
        """Pre-compute shape parameters as int32 array for numba path.
        Columns: [type, p0..p7, r, g, b] = 11 cols
        """
        data = np.zeros((num_shapes, 11), dtype=np.int32)
        bg = self._parse_bg_color()
        margin = max(1, int(cell_size * 0.1))
        for idx in range(num_shapes):
            shape_type = random.choice(self.config.shape_types)
            r, g, b = self._get_color()
            x1 = cell_x + random.randint(0, margin)
            y1 = cell_y + random.randint(0, margin)
            x2 = cell_x + cell_size - random.randint(0, margin)
            y2 = cell_y + cell_size - random.randint(0, margin)
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            st = SHAPE_TYPE_INT.get(shape_type, 0)
            data[idx, 0] = st
            data[idx, 8] = r; data[idx, 9] = g; data[idx, 10] = b
            if st == 0:
                data[idx, 1] = x1; data[idx, 2] = y1
                data[idx, 3] = x2; data[idx, 4] = y2
            elif st == 1:
                data[idx, 1] = (x1+x2)//2; data[idx, 2] = (y1+y2)//2
                data[idx, 3] = max(1, min(x2-x1, y2-y1)//2)
            elif st == 2:
                data[idx, 1] = x1; data[idx, 2] = y1
                data[idx, 3] = x2; data[idx, 4] = y2
                data[idx, 5] = random.randint(1, self.config.stroke_width + 2)
            elif st == 3:
                data[idx, 1] = (x1+x2)//2; data[idx, 2] = y1
                data[idx, 3] = x1; data[idx, 4] = y2
                data[idx, 5] = x2; data[idx, 6] = y2
            elif st == 4:
                data[idx, 1] = (x1+x2)//2; data[idx, 2] = (y1+y2)//2
                data[idx, 3] = max(1, (x2-x1)//2)
                data[idx, 4] = max(1, (y2-y1)//2)
            elif st == 5:
                data[idx, 1] = (x1+x2)//2; data[idx, 2] = (y1+y2)//2
                data[idx, 3] = max(1, (x2-x1)//2)
                data[idx, 4] = max(1, (y2-y1)//2)
                data[idx, 5] = random.randint(0, 180)
                data[idx, 6] = random.randint(180, 360)
                data[idx, 7] = self.config.stroke_width + 1
            elif st == 6:
                cx = (x1+x2)//2; cy = (y1+y2)//2
                r_out = max(1, min(x2-x1, y2-y1)//2)
                r_in = random.randint(max(1, int(r_out*0.3)), max(2, int(r_out*0.7)))
                data[idx, 1] = cx; data[idx, 2] = cy
                data[idx, 3] = r_out; data[idx, 4] = r_in
                data[idx, 5] = bg[0]; data[idx, 6] = bg[1]; data[idx, 7] = bg[2]
        return data

    # --- SVG ---

    def _draw_shape_svg(self, dwg, group, size: float):
        shape_type = random.choice(self.config.shape_types)
        color = self._get_color_svg()
        sw = self.config.stroke_width
        if shape_type == 'rect':
            w = random.uniform(size * 0.2, size * 0.9)
            h = random.uniform(size * 0.2, size * 0.9)
            x = random.uniform(0, size - w); y = random.uniform(0, size - h)
            group.add(dwg.rect(insert=(x, y), size=(w, h), fill=color))
        elif shape_type == 'circle':
            r = random.uniform(size * 0.1, size * 0.45)
            cx = random.uniform(r, size - r); cy = random.uniform(r, size - r)
            group.add(dwg.circle(center=(cx, cy), r=r, fill=color))
        elif shape_type == 'line':
            group.add(dwg.line(
                start=(random.uniform(0, size), random.uniform(0, size)),
                end=(random.uniform(0, size), random.uniform(0, size)),
                stroke=color, stroke_width=sw))
        elif shape_type == 'triangle':
            points = [
                (size*0.5 + random.uniform(-size*0.2, size*0.2), random.uniform(0, size*0.3)),
                (random.uniform(0, size*0.3), random.uniform(size*0.6, size)),
                (random.uniform(size*0.7, size), random.uniform(size*0.6, size))]
            group.add(dwg.polygon(points, fill=color))
        elif shape_type == 'diamond':
            cx, cy = size/2, size/2
            w = random.uniform(size*0.15, size*0.4); h = random.uniform(size*0.15, size*0.4)
            group.add(dwg.polygon([(cx, cy-h), (cx+w, cy), (cx, cy+h), (cx-w, cy)], fill=color))
        elif shape_type == 'arc':
            r = random.uniform(size*0.2, size*0.45); cx, cy = size/2, size/2
            sa = random.uniform(0, 360); ea = sa + random.uniform(30, 180)
            sr, er = math.radians(sa), math.radians(ea)
            x1 = cx + r*math.cos(sr); y1 = cy + r*math.sin(sr)
            x2 = cx + r*math.cos(er); y2 = cy + r*math.sin(er)
            la = 1 if (ea - sa) > 180 else 0
            group.add(dwg.path(d=f"M {x1} {y1} A {r} {r} 0 {la} 1 {x2} {y2}",
                               stroke=color, stroke_width=sw, fill='none'))
        elif shape_type == 'ring':
            ro = random.uniform(size*0.25, size*0.45); ri = ro * random.uniform(0.4, 0.7)
            cx, cy = size/2, size/2
            group.add(dwg.circle(center=(cx, cy), r=ro, fill=color))
            group.add(dwg.circle(center=(cx, cy), r=ri, fill=self.config.background_color))

    def _apply_symmetry_svg(self, dwg, base_group, x: float, y: float):
        cx, cy = self.config.width / 2, self.config.height / 2
        for sx, sy, angle in self._get_transforms():
            t = (f"translate({cx},{cy}) scale({sx},{sy}) rotate({angle}) "
                 f"translate({-cx + x},{-cy + y})")
            ng = dwg.g(transform=t)
            for el in base_group.elements:
                ng.add(el)
            dwg.add(ng)

    def generate_svg(self, output_path: str):
        if not SVGWRITE_AVAILABLE:
            raise RuntimeError("svgwrite required. pip install svgwrite")
        logger.info("Generating SVG: %s", output_path)
        dwg = svgwrite.Drawing(filename=output_path,
                               size=(self.config.width, self.config.height),
                               viewBox=f"0 0 {self.config.width} {self.config.height}")
        if self.config.background_color != "transparent":
            dwg.add(dwg.rect(insert=(0, 0),
                              size=(self.config.width, self.config.height),
                              fill=self.config.background_color))
        gs = self.config.grid_size
        cols = self.config.width // gs; rows = self.config.height // gs
        for i, j in self._get_source_cells(cols, rows):
            bg = dwg.g()
            for _ in range(random.randint(self.config.min_shapes_per_cell, self.config.max_shapes_per_cell)):
                self._draw_shape_svg(dwg, bg, gs)
            self._apply_symmetry_svg(dwg, bg, i * gs, j * gs)
        dwg.save()
        logger.info("Saved SVG: %s", output_path)

    # --- PNG (PIL fallback) ---

    def _draw_shape_png(self, draw, x_off, y_off, size):
        shape_type = random.choice(self.config.shape_types)
        color = self._get_color()
        m = max(1, int(size * 0.1))
        x1 = x_off + random.randint(0, m); y1 = y_off + random.randint(0, m)
        x2 = x_off + size - random.randint(0, m); y2 = y_off + size - random.randint(0, m)
        x1, x2 = min(x1, x2), max(x1, x2); y1, y2 = min(y1, y2), max(y1, y2)
        if shape_type == 'rect':
            draw.rectangle([x1, y1, x2, y2], fill=color)
        elif shape_type == 'circle':
            draw.ellipse([x1, y1, x2, y2], fill=color)
        elif shape_type == 'line':
            draw.line([(x1, y1), (x2, y2)], fill=color,
                      width=random.randint(1, self.config.stroke_width + 2))
        elif shape_type == 'triangle':
            draw.polygon([((x1+x2)//2, y1), (x1, y2), (x2, y2)], fill=color)
        elif shape_type == 'diamond':
            cx, cy = (x1+x2)//2, (y1+y2)//2
            draw.polygon([(cx, y1), (x2, cy), (cx, y2), (x1, cy)], fill=color)
        elif shape_type == 'arc':
            draw.arc([x1, y1, x2, y2], start=random.randint(0, 180),
                     end=random.randint(180, 360), fill=color,
                     width=self.config.stroke_width + 1)
        elif shape_type == 'ring':
            cx, cy = (x1+x2)//2, (y1+y2)//2
            r = min(x2-x1, y2-y1)//2
            ri = random.randint(max(1, int(r*0.3)), max(2, int(r*0.7)))
            draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
            draw.ellipse([cx-ri, cy-ri, cx+ri, cy+ri], fill=self._parse_bg_color())

    def _mirror_point(self, x, y, size, w, h, mx, my):
        return (w - x - size if mx == -1 else x, h - y - size if my == -1 else y)

    def generate_png(self, output_path: str):
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow required. pip install Pillow")
        logger.info("Generating PNG (PIL): %s", output_path)
        w, h = self.config.width, self.config.height
        bg = self._parse_bg_color()
        img = Image.new("RGB", (w, h), color=bg)
        draw = ImageDraw.Draw(img)
        gs = self.config.grid_size
        cols, rows = w // gs, h // gs
        cx, cy = w // 2, h // 2
        for i, j in self._get_source_cells(cols, rows):
            bx, by = i * gs, j * gs
            for sx, sy, angle in self._get_transforms():
                if angle != 0:
                    tmp = Image.new("RGB", (gs, gs), bg)
                    td = ImageDraw.Draw(tmp)
                    for _ in range(random.randint(self.config.min_shapes_per_cell, self.config.max_shapes_per_cell)):
                        self._draw_shape_png(td, 0, 0, gs)
                    rot = tmp.rotate(-angle, resample=Image.BICUBIC, expand=True)
                    if sx == -1: rot = rot.transpose(Image.FLIP_LEFT_RIGHT)
                    if sy == -1: rot = rot.transpose(Image.FLIP_TOP_BOTTOM)
                    rcx, rcy = rot.size[0]//2, rot.size[1]//2
                    ccx = bx + gs//2 - cx; ccy = by + gs//2 - cy
                    rad = math.radians(angle)
                    ncx = int(ccx*math.cos(rad) - ccy*math.sin(rad))
                    ncy = int(ccx*math.sin(rad) + ccy*math.cos(rad))
                    if sx == -1: ncx = -ncx
                    if sy == -1: ncy = -ncy
                    img.paste(rot, (cx + ncx - rcx, cy + ncy - rcy))
                    draw = ImageDraw.Draw(img)
                else:
                    px, py = self._mirror_point(bx, by, gs, w, h, sx, sy)
                    for _ in range(random.randint(self.config.min_shapes_per_cell, self.config.max_shapes_per_cell)):
                        self._draw_shape_png(draw, px, py, gs)
        if self.config.grid_size >= 8:
            img = img.filter(ImageFilter.SMOOTH)
        img.save(output_path)
        logger.info("Saved PNG: %s", output_path)

    # --- PNG (Numba accelerated) ---

    def generate_png_numba(self, output_path: str):
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow required. pip install Pillow")
        if not NUMBA_AVAILABLE:
            raise RuntimeError("Numba required. pip install numba")
        import glyph_core
        glyph_core.warmup_numba()

        logger.info("Generating PNG (Numba): %s", output_path)
        c = self.config
        w, h = c.width, c.height
        bg = self._parse_bg_color()
        img = np.full((h, w, 3), bg, dtype=np.uint8)
        gs = c.grid_size
        cols, rows = w // gs, h // gs
        source_cells = self._get_source_cells(cols, rows)
        transforms = self._get_transforms()
        icx, icy = w // 2, h // 2

        for i, j in source_cells:
            bx, by = i * gs, j * gs
            for sx, sy, angle in transforms:
                n_shapes = random.randint(c.min_shapes_per_cell, c.max_shapes_per_cell)
                if angle != 0:
                    tmp = np.full((gs, gs, 3), bg, dtype=np.uint8)
                    shapes = self._precompute_shapes_np(n_shapes, 0, 0, gs)
                    _nb_draw_shapes(tmp, shapes, n_shapes, gs, gs, bg[0], bg[1], bg[2], c.stroke_width)
                    rw, rh = _nb_rotated_size(gs, gs, angle)
                    dst = np.zeros((rh, rw, 3), dtype=np.uint8)
                    _nb_rotate_block(tmp, dst, gs, gs, rh, rw, angle, sx == -1, sy == -1)
                    ccx = bx + gs//2 - icx; ccy = by + gs//2 - icy
                    rad = math.radians(angle)
                    ncx = int(ccx * math.cos(rad) - ccy * math.sin(rad))
                    ncy = int(ccx * math.sin(rad) + ccy * math.cos(rad))
                    if sx == -1: ncx = -ncx
                    if sy == -1: ncy = -ncy
                    px = icx + ncx - rw // 2
                    py = icy + ncy - rh // 2
                    _nb_paste_block(img, dst, rh, rw, px, py, h, w)
                else:
                    px = w - bx - gs if sx == -1 else bx
                    py = h - by - gs if sy == -1 else by
                    shapes = self._precompute_shapes_np(n_shapes, px, py, gs)
                    _nb_draw_shapes(img, shapes, n_shapes, h, w, bg[0], bg[1], bg[2], c.stroke_width)

        if gs >= 8:
            smoothed = np.empty_like(img)
            _nb_smooth(img, smoothed, h, w)
            img = smoothed

        pil_img = Image.fromarray(img, 'RGB')
        pil_img.save(output_path)
        logger.info("Saved PNG (Numba): %s", output_path)

    # --- Dispatcher ---

    def generate(self, output_path: str, use_numba: bool = True):
        if self.config.output_format == OutputFormat.SVG:
            self.generate_svg(output_path)
        elif use_numba and NUMBA_AVAILABLE:
            self.generate_png_numba(output_path)
        else:
            self.generate_png(output_path)


# =============================================================================
# BATCH GENERATION
# =============================================================================

def generate_glyphs(config: GlyphConfig, output_dir: str, count: int = 10,
                    progress_callback: Optional[Callable[[int, int, str], None]] = None,
                    use_numba: bool = True) -> List[str]:
    """Generate multiple glyphs. Uses deepcopy to preserve enum types."""
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Output: %s", os.path.abspath(output_dir))
    logger.info("Batch: %d glyphs, format=%s, symmetry=%s, palette=%s, numba=%s",
                count, config.output_format.value, config.symmetry.value,
                config.color_palette.value, use_numba and NUMBA_AVAILABLE)

    config_path = os.path.join(output_dir, "generation_config.json")
    with open(config_path, 'w') as f:
        json.dump({'config': config.to_dict(), 'count': count, 'generated_files': []}, f, indent=2)

    ext = config.output_format.value
    generated_files = []

    for i in range(count):
        gen_config = copy.deepcopy(config)
        if config.seed is not None:
            gen_config.seed = config.seed + i

        generator = GlyphGenerator(gen_config)
        filename = f"glyph_{i+1:04d}.{ext}"
        output_path = os.path.join(output_dir, filename)

        try:
            generator.generate(output_path, use_numba=use_numba)
            generated_files.append(filename)
            logger.info("  [%d/%d] OK   %s", i + 1, count, filename)
            if progress_callback:
                progress_callback(i + 1, count, filename)
        except Exception as e:
            logger.error("  [%d/%d] FAIL %s: %s", i + 1, count, filename, e, exc_info=True)
            if progress_callback:
                progress_callback(i + 1, count, f"{filename}: {e}")

    with open(config_path, 'w') as f:
        json.dump({'config': config.to_dict(), 'count': count, 'generated_files': generated_files}, f, indent=2)

    logger.info("Batch done: %d/%d in '%s'", len(generated_files), count, output_dir)
    return generated_files


def generate_single_to_bytes(config: GlyphConfig, use_numba: bool = True) -> Optional[bytes]:
    """Generate a single PNG glyph, return bytes."""
    if not PIL_AVAILABLE:
        logger.error("Pillow not available for preview")
        return None
    import glyph_core
    gen_config = copy.deepcopy(config)
    gen_config.output_format = OutputFormat.PNG
    gen_config.background_color = "white"
    logger.debug("Preview: %s %s seed=%s numba=%s",
                 gen_config.symmetry.value, gen_config.color_palette.value,
                 gen_config.seed, use_numba and NUMBA_AVAILABLE)

    c = gen_config
    w, h = c.width, c.height
    bg = (255, 255, 255)

    if use_numba and NUMBA_AVAILABLE:
        glyph_core.warmup_numba()
        img = np.full((h, w, 3), bg, dtype=np.uint8)
        gs = c.grid_size
        cols, rows = w // gs, h // gs
        generator = GlyphGenerator(gen_config)
        source_cells = generator._get_source_cells(cols, rows)
        transforms = generator._get_transforms()
        icx, icy = w // 2, h // 2

        for i, j in source_cells:
            bx, by = i * gs, j * gs
            for sx, sy, angle in transforms:
                n_shapes = random.randint(c.min_shapes_per_cell, c.max_shapes_per_cell)
                if angle != 0:
                    tmp = np.full((gs, gs, 3), bg, dtype=np.uint8)
                    shapes = generator._precompute_shapes_np(n_shapes, 0, 0, gs)
                    _nb_draw_shapes(tmp, shapes, n_shapes, gs, gs, bg[0], bg[1], bg[2], c.stroke_width)
                    rw, rh = _nb_rotated_size(gs, gs, angle)
                    dst = np.zeros((rh, rw, 3), dtype=np.uint8)
                    _nb_rotate_block(tmp, dst, gs, gs, rh, rw, angle, sx == -1, sy == -1)
                    ccx = bx + gs//2 - icx; ccy = by + gs//2 - icy
                    rad = math.radians(angle)
                    ncx = int(ccx*math.cos(rad) - ccy*math.sin(rad))
                    ncy = int(ccx*math.sin(rad) + ccy*math.cos(rad))
                    if sx == -1: ncx = -ncx
                    if sy == -1: ncy = -ncy
                    _nb_paste_block(img, dst, rh, rw, icx + ncx - rw//2, icy + ncy - rh//2, h, w)
                else:
                    px = w - bx - gs if sx == -1 else bx
                    py = h - by - gs if sy == -1 else by
                    shapes = generator._precompute_shapes_np(n_shapes, px, py, gs)
                    _nb_draw_shapes(img, shapes, n_shapes, h, w, bg[0], bg[1], bg[2], c.stroke_width)

        if gs >= 8:
            smoothed = np.empty_like(img)
            _nb_smooth(img, smoothed, h, w)
            img = smoothed
        pil_img = Image.fromarray(img, 'RGB')
    else:
        pil_img = Image.new("RGB", (w, h), color=bg)
        draw = ImageDraw.Draw(pil_img)
        generator = GlyphGenerator(gen_config)
        gs = c.grid_size
        cols, rows = w // gs, h // gs
        icx, icy = w // 2, h // 2
        for i, j in generator._get_source_cells(cols, rows):
            bx, by = i * gs, j * gs
            for sx, sy, angle in generator._get_transforms():
                if angle != 0:
                    tmp = Image.new("RGB", (gs, gs), bg)
                    td = ImageDraw.Draw(tmp)
                    for _ in range(random.randint(c.min_shapes_per_cell, c.max_shapes_per_cell)):
                        generator._draw_shape_png(td, 0, 0, gs)
                    rot = tmp.rotate(-angle, resample=Image.BICUBIC, expand=True)
                    if sx == -1: rot = rot.transpose(Image.FLIP_LEFT_RIGHT)
                    if sy == -1: rot = rot.transpose(Image.FLIP_TOP_BOTTOM)
                    rcx, rcy = rot.size[0]//2, rot.size[1]//2
                    ccx = bx + gs//2 - icx; ccy = by + gs//2 - icy
                    rad = math.radians(angle)
                    ncx = int(ccx*math.cos(rad) - ccy*math.sin(rad))
                    ncy = int(ccx*math.sin(rad) + ccy*math.cos(rad))
                    if sx == -1: ncx = -ncx
                    if sy == -1: ncy = -ncy
                    pil_img.paste(rot, (icx + ncx - rcx, icy + ncy - rcy))
                    draw = ImageDraw.Draw(pil_img)
                else:
                    px = w - bx - gs if sx == -1 else bx
                    py = h - by - gs if sy == -1 else by
                    for _ in range(random.randint(c.min_shapes_per_cell, c.max_shapes_per_cell)):
                        generator._draw_shape_png(draw, px, py, gs)
        if gs >= 8:
            pil_img = pil_img.filter(ImageFilter.SMOOTH)

    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    logger.debug("Preview rendered (%d bytes)", buf.tell())
    return buf.getvalue()


def generate_gallery(glyph_dir: str, output_path: str, cols: int = 5):
    if not PIL_AVAILABLE:
        logger.error("Gallery requires Pillow"); return
    png_files = sorted(f for f in os.listdir(glyph_dir) if f.endswith('.png'))
    if not png_files:
        logger.warning("No PNG files in %s", glyph_dir); return
    thumb_w, thumb_h, pad = 128, 128, 10
    rows = math.ceil(len(png_files) / cols)
    gallery = Image.new('RGB', (cols*(thumb_w+pad)+pad, rows*(thumb_h+pad)+pad), 'white')
    for idx, fn in enumerate(png_files):
        img = Image.open(os.path.join(glyph_dir, fn))
        img.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
        gallery.paste(img, (pad + idx%cols*(thumb_w+pad), pad + idx//cols*(thumb_h+pad)))
    gallery.save(output_path)
    logger.info("Gallery saved: %s (%d images)", output_path, len(png_files))