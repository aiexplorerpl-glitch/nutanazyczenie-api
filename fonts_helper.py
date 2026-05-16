"""
fonts_helper.py — wspólny moduł rejestracji czcionek
Automatycznie pobiera DejaVu przy pierwszym użyciu jeśli brakuje.
"""
import os
import requests as req
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

_BASE     = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_BASE, "fonts")

_FONTS_URLS = {
    "DejaVuSans.ttf":         "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf",
    "DejaVuSans-Bold.ttf":    "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf",
    "DejaVuSans-Oblique.ttf": "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Oblique.ttf",
}

_registered = False


def _ensure_fonts():
    """Pobiera czcionki DejaVu jeśli nie ma ich lokalnie."""
    os.makedirs(_FONT_DIR, exist_ok=True)
    for filename, url in _FONTS_URLS.items():
        filepath = os.path.join(_FONT_DIR, filename)
        if not os.path.exists(filepath):
            try:
                print(f"[Fonts] Pobieram {filename}...")
                r = req.get(url, timeout=30)
                r.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(r.content)
                print(f"[Fonts] ✅ {filename} pobrany")
            except Exception as e:
                print(f"[Fonts] ❌ Błąd pobierania {filename}: {e}")


def register_fonts():
    """
    Rejestruje czcionki DejaVu z pełną obsługą polskich znaków.
    Automatycznie pobiera jeśli brakuje. Fallback na Helvetica.
    Zwraca (font_normal, font_bold, font_italic).
    """
    global _registered

    _ensure_fonts()

    regular = os.path.join(_FONT_DIR, "DejaVuSans.ttf")
    bold    = os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")
    italic  = os.path.join(_FONT_DIR, "DejaVuSans-Oblique.ttf")

    if os.path.exists(regular):
        try:
            if not _registered:
                pdfmetrics.registerFont(TTFont("DejaVu",        regular))
                pdfmetrics.registerFont(TTFont("DejaVu-Bold",   bold if os.path.exists(bold)   else regular))
                pdfmetrics.registerFont(TTFont("DejaVu-Italic", italic if os.path.exists(italic) else regular))
                registerFontFamily("DejaVu",
                    normal="DejaVu", bold="DejaVu-Bold",
                    italic="DejaVu-Italic", boldItalic="DejaVu-Bold")
                _registered = True
                print("[Fonts] ✅ DejaVu zarejestrowane — polskie znaki OK")
            return "DejaVu", "DejaVu-Bold", "DejaVu-Italic"
        except Exception as e:
            print(f"[Fonts] ⚠️ Błąd rejestracji: {e}")

    print("[Fonts] ⚠️ Fallback na Helvetica — brak polskich znaków")
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
