import svgwrite
import random
import os

# Configuration
WIDTH, HEIGHT = 512, 512
NUM_GLYPHS = 10
OUTPUT_DIR = "glyphs_svg"
GRID_SIZE = 16           # size of grid cells
MAX_SHAPES_PER_CELL = 3
ROTATION_SYMMETRY = 8    # number of rotational segments

os.makedirs(OUTPUT_DIR, exist_ok=True)

def random_color():
    # Monochrome-style for autoglyph aesthetics
    shade = random.randint(0, 50)
    return f'rgb({shade},{shade},{shade})'

def draw_shape(dwg, group, size):
    """Draw a single shape inside a group."""
    shape_type = random.choice(['rect', 'circle', 'line'])
    color = random_color()

    if shape_type == 'rect':
        w = random.uniform(size*0.3, size*0.8)
        h = random.uniform(size*0.3, size*0.8)
        group.add(dwg.rect(insert=(0, 0), size=(w, h), fill=color))
    elif shape_type == 'circle':
        r = random.uniform(size*0.2, size*0.4)
        group.add(dwg.circle(center=(size/2, size/2), r=r, fill=color))
    elif shape_type == 'line':
        x1 = random.uniform(0, size)
        y1 = random.uniform(0, size)
        x2 = random.uniform(0, size)
        y2 = random.uniform(0, size)
        group.add(dwg.line(start=(x1, y1), end=(x2, y2), stroke=color, stroke_width=1))

def draw_glyph(dwg, width, height, grid_size, rotation_segments):
    cx, cy = width / 2, height / 2  # center of rotation
    cols = width // grid_size
    rows = height // grid_size

    # Only fill a quadrant, then mirror + rotate
    for i in range(cols//2):
        for j in range(rows//2):
            x = i * grid_size
            y = j * grid_size

            # Base group for shapes in this cell
            base_group = dwg.g()
            for _ in range(random.randint(1, MAX_SHAPES_PER_CELL)):
                draw_shape(dwg, base_group, grid_size)

            # Apply mirroring in X and Y axes and rotation
            mirrors = [
                (1, 1),   # original
                (-1, 1),  # mirror X
                (1, -1),  # mirror Y
                (-1, -1)  # mirror XY
            ]

            for mx, my in mirrors:
                for k in range(rotation_segments):
                    angle = (360 / rotation_segments) * k
                    transform = (
                        f"translate({cx},{cy}) "
                        f"scale({mx},{my}) "
                        f"rotate({angle}) "
                        f"translate({-cx + x},{-cy + y})"
                    )
                    # create a new group, add all elements from base_group
                    new_group = dwg.g(transform=transform)
                    for element in base_group.elements:
                        new_group.add(element)
                    dwg.add(new_group)

# Generate SVG glyphs
for n in range(NUM_GLYPHS):
    dwg = svgwrite.Drawing(
        filename=f"{OUTPUT_DIR}/glyph_{n+1}.svg", size=(WIDTH, HEIGHT)
    )
    draw_glyph(dwg, WIDTH, HEIGHT, GRID_SIZE, ROTATION_SYMMETRY)
    dwg.save()

print(f"Generated {NUM_GLYPHS} radial + mirrored SVG glyphs in {OUTPUT_DIR}/")
