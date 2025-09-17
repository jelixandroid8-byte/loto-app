from PIL import Image
import os

SRC = 'img1.jpg'
OUT_DIR = 'static/icons'
SIZES = [(192,192),(512,512)]

os.makedirs(OUT_DIR, exist_ok=True)
img = Image.open(SRC).convert('RGBA')
for w,h in SIZES:
    out = img.resize((w,h), Image.LANCZOS)
    out_path = os.path.join(OUT_DIR, f'icon-{w}x{h}.png')
    out.save(out_path, format='PNG')
    print('Saved', out_path)
