"""
Glyph Generator - Creates procedural glyphs with various symmetry and style options

Features:
    - Multiple output formats (PNG, SVG)
    - Various color palettes (monochrome, vibrant, pastel, neon, earth, ocean, sunset)
    - Symmetry modes (none, mirror_x, mirror_xy, radial, kaleidoscope)
    - Configurable grid, shapes, density, opacity
    - Seed support for reproducible results
    - Command-line interface
    - JSON config export for each generation batch

Requirements:
    pip install Pillow svgwrite

Usage:
    python glyph_generator.py -n 20 -p monochrome -s kaleidoscope
    python glyph_generator.py -f png -p vibrant -s mirror_xy -n 15
    python glyph_generator.py --seed 42 -n 5 -p neon --size 1024
"""

import argparse
import json
import math
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Callable

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


class BackgroundStyle(Enum):
    SOLID_WHITE = "white"
    SOLID_BLACK = "black"
    TRANSPARENT = "transparent"
    GRADIENT = "gradient"


# Custom palette colors
CUSTOM_PALETTE = [
    "#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#9D4EDD",
    "#FF8C32", "#00D2FF", "#FF0099", "#7FFF00", "#FF4500"
]

# Palette generators - return (r, g, b) tuple
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


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB tuple to hex string."""
    return f'#{r:02x}{g:02x}{b:02x}'


def rgb_to_svg(r: int, g: int, b: int, opacity: float = 1.0) -> str:
    """Convert RGB to SVG color string."""
    if opacity < 1.0:
        return f'rgba({r},{g},{b},{opacity})'
    return f'rgb({r},{g},{b})'


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert hex string to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def parse_color(color_str: str) -> Tuple[int, int, int]:
    """Parse various color formats to RGB tuple."""
    if color_str.startswith('rgb('):
        values = color_str[4:-1].split(',')
        return tuple(int(v.strip()) for v in values)
    elif color_str.startswith('#'):
        return hex_to_rgb(color_str)
    elif color_str.startswith('rgba('):
        values = color_str[5:-1].split(',')
        return tuple(int(v.strip()) for v in values[:3])
    return (128, 128, 128)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class GlyphConfig:
    """Configuration for glyph generation."""
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
        """Convert config to dictionary for JSON serialization."""
        return {
            'width': self.width,
            'height': self.height,
            'grid_size': self.grid_size,
            'max_shapes_per_cell': self.max_shapes_per_cell,
            'min_shapes_per_cell': self.min_shapes_per_cell,
            'symmetry': self.symmetry.value,
            'rotation_segments': self.rotation_segments,
            'color_palette': self.color_palette.value,
            'background_color': self.background_color,
            'shape_types': self.shape_types,
            'output_format': self.output_format.value,
            'seed': self.seed,
            'opacity': self.opacity,
            'stroke_width': self.stroke_width,
            'custom_palette': self.custom_palette,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'GlyphConfig':
        """Create config from dictionary."""
        data = data.copy()
        data['symmetry'] = SymmetryMode(data['symmetry'])
        data['color_palette'] = ColorPalette(data['color_palette'])
        data['output_format'] = OutputFormat(data['output_format'])
        return cls(**data)


# =============================================================================
# GLYPH GENERATOR
# =============================================================================

class GlyphGenerator:
    """Main glyph generator class supporting both PNG and SVG output."""
    
    def __init__(self, config: GlyphConfig):
        self.config = config
        if config.seed is not None:
            random.seed(config.seed)
        self._custom_palette_rgb = [hex_to_rgb(c) for c in config.custom_palette]
    
    def _get_color(self) -> Tuple[int, int, int]:
        """Get a random color as RGB tuple."""
        if self.config.color_palette == ColorPalette.CUSTOM:
            return random.choice(self._custom_palette_rgb)
        return PALETTE_GENERATORS[self.config.color_palette]()
    
    def _get_color_svg(self) -> str:
        """Get color formatted for SVG."""
        r, g, b = self._get_color()
        return rgb_to_svg(r, g, b, self.config.opacity)
    
    def _get_transforms(self) -> List[Tuple[float, float, float]]:
        """Get list of (scale_x, scale_y, rotation) transforms based on symmetry mode."""
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
                angle = (360 / segments) * k
                transforms.append((1, 1, angle))
        
        elif symmetry == SymmetryMode.KALEIDOSCOPE:
            mirrors = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
            for mx, my in mirrors:
                for k in range(segments):
                    angle = (360 / segments) * k
                    transforms.append((mx, my, angle))
        
        return transforms
    
    def _get_source_cells(self, cols: int, rows: int) -> List[Tuple[int, int]]:
        """Get which grid cells to generate shapes for (before symmetry applied)."""
        symmetry = self.config.symmetry
        
        if symmetry in [SymmetryMode.KALEIDOSCOPE, SymmetryMode.MIRROR_XY]:
            return [(i, j) for i in range(cols // 2) for j in range(rows // 2)]
        elif symmetry == SymmetryMode.MIRROR_X:
            return [(i, j) for i in range(cols // 2) for j in range(rows)]
        else:
            return [(i, j) for i in range(cols) for j in range(rows)]
    
    # -------------------------------------------------------------------------
    # SVG Methods
    # -------------------------------------------------------------------------
    
    def _draw_shape_svg(self, dwg, group: 'svgwrite.g', size: float):
        """Draw a single shape into an SVG group."""
        shape_type = random.choice(self.config.shape_types)
        color = self._get_color_svg()
        sw = self.config.stroke_width
        
        if shape_type == 'rect':
            w = random.uniform(size * 0.2, size * 0.9)
            h = random.uniform(size * 0.2, size * 0.9)
            x = random.uniform(0, size - w)
            y = random.uniform(0, size - h)
            group.add(dwg.rect(insert=(x, y), size=(w, h), fill=color))
        
        elif shape_type == 'circle':
            r = random.uniform(size * 0.1, size * 0.45)
            cx = random.uniform(r, size - r)
            cy = random.uniform(r, size - r)
            group.add(dwg.circle(center=(cx, cy), r=r, fill=color))
        
        elif shape_type == 'line':
            x1 = random.uniform(0, size)
            y1 = random.uniform(0, size)
            x2 = random.uniform(0, size)
            y2 = random.uniform(0, size)
            group.add(dwg.line(
                start=(x1, y1), end=(x2, y2),
                stroke=color, stroke_width=sw
            ))
        
        elif shape_type == 'triangle':
            # Equilateral-ish triangle
            points = [
                (size * 0.5 + random.uniform(-size*0.2, size*0.2), random.uniform(0, size*0.3)),
                (random.uniform(0, size*0.3), random.uniform(size*0.6, size)),
                (random.uniform(size*0.7, size), random.uniform(size*0.6, size))
            ]
            group.add(dwg.polygon(points, fill=color))
        
        elif shape_type == 'diamond':
            cx, cy = size / 2, size / 2
            w = random.uniform(size * 0.15, size * 0.4)
            h = random.uniform(size * 0.15, size * 0.4)
            points = [(cx, cy - h), (cx + w, cy), (cx, cy + h), (cx - w, cy)]
            group.add(dwg.polygon(points, fill=color))
        
        elif shape_type == 'arc':
            r = random.uniform(size * 0.2, size * 0.45)
            cx, cy = size / 2, size / 2
            start_angle = random.uniform(0, 360)
            end_angle = start_angle + random.uniform(30, 180)
            # SVG arc as path
            start_rad = math.radians(start_angle)
            end_rad = math.radians(end_angle)
            x1 = cx + r * math.cos(start_rad)
            y1 = cy + r * math.sin(start_rad)
            x2 = cx + r * math.cos(end_rad)
            y2 = cy + r * math.sin(end_rad)
            large_arc = 1 if (end_angle - start_angle) > 180 else 0
            path = dwg.path(
                d=f"M {x1} {y1} A {r} {r} 0 {large_arc} 1 {x2} {y2}",
                stroke=color, stroke_width=sw, fill='none'
            )
            group.add(path)
        
        elif shape_type == 'ring':
            r_outer = random.uniform(size * 0.25, size * 0.45)
            r_inner = r_outer * random.uniform(0.4, 0.7)
            cx, cy = size / 2, size / 2
            group.add(dwg.circle(center=(cx, cy), r=r_outer, fill=color))
            # Cut out inner circle with background color (simplified)
            group.add(dwg.circle(center=(cx, cy), r=r_inner, fill=self.config.background_color))
    
    def _apply_symmetry_svg(self, dwg, base_group: 'svgwrite.g', x: float, y: float):
        """Apply symmetry transformations and add to drawing."""
        cx, cy = self.config.width / 2, self.config.height / 2
        transforms = self._get_transforms()
        
        for sx, sy, angle in transforms:
            transform = (
                f"translate({cx},{cy}) "
                f"scale({sx},{sy}) "
                f"rotate({angle}) "
                f"translate({-cx + x},{-cy + y})"
            )
            new_group = dwg.g(transform=transform)
            for element in base_group.elements:
                new_group.add(element)
            dwg.add(new_group)
    
    def generate_svg(self, output_path: str):
        """Generate a single SVG glyph."""
        if not SVGWRITE_AVAILABLE:
            raise RuntimeError("svgwrite is required for SVG output. Install with: pip install svgwrite")
        
        dwg = svgwrite.Drawing(
            filename=output_path,
            size=(self.config.width, self.config.height),
            viewBox=f"0 0 {self.config.width} {self.config.height}"
        )
        
        # Background
        if self.config.background_color != "transparent":
            dwg.add(dwg.rect(
                insert=(0, 0),
                size=(self.config.width, self.config.height),
                fill=self.config.background_color
            ))
        
        grid_size = self.config.grid_size
        cols = self.config.width // grid_size
        rows = self.config.height // grid_size
        source_cells = self._get_source_cells(cols, rows)
        
        for i, j in source_cells:
            x = i * grid_size
            y = j * grid_size
            
            # Generate shapes for this cell
            base_group = dwg.g()
            num_shapes = random.randint(
                self.config.min_shapes_per_cell,
                self.config.max_shapes_per_cell
            )
            for _ in range(num_shapes):
                self._draw_shape_svg(dwg, base_group, grid_size)
            
            # Apply symmetry
            self._apply_symmetry_svg(dwg, base_group, x, y)
        
        dwg.save()
    
    # -------------------------------------------------------------------------
    # PNG Methods
    # -------------------------------------------------------------------------
    
    def _draw_shape_png(self, draw: 'ImageDraw.ImageDraw', 
                        x_off: int, y_off: int, size: int):
        """Draw a single shape in PNG format."""
        shape_type = random.choice(self.config.shape_types)
        color = self._get_color()
        
        margin = max(1, int(size * 0.1))
        x1 = x_off + random.randint(0, margin)
        y1 = y_off + random.randint(0, margin)
        x2 = x_off + size - random.randint(0, margin)
        y2 = y_off + size - random.randint(0, margin)
        
        # Ensure proper ordering
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        
        if shape_type == 'rect':
            draw.rectangle([x1, y1, x2, y2], fill=color)
        
        elif shape_type == 'circle':
            draw.ellipse([x1, y1, x2, y2], fill=color)
        
        elif shape_type == 'line':
            draw.line(
                [(x1, y1), (x2, y2)],
                fill=color,
                width=random.randint(1, self.config.stroke_width + 2)
            )
        
        elif shape_type == 'triangle':
            points = [
                ((x1 + x2) // 2, y1),
                (x1, y2),
                (x2, y2)
            ]
            draw.polygon(points, fill=color)
        
        elif shape_type == 'diamond':
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            points = [(cx, y1), (x2, cy), (cx, y2), (x1, cy)]
            draw.polygon(points, fill=color)
        
        elif shape_type == 'arc':
            draw.arc([x1, y1, x2, y2], 
                     start=random.randint(0, 180), 
                     end=random.randint(180, 360),
                     fill=color,
                     width=self.config.stroke_width + 1)
        
        elif shape_type == 'ring':
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            r = min(x2 - x1, y2 - y1) // 2
            r_inner = random.randint(int(r * 0.3), int(r * 0.7))
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
            draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], 
                        fill=self._parse_bg_color())
    
    def _parse_bg_color(self) -> Tuple[int, int, int]:
        """Parse background color to RGB tuple."""
        bg = self.config.background_color
        if bg == "white":
            return (255, 255, 255)
        elif bg == "black":
            return (0, 0, 0)
        elif bg == "transparent":
            return (0, 0, 0)  # Won't work well for PNG transparency
        else:
            try:
                return parse_color(bg)
            except:
                return (255, 255, 255)
    
    def _mirror_point(self, x: int, y: int, size: int, 
                      w: int, h: int, mx: int, my: int) -> Tuple[int, int]:
        """Mirror a point based on mirror flags."""
        new_x = w - x - size if mx == -1 else x
        new_y = h - y - size if my == -1 else y
        return new_x, new_y
    
    def _rotate_point(self, x: int, y: int, size: int, 
                      cx: int, cy: int, angle: float) -> Tuple[int, int]:
        """Rotate a point around center."""
        # Center of the cell
        cell_cx = x + size / 2
        cell_cy = y + size / 2
        
        # Translate to origin
        dx = cell_cx - cx
        dy = cell_cy - cy
        
        # Rotate
        rad = math.radians(angle)
        new_dx = dx * math.cos(rad) - dy * math.sin(rad)
        new_dy = dx * math.sin(rad) + dy * math.cos(rad)
        
        # Translate back
        new_x = int(cx + new_dx - size / 2)
        new_y = int(cy + new_dy - size / 2)
        
        return new_x, new_y
    
    def generate_png(self, output_path: str):
        """Generate a single PNG glyph."""
        if not PIL_AVAILABLE:
            raise RuntimeError("Pillow is required for PNG output. Install with: pip install Pillow")
        
        w, h = self.config.width, self.config.height
        bg_color = self._parse_bg_color()
        
        # Handle transparency
        if self.config.background_color == "transparent":
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
        else:
            img = Image.new("RGB", (w, h), color=bg_color)
            draw = ImageDraw.Draw(img)
        
        grid_size = self.config.grid_size
        cols = w // grid_size
        rows = h // grid_size
        source_cells = self._get_source_cells(cols, rows)
        transforms = self._get_transforms()
        cx, cy = w // 2, h // 2
        
        for i, j in source_cells:
            base_x = i * grid_size
            base_y = j * grid_size
            
            # Generate shapes once for this source cell
            # We need to draw at all transformed positions
            for sx, sy, angle in transforms:
                if angle != 0:
                    # For PNG, we'll use a temporary image and rotate it
                    temp_img = Image.new("RGBA" if self.config.background_color == "transparent" else "RGB",
                                        (grid_size, grid_size), 
                                        (0, 0, 0, 0) if self.config.background_color == "transparent" else bg_color)
                    temp_draw = ImageDraw.Draw(temp_img)
                    
                    num_shapes = random.randint(
                        self.config.min_shapes_per_cell,
                        self.config.max_shapes_per_cell
                    )
                    for _ in range(num_shapes):
                        self._draw_shape_png(temp_draw, 0, 0, grid_size)
                    
                    # Rotate the temporary image
                    rotated = temp_img.rotate(-angle, resample=Image.BICUBIC, expand=True)
                    
                    # Mirror if needed
                    if sx == -1:
                        rotated = rotated.transpose(Image.FLIP_LEFT_RIGHT)
                    if sy == -1:
                        rotated = rotated.transpose(Image.FLIP_TOP_BOTTOM)
                    
                    # Calculate position
                    rot_cx, rot_cy = rotated.size[0] // 2, rotated.size[1] // 2
                    # Position after rotation from source cell
                    cell_cx = base_x + grid_size // 2 - cx
                    cell_cy = base_y + grid_size // 2 - cy
                    rad = math.radians(angle)
                    new_cx = int(cell_cx * math.cos(rad) - cell_cy * math.sin(rad))
                    new_cy = int(cell_cx * math.sin(rad) + cell_cy * math.cos(rad))
                    if sx == -1:
                        new_cx = -new_cx
                    if sy == -1:
                        new_cy = -new_cy
                    
                    paste_x = cx + new_cx - rot_cx
                    paste_y = cy + new_cy - rot_cy
                    
                    if self.config.background_color == "transparent":
                        img.paste(rotated, (paste_x, paste_y), rotated)
                    else:
                        img.paste(rotated, (paste_x, paste_y))
                    draw = ImageDraw.Draw(img)
                else:
                    # Simple mirror, no rotation
                    px, py = self._mirror_point(base_x, base_y, grid_size, w, h, sx, sy)
                    
                    num_shapes = random.randint(
                        self.config.min_shapes_per_cell,
                        self.config.max_shapes_per_cell
                    )
                    for _ in range(num_shapes):
                        self._draw_shape_png(draw, px, py, grid_size)
        
        # Apply optional smoothing for cleaner look
        if self.config.grid_size >= 8:
            img = img.filter(ImageFilter.SMOOTH)
        
        img.save(output_path)
    
    # -------------------------------------------------------------------------
    # Main Generation Method
    # -------------------------------------------------------------------------
    
    def generate(self, output_path: str):
        """Generate a glyph based on config format."""
        if self.config.output_format == OutputFormat.SVG:
            self.generate_svg(output_path)
        else:
            self.generate_png(output_path)


# =============================================================================
# BATCH GENERATION
# =============================================================================

def generate_glyphs(config: GlyphConfig, output_dir: str, count: int = 10) -> List[str]:
    """Generate multiple glyphs with the given configuration."""
    os.makedirs(output_dir, exist_ok=True)
    
    # Save configuration
    config_path = os.path.join(output_dir, "generation_config.json")
    with open(config_path, 'w') as f:
        json.dump({
            'config': config.to_dict(),
            'count': count,
            'generated_files': []
        }, f, indent=2)
    
    ext = config.output_format.value
    generated_files = []
    
    for i in range(count):
        # Create a new config with modified seed for each glyph
        if config.seed is not None:
            gen_config = GlyphConfig(**{**config.to_dict(), 'seed': config.seed + i})
        else:
            gen_config = GlyphConfig(**config.to_dict())
        
        generator = GlyphGenerator(gen_config)
        
        filename = f"glyph_{i+1:04d}.{ext}"
        output_path = os.path.join(output_dir, filename)
        
        try:
            generator.generate(output_path)
            generated_files.append(filename)
            print(f"  ✓ {filename}")
        except Exception as e:
            print(f"  ✗ {filename}: {str(e)}")
    
    # Update config with generated files list
    with open(config_path, 'w') as f:
        json.dump({
            'config': config.to_dict(),
            'count': count,
            'generated_files': generated_files
        }, f, indent=2)
    
    print(f"\n{'='*50}")
    print(f"Generated {len(generated_files)}/{count} glyphs in '{output_dir}/'")
    print(f"Config saved to '{config_path}'")
    print(f"{'='*50}")
    
    return generated_files


def generate_gallery(glyph_dir: str, output_path: str, cols: int = 5):
    """Create a gallery image from generated glyphs (PNG only)."""
    if not PIL_AVAILABLE:
        print("Gallery generation requires Pillow")
        return
    
    # Find all PNG files
    png_files = sorted([f for f in os.listdir(glyph_dir) if f.endswith('.png')])
    if not png_files:
        print("No PNG files found for gallery")
        return
    
    # Load first image to get dimensions
    first_img = Image.open(os.path.join(glyph_dir, png_files[0]))
    thumb_w, thumb_h = 128, 128
    padding = 10
    
    rows = math.ceil(len(png_files) / cols)
    gallery_w = cols * (thumb_w + padding) + padding
    gallery_h = rows * (thumb_h + padding) + padding
    
    gallery = Image.new('RGB', (gallery_w, gallery_h), color='white')
    
    for idx, filename in enumerate(png_files):
        img = Image.open(os.path.join(glyph_dir, filename))
        img.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
        
        row = idx // cols
        col = idx % cols
        x = padding + col * (thumb_w + padding)
        y = padding + row * (thumb_h + padding)
        
        gallery.paste(img, (x, y))
    
    gallery.save(output_path)
    print(f"Gallery saved to '{output_path}'")


# =============================================================================
# COMMAND LINE INTERFACE
# =============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate procedural glyphs with various symmetry and style options",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 20 monochrome kaleidoscope SVGs
  python glyph_generator.py -n 20 -p monochrome -s kaleidoscope
  
  # Generate 15 vibrant PNGs with mirror symmetry
  python glyph_generator.py -f png -p vibrant -s mirror_xy -n 15
  
  # Generate with specific seed for reproducibility
  python glyph_generator.py --seed 42 -n 5 -p neon --size 1024
  
  # Generate ocean-themed radial glyphs with triangles
  python glyph_generator.py -p ocean -s radial --shapes triangle,diamond
  
  # Create a gallery from existing PNGs
  python glyph_generator.py --gallery my_glyphs/ -o gallery.png
"""
    )
    
    # Generation options
    parser.add_argument(
        '-n', '--count',
        type=int,
        default=10,
        help='Number of glyphs to generate (default: 10)'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='glyphs_output',
        help='Output directory (default: glyphs_output)'
    )
    
    parser.add_argument(
        '-f', '--format',
        type=str,
        choices=['png', 'svg'],
        default='svg',
        help='Output format (default: svg)'
    )
    
    # Style options
    parser.add_argument(
        '-p', '--palette',
        type=str,
        choices=[p.value for p in ColorPalette],
        default='monochrome',
        help='Color palette (default: monochrome)'
    )
    
    parser.add_argument(
        '-s', '--symmetry',
        type=str,
        choices=[s.value for s in SymmetryMode],
        default='kaleidoscope',
        help='Symmetry mode (default: kaleidoscope)'
    )
    
    parser.add_argument(
        '--background',
        type=str,
        default='white',
        help='Background color (default: white)'
    )
    
    parser.add_argument(
        '--opacity',
        type=float,
        default=1.0,
        help='Shape opacity 0.0-1.0 for SVG (default: 1.0)'
    )
    
    # Grid and shape options
    parser.add_argument(
        '--size',
        type=int,
        default=512,
        help='Image size in pixels (default: 512)'
    )
    
    parser.add_argument(
        '--grid-size',
        type=int,
        default=16,
        help='Grid cell size in pixels (default: 16)'
    )
    
    parser.add_argument(
        '--rotation-segments',
        type=int,
        default=8,
        help='Number of rotation segments for radial/kaleidoscope (default: 8)'
    )
    
    parser.add_argument(
        '--max-shapes',
        type=int,
        default=3,
        help='Maximum shapes per grid cell (default: 3)'
    )
    
    parser.add_argument(
        '--min-shapes',
        type=int,
        default=1,
        help='Minimum shapes per grid cell (default: 1)'
    )
    
    parser.add_argument(
        '--stroke-width',
        type=int,
        default=1,
        help='Stroke width for lines and arcs (default: 1)'
    )
    
    parser.add_argument(
        '--shapes',
        type=str,
        default='rect,circle,line,triangle',
        help='Comma-separated shape types: %s (default: rect,circle,line,triangle)' % ', '.join(VALID_SHAPES)
    )
    
    # Reproducibility
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed for reproducibility (default: None)'
    )
    
    # Gallery option
    parser.add_argument(
        '--gallery',
        type=str,
        default=None,
        metavar='DIR',
        help='Create gallery from PNGs in specified directory'
    )
    
    parser.add_argument(
        '--gallery-cols',
        type=int,
        default=5,
        help='Number of columns in gallery (default: 5)'
    )
    
    # Load config option
    parser.add_argument(
        '--load-config',
        type=str,
        default=None,
        metavar='FILE',
        help='Load configuration from JSON file'
    )
    
    return parser.parse_args()


