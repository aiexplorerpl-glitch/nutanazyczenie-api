"""
download_fonts.py — uruchamiany przed startem serwera przez Procfile
Pobiera czcionki DejaVu z obsługą polskich znaków (ą, ę, ś, ć, ł, ż, ź, ó, ń)
"""
import os
import sys
import requests

FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

FONTS = {
    "DejaVuSans.ttf":         "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf":    "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique.ttf": "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Oblique.ttf",
}

all_ok = True
for filename, url in FONTS.items():
    filepath = os.path.join(FONTS_DIR, filename)
    if os.path.exists(filepath):
        print(f"[Fonts] ✅ {filename} — już istnieje")
        continue
    try:
        print(f"[Fonts] Pobieram {filename}...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
        print(f"[Fonts] ✅ {filename} pobrany ({len(resp.content)//1024} KB)")
    except Exception as e:
        print(f"[Fonts] ❌ Błąd pobierania {filename}: {e}")
        all_ok = False

if all_ok:
    print("[Fonts] ✅ Wszystkie czcionki gotowe")
else:
    print("[Fonts] ⚠️ Niektóre czcionki niedostępne — fallback na Helvetica")
