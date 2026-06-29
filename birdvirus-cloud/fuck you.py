import ctypes
import random
import time

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

hdc = user32.GetDC(0)

width = user32.GetSystemMetrics(0)
height = user32.GetSystemMetrics(1)

TRANSPARENT = 1
gdi32.SetBkMode(hdc, TRANSPARENT)

text = "you are birdvirus"

try:
    while True:
        x = random.randint(0, max(0, width - 200))
        y = random.randint(0, max(0, height - 30))

        # COLORREF format is 0x00BBGGRR
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        color = (b << 16) | (g << 8) | r

        gdi32.SetTextColor(hdc, color)
        gdi32.TextOutW(hdc, x, y, text, len(text))

        time.sleep(0.02)

except KeyboardInterrupt:
    pass
finally:
    user32.ReleaseDC(0, hdc)
