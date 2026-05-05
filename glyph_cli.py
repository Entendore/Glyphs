"""
Glyph Generator - Command-Line Interface
"""

import argparse
import logging
import sys

from glyph_core import (
    GlyphConfig, ColorPalette, SymmetryMode, OutputFormat,
    VALID_SHAPES, validate_shapes, generate_glyphs, generate_gallery,
    PIL_AVAILABLE, SVGWRITE_AVAILABLE, NUMBA_AVAILABLE,
)

logger = logging.getLogger("glyph")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate procedural glyphs with various symmetry and style options",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py cli -n 20 -p monochrome -s kaleidoscope
  python app.py cli -f png -p vibrant -s mirror_xy -n 15
  python app.py cli --seed 42 -n 5 -p neon --size 1024
  python app.py cli --no-numba -n 50 -p ocean
""")
    p.add_argument('-n', '--count', type=int, default=10)
    p.add_argument('-o', '--output', type=str, default='glyphs_output')
    p.add_argument('-f', '--format', type=str, choices=['png', 'svg'], default='svg')
    p.add_argument('-p', '--palette', type=str, choices=[x.value for x in ColorPalette], default='monochrome')
    p.add_argument('-s', '--symmetry', type=str, choices=[x.value for x in SymmetryMode], default='kaleidoscope')
    p.add_argument('--background', type=str, default='white')
    p.add_argument('--opacity', type=float, default=1.0)
    p.add_argument('--size', type=int, default=512)
    p.add_argument('--grid-size', type=int, default=16)
    p.add_argument('--rotation-segments', type=int, default=8)
    p.add_argument('--max-shapes', type=int, default=3)
    p.add_argument('--min-shapes', type=int, default=1)
    p.add_argument('--stroke-width', type=int, default=1)
    p.add_argument('--shapes', type=str, default='rect,circle,line,triangle')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--gallery', type=str, default=None, metavar='DIR')
    p.add_argument('--gallery-cols', type=int, default=5)
    p.add_argument('--load-config', type=str, default=None, metavar='FILE')
    p.add_argument('--no-numba', action='store_true', help='Disable Numba acceleration')
    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args()


def run_cli(argv=None) -> int:
    args = parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format='%(levelname)-5s  %(message)s', stream=sys.stderr, force=True)

    if args.gallery:
        if not PIL_AVAILABLE:
            print("Error: Pillow required for gallery", file=sys.stderr); return 1
        out = args.output if args.output.endswith('.png') else 'gallery.png'
        generate_gallery(args.gallery, out, args.gallery_cols); return 0

    if args.load_config:
        import json
        try:
            with open(args.load_config) as f:
                d = json.load(f)
            config = GlyphConfig.from_dict(d['config'] if 'config' in d else d)
            print(f"Loaded config from '{args.load_config}'", file=sys.stderr)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr); return 1
    else:
        if args.format == 'png' and not PIL_AVAILABLE:
            print("Error: pip install Pillow", file=sys.stderr); return 1
        if args.format == 'svg' and not SVGWRITE_AVAILABLE:
            print("Error: pip install svgwrite", file=sys.stderr); return 1
        config = GlyphConfig(
            width=args.size, height=args.size, grid_size=args.grid_size,
            max_shapes_per_cell=args.max_shapes, min_shapes_per_cell=args.min_shapes,
            symmetry=SymmetryMode(args.symmetry), rotation_segments=args.rotation_segments,
            color_palette=ColorPalette(args.palette), background_color=args.background,
            shape_types=validate_shapes([s.strip() for s in args.shapes.split(',')]),
            output_format=OutputFormat(args.format), seed=args.seed,
            opacity=args.opacity, stroke_width=args.stroke_width)

    use_numba = not args.no_numba and NUMBA_AVAILABLE and args.format == 'png'

    print(f"\n{'='*50}", file=sys.stderr)
    print("GLYPH GENERATOR", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)
    print(f"Format:     {config.output_format.value}", file=sys.stderr)
    print(f"Symmetry:   {config.symmetry.value}", file=sys.stderr)
    print(f"Palette:    {config.color_palette.value}", file=sys.stderr)
    print(f"Size:       {config.width}x{config.height}", file=sys.stderr)
    print(f"Grid:       {config.grid_size}px", file=sys.stderr)
    print(f"Shapes:     {', '.join(config.shape_types)}", file=sys.stderr)
    print(f"Per cell:   {config.min_shapes_per_cell}-{config.max_shapes_per_cell}", file=sys.stderr)
    if config.symmetry in [SymmetryMode.RADIAL, SymmetryMode.KALEIDOSCOPE]:
        print(f"Segments:   {config.rotation_segments}", file=sys.stderr)
    print(f"Seed:       {config.seed if config.seed else 'random'}", file=sys.stderr)
    print(f"Numba:      {'ON' if use_numba else 'OFF'}", file=sys.stderr)
    print(f"{'='*50}\n", file=sys.stderr)

    files = generate_glyphs(config, args.output, args.count, use_numba=use_numba)
    print(f"\nDone: {len(files)}/{args.count} glyphs", file=sys.stderr)
    return 0