def validate_shapes(shapes: List[str]) -> List[str]:
    """Validate and filter shape types."""
    valid = []
    invalid = []
    for s in shapes:
        if s in VALID_SHAPES:
            valid.append(s)
        else:
            invalid.append(s)
    if invalid:
        print(f"Warning: Ignoring invalid shapes: {invalid}")
    return valid if valid else ['rect', 'circle', 'line']


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Gallery mode
    if args.gallery:
        if not PIL_AVAILABLE:
            print("Error: Pillow is required for gallery generation")
            return 1
        output = args.output if args.output.endswith('.png') else 'gallery.png'
        generate_gallery(args.gallery, output, args.gallery_cols)
        return 0
    
    # Load config if specified
    if args.load_config:
        try:
            with open(args.load_config, 'r') as f:
                saved_config = json.load(f)
            if 'config' in saved_config:
                config = GlyphConfig.from_dict(saved_config['config'])
            else:
                config = GlyphConfig.from_dict(saved_config)
            print(f"Loaded configuration from '{args.load_config}'")
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1
    else:
        # Check dependencies
        if args.format == 'png' and not PIL_AVAILABLE:
            print("Error: Pillow is required for PNG output")
            print("Install with: pip install Pillow")
            return 1
        
        if args.format == 'svg' and not SVGWRITE_AVAILABLE:
            print("Error: svgwrite is required for SVG output")
            print("Install with: pip install svgwrite")
            return 1
        
        # Create config from arguments
        shape_list = validate_shapes([s.strip() for s in args.shapes.split(',')])
        
        config = GlyphConfig(
            width=args.size,
            height=args.size,
            grid_size=args.grid_size,
            max_shapes_per_cell=args.max_shapes,
            min_shapes_per_cell=args.min_shapes,
            symmetry=SymmetryMode(args.symmetry),
            rotation_segments=args.rotation_segments,
            color_palette=ColorPalette(args.palette),
            background_color=args.background,
            shape_types=shape_list,
            output_format=OutputFormat(args.format),
            seed=args.seed,
            opacity=args.opacity,
            stroke_width=args.stroke_width,
        )
    
    # Print configuration summary
    print(f"\n{'='*50}")
    print("GLYPH GENERATOR")
    print(f"{'='*50}")
    print(f"Format:           {config.output_format.value}")
    print(f"Symmetry:         {config.symmetry.value}")
    print(f"Palette:          {config.color_palette.value}")
    print(f"Size:             {config.width}x{config.height}")
    print(f"Grid:             {config.grid_size}px")
    print(f"Shapes:           {', '.join(config.shape_types)}")
    print(f"Shapes/cell:      {config.min_shapes_per_cell}-{config.max_shapes_per_cell}")
    if config.symmetry in [SymmetryMode.RADIAL, SymmetryMode.KALEIDOSCOPE]:
        print(f"Rotation segments: {config.rotation_segments}")
    print(f"Seed:             {config.seed if config.seed else 'random'}")
    print(f"{'='*50}\n")
    
    # Generate glyphs
    generate_glyphs(config, args.output, args.count)
    
    return 0


if __name__ == '__main__':
    exit(main())