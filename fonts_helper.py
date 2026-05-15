"""
fonts_helper.py — wspólny moduł rejestracji czcionek
Używany przez agent3_pack.py i agent3_qr.py
"""
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# Ścieżki do szukania czcionek DejaVu
_BASE = os.path.dirname(__file__)
FONT_SEARCH_PATHS = [
    os.path.join(_BASE, "fonts"),          # /app/fonts — po pobraniu przez download_fonts.py
    "/usr/share/fonts/truetype/dejavu",    # Linux systemowe
    "/usr/share/fonts/dejavu",
]

_registered = False


def get_font_dir():
    """Zwraca ścieżkę do katalogu z czcionkami DejaVu lub None."""
    for path in FONT_SEARCH_PATHS:
        if os.path.exists(os.path.join(path, "DejaVuSans.ttf")):
            return path
    return None


def register_fonts():
    """
    Rejestruje czcionki DejaVu z pełną obsługą polskich znaków.
    Fallback na Helvetica jeśli DejaVu niedostępne.
    Zwraca (font_normal, font_bold, font_italic).
    """
    global _registered

    font_dir = get_font_dir()

    if font_dir:
        try:
            if not _registered:
                pdfmetrics.registerFont(
                    TTFont("DejaVu", os.path.join(font_dir, "DejaVuSans.ttf")))
                pdfmetrics.registerFont(
                    TTFont("DejaVu-Bold", os.path.join(font_dir, "DejaVuSans-Bold.ttf")))
                pdfmetrics.registerFont(
                    TTFont("DejaVu-Italic", os.path.join(font_dir, "DejaVuSans-Oblique.ttf")))
                registerFontFamily("DejaVu",
                    normal="DejaVu", bold="DejaVu-Bold",
                    italic="DejaVu-Italic", boldItalic="DejaVu-Bold")
                _registered = True
            return "DejaVu", "DejaVu-Bold", "DejaVu-Italic"
        except Exception as e:
            print(f"[Fonts] ⚠️ Błąd rejestracji DejaVu: {e}")

    print("[Fonts] ⚠️ DejaVu niedostępne — używam Helvetica (brak polskich znaków)")
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
