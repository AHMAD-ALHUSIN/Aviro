"""
يُشغَّل في CI لتوليد أيقونة التطبيق تلقائياً
"""
from PIL import Image, ImageDraw
import math

SIZE = 512
img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# خلفية دائرة متدرجة اللون (نرسمها بطبقات)
for i in range(SIZE // 2):
    ratio = i / (SIZE // 2)
    r = int(59  + ratio * (99  - 59))
    g = int(130 + ratio * (102 - 130))
    b = int(246 + ratio * (241 - 246))
    draw.ellipse(
        [SIZE//2 - (SIZE//2 - i), SIZE//2 - (SIZE//2 - i),
         SIZE//2 + (SIZE//2 - i), SIZE//2 + (SIZE//2 - i)],
        outline=(r, g, b, 255),
    )

# رسم دائرة خلفية صلبة
draw.ellipse([0, 0, SIZE, SIZE], fill=(59, 130, 246, 255))

# سهم التحميل ↓
W = (255, 255, 255, 255)
cx = SIZE // 2

# جسم السهم (عمود)
draw.rectangle([cx - 35, 110, cx + 35, 310], fill=W)

# رأس السهم (مثلث)
draw.polygon(
    [(cx - 100, 270), (cx, 390), (cx + 100, 270)],
    fill=W,
)

# خط أسفل السهم
draw.rectangle([cx - 120, 410, cx + 120, 455], fill=W)
draw.rounded_rectangle([cx - 120, 408, cx + 120, 458], radius=20, fill=W)

img.save("icon.png")
print("icon.png generated ✓")
