from PIL import Image, ImageDraw
import random
import os

# Configuration
WIDTH, HEIGHT = 256, 256
OUTPUT_DIR = "glyphs"
NUM_GLYPHS = 10
MAX_SHAPES = 10

os.makedirs(OUTPUT_DIR, exist_ok=True)

def random_color():
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def draw_glyph(draw):
    for _ in range(random.randint(5, MAX_SHAPES)):
        shape_type = random.choice(['ellipse', 'rectangle', 'line'])
        x1, y1 = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        x2, y2 = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        
        # Ensure coordinates are in correct order
        x0, x1_sorted = min(x1, x2), max(x1, x2)
        y0, y1_sorted = min(y1, y2), max(y1, y2)
        
        color = random_color()
        if shape_type == 'ellipse':
            draw.ellipse([x0, y0, x1_sorted, y1_sorted], fill=color, outline=None)
        elif shape_type == 'rectangle':
            draw.rectangle([x0, y0, x1_sorted, y1_sorted], fill=color, outline=None)
        elif shape_type == 'line':
            draw.line([x1, y1, x2, y2], fill=color, width=random.randint(1, 5))

# Generate glyphs
for i in range(NUM_GLYPHS):
    img = Image.new("RGB", (WIDTH, HEIGHT), color="white")
    draw = ImageDraw.Draw(img)
    draw_glyph(draw)
    img.save(f"{OUTPUT_DIR}/glyph_{i+1}.png")

print(f"Generated {NUM_GLYPHS} glyphs in {OUTPUT_DIR}/")
