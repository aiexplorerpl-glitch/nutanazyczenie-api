"""
AGENT 3 — PAKIECIARZ
====================
Odpowiada za:
1. Pobranie pliku audio z Supabase Storage
2. Stworzenie ładnego PDF z tekstem piosenki i wierszem
3. Wgranie PDF do Supabase Storage
4. Wysłanie emaila z linkami do pobrania przez Resend
5. Obsługę wysyłki do zamawiającego LUB bezpośrednio do obdarowanego
"""

import os
import io
import requests
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import resend
from supabase import create_client

resend.api_key = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "kontakt@nutanazyczenie.pl")

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

# Kolory marki
GOLD  = colors.HexColor("#C9963A")
DARK  = colors.HexColor("#1A1208")
MUTED = colors.HexColor("#7A6A5A")


def register_fonts():
    """
    Rejestruje bezpieczne czcionki dostępne na każdym serwerze Linux.
    Używamy DejaVu — wbudowanych w ReportLab od wersji 3.3.
    Fallback na Helvetica jeśli ReportLab jest starsze.
    """
    try:
        # DejaVu jest dostępne w reportlab >= 3.3 bez instalacji
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        pdfmetrics.registerFont(TTFont("DejaVu",      "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", "DejaVuSans-Bold.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Italic","DejaVuSans-Oblique.ttf"))
        registerFontFamily("DejaVu",
            normal="DejaVu",
            bold="DejaVu-Bold",
            italic="DejaVu-Italic",
            boldItalic="DejaVu-Bold",
        )
        return "DejaVu", "DejaVu-Bold", "DejaVu-Italic"
    except Exception:
        # Fallback — Helvetica jest zawsze dostępna w ReportLab
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


