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
    """Generate a random vibrant color."""
    # Option 1: fully random
    r = random.randint(50, 255)
    g = random.randint(50, 255)
    b = random.randint(50, 255)
    return f'rgb({r},{g},{b})'

    # Option 2: limited palette (uncomment to use)
    # palette = [
    #     "#FF6B6B", "#FFD93D", "#6BCB77", "#4D96FF", "#9D4EDD"
    # ]
    # return random.choice(palette)

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

    for i in range(cols//2):
        for j in range(rows//2):
            x = i * grid_size
            y = j * grid_size

            # Base group for shapes in this cell
            base_group = dwg.g()
            for _ in range(random.randint(1, MAX_SHAPES_PER_CELL)):
                draw_shape(dwg, base_group, grid_size)

            # Apply mirroring and rotation
            mirrors = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
            for mx, my in mirrors:
                for k in range(rotation_segments):
                    angle = (360 / rotation_segments) * k
                    transform = (
                        f"translate({cx},{cy}) "
                        f"scale({mx},{my}) "
                        f"rotate({angle}) "
                        f"translate({-cx + x},{-cy + y})"
                    )
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

print(f"Generated {NUM_GLYPHS} colorful SVG glyphs in {OUTPUT_DIR}/")
