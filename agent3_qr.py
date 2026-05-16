"""
MODUŁ: Generowanie kartki z kodem QR
=====================================
Tworzy elegancką kartkę A6 (105×148 mm) gotową do wydruku.
Kartka zawiera:
- Złote logo NutaNaŻyczenie
- Kod QR prowadzący do piosenki lub wideo
- Imię odbiorcy i okazja
- Tekst zapraszający do skanowania
- Stopka z marką

Używa darmowego API qrserver.com do generowania QR — brak zewnętrznych bibliotek.
"""

import io
import requests
from urllib.parse import quote
from reportlab.lib.pagesizes import A6
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.colors import HexColor
from fonts_helper import register_fonts

# Kolory marki
GOLD  = HexColor("#C9963A")
DARK  = HexColor("#1A1208")
MUTED = HexColor("#7A6A5A")


def fetch_qr_image(url: str, size: int = 280) -> io.BytesIO:
    """
    Pobiera obraz QR kodu z darmowego API qrserver.com.
    Zwraca BytesIO gotowe do wstawienia w ReportLab.
    """
    encoded = quote(url, safe='')
    api_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size={size}x{size}&data={encoded}&color=1A1208&bgcolor=FAF6F0"
        f"&margin=10&format=png&ecc=M"
    )
    resp = requests.get(api_url, timeout=15)
    if resp.status_code != 200:
        raise Exception(f"QR API error: {resp.status_code}")
    return io.BytesIO(resp.content)


def get_qr_message(has_video: bool, recipient_name: str, occasion: str) -> tuple:
    """
    Zwraca (headline, subtext) zależnie od rodzaju produktu.
    """
    name = recipient_name.strip()

    if has_video:
        headline = "Zeskanuj i oglądaj swój film 🎬"
        subtext  = "Spersonalizowany film z piosenką napisany i skomponowany specjalnie dla Ciebie."
    else:
        headline = "Zeskanuj i posłuchaj swojej piosenki 🎵"
        subtext  = "Spersonalizowana piosenka napisana i skomponowana specjalnie dla Ciebie."
    return headline, subtext


def create_qr_card(
    order: dict,
    media_url: str,     # URL do wideo (jeśli jest) lub MP3
    has_video: bool,
    order_id: str,
) -> bytes:
    """
    Tworzy piękną karteczkę A6 z kodem QR jako plik PDF w pamięci.

    Args:
        order:     dane zamówienia
        media_url: URL do wideo lub MP3 w Supabase Storage
        has_video: True jeśli pakiet zawiera wideo
        order_id:  ID zamówienia (do nazwy pliku)

    Returns:
        bytes: PDF gotowy do wysłania jako załącznik
    """
    recipient_name = order.get("recipient_name", "")
    occasion       = order.get("occasion", "")

    # Pobieramy QR kod
    print(f"[QR] Generuję QR kod dla: {media_url[:60]}...")
    qr_buffer = fetch_qr_image(media_url, size=300)
    print(f"[QR] ✅ QR kod pobrany")

    headline, subtext = get_qr_message(has_video, recipient_name, occasion)

    # ── Budujemy PDF A6 ────────────────────────────────────────
    buffer = io.BytesIO()
    # A6 = 105 × 148 mm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A6,
        rightMargin=8*mm,
        leftMargin=8*mm,
        topMargin=6*mm,
        bottomMargin=6*mm,
    )

    # Czcionki z obsługą polskich znaków
    font_normal, font_bold, font_italic = register_fonts()

    # Style
    s_logo = ParagraphStyle("Logo",
        fontSize=14, textColor=GOLD, alignment=TA_CENTER,
        fontName=font_bold, spaceAfter=1*mm)

    s_tagline = ParagraphStyle("Tagline",
        fontSize=6.5, textColor=MUTED, alignment=TA_CENTER,
        fontName=font_normal, spaceAfter=4*mm, letterSpacing=1.5)

    s_name = ParagraphStyle("Name",
        fontSize=16, textColor=DARK, alignment=TA_CENTER,
        fontName=font_bold, spaceAfter=1*mm)

    s_occasion = ParagraphStyle("Occasion",
        fontSize=9, textColor=GOLD, alignment=TA_CENTER,
        fontName=font_italic, spaceAfter=4*mm)

    s_headline = ParagraphStyle("Headline",
        fontSize=9.5, textColor=DARK, alignment=TA_CENTER,
        fontName=font_bold, spaceAfter=2*mm, leading=13)

    s_subtext = ParagraphStyle("Subtext",
        fontSize=7, textColor=MUTED, alignment=TA_CENTER,
        fontName=font_normal, leading=10, spaceAfter=4*mm)

    s_footer = ParagraphStyle("Footer",
        fontSize=6, textColor=MUTED, alignment=TA_CENTER,
        fontName=font_normal, letterSpacing=0.5)

    # ── Separator złota linia ──────────────────────────────────
    def gold_line():
        tbl = Table([[""]],
            colWidths=[89*mm], rowHeights=[0.6*mm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), GOLD),
            ("LINEABOVE",  (0,0), (-1,-1), 0, colors.white),
        ]))
        return tbl

    # ── Obraz QR ──────────────────────────────────────────────
    qr_image = Image(qr_buffer, width=48*mm, height=48*mm)

    story = [
        # Złota linia na górze
        gold_line(),
        Spacer(1, 5*mm),
        # Imię
        Paragraph(recipient_name, s_name),
        Spacer(1, 4*mm),
        # Okazja — wyraźny odstęp od imienia
        Paragraph(occasion, s_occasion),
        Spacer(1, 3*mm),
        # QR kod wyśrodkowany
        qr_image,
        Spacer(1, 4*mm),
        # Tekst zapraszający
        Paragraph(headline, s_headline),
        Paragraph(subtext, s_subtext),
        gold_line(),
        Spacer(1, 2*mm),
        # Stopka — tylko tu jest marka
        Paragraph("nutanazyczenie.pl  ·  Twój wyjątkowy prezent muzyczny", s_footer),
    ]

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    print(f"[QR] ✅ Kartka PDF wygenerowana ({len(pdf_bytes)//1024} KB)")
    return pdf_bytes