def create_pdf(order: dict, song_text: str, poem: str) -> bytes:
    """
    Tworzy PDF w pamięci (BytesIO) — nie zapisuje na dysk.
    Zwraca bajty PDF gotowe do wgrania do Supabase Storage.
    """
    font_normal, font_bold, font_italic = register_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2.5*cm, leftMargin=2.5*cm,
        topMargin=2.5*cm,   bottomMargin=2.5*cm,
    )

    styles = getSampleStyleSheet()

    s_title = ParagraphStyle("T",
        fontSize=26, textColor=GOLD, alignment=TA_CENTER,
        spaceAfter=4, fontName=font_bold)
    s_subtitle = ParagraphStyle("S",
        fontSize=12, textColor=DARK, alignment=TA_CENTER,
        spaceAfter=4, fontName=font_normal)
    s_meta = ParagraphStyle("M",
        fontSize=10, textColor=MUTED, alignment=TA_CENTER,
        spaceAfter=4, fontName=font_italic)
    s_section = ParagraphStyle("Sec",
        fontSize=9, textColor=GOLD, spaceAfter=6, spaceBefore=14,
        fontName=font_bold)
    s_tag = ParagraphStyle("Tag",
        fontSize=8, textColor=MUTED, spaceAfter=2, spaceBefore=8,
        fontName=font_italic)
    s_lyrics = ParagraphStyle("Lyr",
        fontSize=11, textColor=DARK, spaceAfter=3,
        fontName=font_normal, leftIndent=20, leading=16)
    s_poem = ParagraphStyle("Poe",
        fontSize=12, textColor=DARK, spaceAfter=4,
        fontName=font_italic, alignment=TA_CENTER, leading=18)
    s_footer = ParagraphStyle("Ft",
        fontSize=8, textColor=MUTED, alignment=TA_CENTER,
        fontName=font_normal)

    story = []

    # Nagłówek
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("NutaNaZyczenie", s_title))
    story.append(Paragraph("Muzyczne Prezenty", s_subtitle))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=6))
    story.append(Paragraph(
        f"Dla: {order['recipient_name']}  |  "
        f"Okazja: {order['occasion']}  |  "
        f"Data: {datetime.now().strftime('%d.%m.%Y')}",
        s_meta
    ))
    story.append(Spacer(1, 0.5*cm))

    # Tekst piosenki
    story.append(Paragraph("TWOJA SPERSONALIZOWANA PIOSENKA", s_section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=8))

    for line in song_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2*cm))
        elif line.startswith("[") and line.endswith("]"):
            story.append(Paragraph(line, s_tag))
        else:
            story.append(Paragraph(line, s_lyrics))

    story.append(Spacer(1, 0.8*cm))

    # Wiersz
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=8))
    story.append(Paragraph("WIERSZ NA ZYCZENIE (GRATIS)", s_section))
    story.append(Spacer(1, 0.3*cm))
    for line in poem.split("\n"):
        if line.strip():
            story.append(Paragraph(line.strip(), s_poem))

    story.append(Spacer(1, 0.8*cm))

    # Stopka
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=6))
    story.append(Paragraph(
        f"Dziekujemy za zamowienie!  |  nutanazyczenie.pl  |  {FROM_EMAIL}",
        s_footer
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    print(f"[Agent3] ✅ PDF wygenerowany ({len(pdf_bytes)//1024} KB)")
    return pdf_bytes


def upload_pdf(pdf_bytes: bytes, order_id: str) -> str:
    """Wgrywa PDF do Supabase Storage i zwraca publiczny URL."""
    filename = f"{order_id}/prezent.pdf"
    supabase.storage.from_("orders").upload(
        path=filename,
        file=pdf_bytes,
        file_options={"content-type": "application/pdf"},
    )
    url = supabase.storage.from_("orders").get_public_url(filename)
    print(f"[Agent3] ✅ PDF wgrany: {url}")
    return url


def send_email(order: dict, audio_url: str, pdf_url: str, audio_ext: str):
    """
    Wysyła email z linkami do pobrania.
    Zamiast załączników używamy linków — bezpieczniejsze i bez limitów rozmiaru.
    """
    recipient_email = order.get("recipient_email") or order["buyer_email"]
    is_direct = bool(order.get("recipient_email"))

    if is_direct:
        subject  = f"Masz wyjatkowy prezent muzyczny od {order['buyer_name']}!"
        greeting = f"Czesc {order['recipient_name']}!"
        intro    = (
            f"{order['buyer_name']} zamowil/a dla Ciebie spersonalizowana "
            f"piosenke na okazje: <b>{order['occasion']}</b>."
        )
    else:
        subject  = f"Twoj prezent dla {order['recipient_name']} jest gotowy!"
        greeting = f"Czesc {order['buyer_name']}!"
        intro    = (
            f"Twoja spersonalizowana piosenka dla "
            f"<b>{order['recipient_name']}</b> jest gotowa!"
        )

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;background:#FAF6F0;margin:0;padding:0;">
<div style="max-width:560px;margin:40px auto;background:white;
            border-radius:16px;overflow:hidden;
            box-shadow:0 4px 24px rgba(201,150,58,0.15);">

  <div style="background:#1A1208;padding:32px;text-align:center;">
    <div style="font-size:1.8rem;color:#C9963A;font-style:italic;font-weight:bold;">
      NutaNaZyczenie
    </div>
    <div style="font-size:0.8rem;color:rgba(250,246,240,0.5);letter-spacing:2px;">
      MUZYCZNE PREZENTY
    </div>
  </div>

  <div style="padding:36px 32px;">
    <p style="font-size:1.2rem;color:#1A1208;margin-bottom:16px;">{greeting}</p>
    <p style="color:#3D2B1F;line-height:1.7;margin-bottom:20px;">{intro}</p>

    <div style="margin:28px 0;">
      <a href="{audio_url}"
         style="display:block;background:#C9963A;color:white;text-align:center;
                padding:14px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;font-weight:500;margin-bottom:12px;">
        Pobierz piosenke (.{audio_ext})
      </a>
      <a href="{pdf_url}"
         style="display:block;background:transparent;color:#C9963A;text-align:center;
                padding:14px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;border:1.5px solid #C9963A;">
        Pobierz tekst i wiersz (PDF)
      </a>
    </div>

    <div style="background:#FAF6F0;border-left:4px solid #C9963A;
                border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:24px;">
      <p style="margin:0;color:#7A6A5A;font-style:italic;font-size:0.9rem;">
        Kazda piosenka jest unikalna — stworzona specjalnie dla jednej osoby,
        na jedna wyjatkowa chwile.
      </p>
    </div>

    <p style="color:#7A6A5A;font-size:0.85rem;line-height:1.6;">
      Pytania lub chcesz skorzystac z bezplatnej poprawki?<br>
      Napisz: <a href="mailto:{FROM_EMAIL}" style="color:#C9963A;">{FROM_EMAIL}</a>
    </p>
  </div>

  <div style="background:#1A1208;padding:20px;text-align:center;">
    <p style="color:rgba(250,246,240,0.4);font-size:0.75rem;margin:0;">
      2026 NutaNaZyczenie &nbsp;·&nbsp;
      <a href="https://nutanazyczenie.pl" style="color:#C9963A;">nutanazyczenie.pl</a>
    </p>
  </div>
</div>
</body></html>"""

    resend.Emails.send({
        "from":    f"NutaNaZyczenie <{FROM_EMAIL}>",
        "to":      [recipient_email],
        "subject": subject,
        "html":    html,
    })
    print(f"[Agent3] Email wysłany do: {recipient_email}")

    # Kopia do zamawiającego jeśli wysyłamy bezpośrednio
    if is_direct and order["buyer_email"] != recipient_email:
        resend.Emails.send({
            "from":    f"NutaNaZyczenie <{FROM_EMAIL}>",
            "to":      [order["buyer_email"]],
            "subject": f"Prezent dla {order['recipient_name']} wyslany!",
            "html":    f"""<p>Czesc {order['buyer_name']}!</p>
                          <p>Prezent dla <b>{order['recipient_name']}</b>
                          zostal wyslany na: {recipient_email}</p>
                          <p>Dziekujemy za zamowienie! <a href="https://nutanazyczenie.pl">nutanazyczenie.pl</a></p>""",
        })
        print(f"[Agent3] Potwierdzenie do: {order['buyer_email']}")


def run(order: dict, song_text: str, poem: str, audio_url: str, audio_ext: str = "mp3") -> dict:
    """
    Główna funkcja Agenta 3.

    Args:
        order:      dane zamówienia
        song_text:  tekst piosenki od Agenta 1
        poem:       wiersz od Agenta 1
        audio_url:  publiczny URL audio z Supabase (od Agenta 2)
        audio_ext:  rozszerzenie pliku audio (mp3 lub wav)

    Returns:
        dict: {success, pdf_url, error}
    """
    try:
        # Tworzymy PDF w pamięci
        pdf_bytes = create_pdf(order, song_text, poem)

        # Wgrywamy PDF do Supabase Storage
        pdf_url = upload_pdf(pdf_bytes, str(order["id"]))

        # Wysyłamy email z linkami
        send_email(order, audio_url, pdf_url, audio_ext)

        return {"success": True, "pdf_url": pdf_url}

    except Exception as e:
        print(f"[Agent3] Blad: {e}")
        return {"success": False, "pdf_url": None, "error": str(e)}
