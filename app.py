"""
Glyph Generator - Entry Point

Usage:
    python app.py                  # Launch GUI
    python app.py gui              # Launch GUI
    python app.py cli [options]    # Run CLI
    python app.py -n 20 -p neon   # Shorthand = CLI

Requirements:
    pip install Pillow svgwrite PySide6 numpy
    pip install numba              # Optional: faster PNG rendering
"""

import sys


def main():
    if len(sys.argv) <= 1:
        from glyph_gui import run_gui; run_gui(); return
    first = sys.argv[1].lower()
    if first in ('gui', '--gui'):
        from glyph_gui import run_gui; run_gui()
    elif first in ('cli', '--cli'):
        from glyph_cli import run_cli; sys.exit(run_cli(sys.argv[2:]))
    else:
        from glyph_cli import run_cli; sys.exit(run_cli(sys.argv[1:]))


if __name__ == '__main__':
    main()