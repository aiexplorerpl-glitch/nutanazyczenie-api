"""
AGENT 3 — PAKIECIARZ
====================
Odpowiada za:
1. Stworzenie ładnego PDF z tekstem piosenki i wierszem (z logo)
2. Wysłanie emaila z załącznikami (MP3 + PDF) przez Resend
3. Obsługę wysyłki do zamawiającego LUB bezpośrednio do obdarowanego
"""

import os
import base64
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import resend

resend.api_key = os.environ.get("RESEND_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "kontakt@nutanazyczenie.pl")

# Kolory marki
GOLD = colors.HexColor("#C9963A")
DARK = colors.HexColor("#1A1208")
CREAM = colors.HexColor("#FAF6F0")
MUTED = colors.HexColor("#7A6A5A")


def create_pdf(order: dict, song_text: str, poem: str, order_id: str) -> str:
    """
    Tworzy piękny PDF z tekstem piosenki i wierszem.
    Zawiera logo marki, dane zamówienia i sformatowany tekst.

    Returns:
        str: ścieżka do wygenerowanego pliku PDF
    """
    os.makedirs("/tmp/nutanazyczenie", exist_ok=True)
    pdf_path = f"/tmp/nutanazyczenie/{order_id}_prezent.pdf"

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        rightMargin=2.5 * cm,
        leftMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()

    # Style własne
    style_title = ParagraphStyle(
        "Title",
        parent=styles["Normal"],
        fontSize=28,
        textColor=GOLD,
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName="Helvetica-BoldOblique",
    )
    style_subtitle = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=13,
        textColor=DARK,
        alignment=TA_CENTER,
        spaceAfter=6,
        fontName="Helvetica",
    )
    style_meta = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=10,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName="Helvetica-Oblique",
    )
    style_section = ParagraphStyle(
        "Section",
        parent=styles["Normal"],
        fontSize=9,
        textColor=GOLD,
        spaceAfter=6,
        spaceBefore=16,
        fontName="Helvetica-Bold",
        leftIndent=0,
    )
    style_tag = ParagraphStyle(
        "Tag",
        parent=styles["Normal"],
        fontSize=8,
        textColor=MUTED,
        spaceAfter=2,
        spaceBefore=8,
        fontName="Helvetica-Oblique",
    )
    style_lyrics = ParagraphStyle(
        "Lyrics",
        parent=styles["Normal"],
        fontSize=11,
        textColor=DARK,
        spaceAfter=3,
        fontName="Helvetica",
        leftIndent=20,
        leading=16,
    )
    style_poem = ParagraphStyle(
        "Poem",
        parent=styles["Normal"],
        fontSize=12,
        textColor=DARK,
        spaceAfter=4,
        fontName="Helvetica-Oblique",
        alignment=TA_CENTER,
        leading=18,
    )

    story = []

    # ── NAGŁÓWEK ──────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("🎵 NutaNaŻyczenie", style_title))
    story.append(Paragraph("Muzyczne Prezenty", style_subtitle))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=6))

    # Dane zamówienia
    story.append(Paragraph(
        f"Dla: <b>{order['recipient_name']}</b> &nbsp;·&nbsp; "
        f"Okazja: <b>{order['occasion']}</b> &nbsp;·&nbsp; "
        f"Data: {datetime.now().strftime('%d.%m.%Y')}",
        style_meta
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── TEKST PIOSENKI ────────────────────────────────────────
    story.append(Paragraph("♪  TWOJA SPERSONALIZOWANA PIOSENKA", style_section))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=8))

    # Parsujemy tekst piosenki — szukamy tagów [Verse], [Chorus] itp.
    lines = song_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 0.2 * cm))
            continue

        # Tagi struktury jak [Chorus], [Verse 1] itp.
        if line.startswith("[") and line.endswith("]"):
            story.append(Paragraph(line, style_tag))
        else:
            # Normalna linijka tekstu
            story.append(Paragraph(line, style_lyrics))

    story.append(Spacer(1, 0.8 * cm))

    # ── WIERSZ ────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=GOLD, spaceAfter=8))
    story.append(Paragraph("📜  WIERSZ NA ŻYCZENIE (GRATIS)", style_section))
    story.append(Spacer(1, 0.3 * cm))

    poem_lines = poem.split("\n")
    for line in poem_lines:
        if line.strip():
            story.append(Paragraph(line.strip(), style_poem))

    story.append(Spacer(1, 0.8 * cm))

    # ── STOPKA ────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=6))
    story.append(Paragraph(
        "Dziękujemy za zamówienie! 💛 &nbsp;·&nbsp; nutanazyczenie.pl &nbsp;·&nbsp; "
        "kontakt@nutanazyczenie.pl",
        style_meta
    ))
    story.append(Paragraph(
        "Ten prezent został stworzony specjalnie dla Ciebie przez NutaNaŻyczenie — "
        "Muzyczne Prezenty na każdą okazję.",
        ParagraphStyle(
            "Footer2",
            parent=styles["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        )
    ))

    doc.build(story)
    print(f"[Agent3] ✅ PDF gotowy: {pdf_path}")
    return pdf_path


def send_email(order: dict, mp3_path: str, pdf_path: str) -> bool:
    """
    Wysyła email z gotowym prezentem przez Resend.
    Jeśli klient podał email odbiorcy → wysyłamy bezpośrednio do niego.
    Jeśli nie → wysyłamy do zamawiającego.
    Zawsze wysyłamy kopię potwierdzenia do zamawiającego.
    """

    # Odczytujemy pliki jako base64 do załączników
    with open(mp3_path, "rb") as f:
        mp3_data = base64.b64encode(f.read()).decode("utf-8")

    with open(pdf_path, "rb") as f:
        pdf_data = base64.b64encode(f.read()).decode("utf-8")

    attachments = [
        {
            "filename": f"Piosenka_dla_{order['recipient_name']}.mp3",
            "content": mp3_data,
        },
        {
            "filename": f"Tekst_i_wiersz_{order['recipient_name']}.pdf",
            "content": pdf_data,
        },
    ]

    # ── EMAIL DO ODBIORCY (lub zamawiającego) ─────────────────
    recipient_email = order.get("recipient_email") or order["buyer_email"]
    is_direct = bool(order.get("recipient_email"))

    if is_direct:
        # Wysyłamy bezpośrednio do solenizanta
        subject = f"🎵 Masz wyjątkowy prezent muzyczny od {order['buyer_name']}!"
        greeting = f"Cześć {order['recipient_name']}!"
        intro = (
            f"{order['buyer_name']} zamówił/a dla Ciebie spersonalizowaną "
            f"piosenkę i wiersz na okazję: <b>{order['occasion']}</b>. "
            "W załączniku znajdziesz:"
        )
    else:
        # Wysyłamy do zamawiającego
        subject = f"🎵 Twój prezent dla {order['recipient_name']} jest gotowy!"
        greeting = f"Cześć {order['buyer_name']}!"
        intro = (
            f"Twoja spersonalizowana piosenka i wiersz dla "
            f"<b>{order['recipient_name']}</b> są gotowe! "
            "W załączniku znajdziesz:"
        )

    html_body = f"""
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family: Georgia, serif; background: #FAF6F0; margin: 0; padding: 0;">
  <div style="max-width: 560px; margin: 40px auto; background: white;
              border-radius: 16px; overflow: hidden;
              box-shadow: 0 4px 24px rgba(201,150,58,0.15);">

    <!-- Header -->
    <div style="background: #1A1208; padding: 32px; text-align: center;">
      <div style="font-size: 2rem; color: #C9963A; font-style: italic;
                  font-weight: bold; margin-bottom: 4px;">🎵 NutaNaŻyczenie</div>
      <div style="font-size: 0.85rem; color: rgba(250,246,240,0.5);
                  letter-spacing: 2px;">MUZYCZNE PREZENTY</div>
    </div>

    <!-- Body -->
    <div style="padding: 36px 32px;">
      <p style="font-size: 1.2rem; color: #1A1208; margin-bottom: 16px;">
        {greeting}
      </p>
      <p style="color: #3D2B1F; line-height: 1.7; margin-bottom: 20px;">
        {intro}
      </p>
      <ul style="color: #3D2B1F; line-height: 2; margin-bottom: 24px;">
        <li>🎵 <b>Piosenka MP3</b> — gotowa do odsłuchania</li>
        <li>📜 <b>PDF z tekstem</b> — piosenka + wiersz na życzenie</li>
      </ul>
      <div style="background: #FAF6F0; border-left: 4px solid #C9963A;
                  border-radius: 0 12px 12px 0; padding: 16px 20px;
                  margin-bottom: 24px;">
        <p style="margin: 0; color: #7A6A5A; font-style: italic; font-size: 0.95rem;">
          "Każda piosenka jest unikalna — stworzona specjalnie dla jednej osoby,
          na jedną wyjątkową chwilę." 💛
        </p>
      </div>
      <p style="color: #7A6A5A; font-size: 0.9rem; line-height: 1.6;">
        Jeśli masz pytania lub chcesz skorzystać z bezpłatnej poprawki,
        napisz do nas: <a href="mailto:{FROM_EMAIL}" style="color: #C9963A;">{FROM_EMAIL}</a>
      </p>
    </div>

    <!-- Footer -->
    <div style="background: #1A1208; padding: 20px 32px; text-align: center;">
      <p style="color: rgba(250,246,240,0.4); font-size: 0.78rem; margin: 0;">
        © 2026 NutaNaŻyczenie &nbsp;·&nbsp;
        <a href="https://nutanazyczenie.pl" style="color: #C9963A;">nutanazyczenie.pl</a>
      </p>
    </div>
  </div>
</body>
</html>
"""

    # Wysyłamy email do odbiorcy/zamawiającego
    resend.Emails.send({
        "from": f"NutaNaŻyczenie <{FROM_EMAIL}>",
        "to": [recipient_email],
        "subject": subject,
        "html": html_body,
        "attachments": attachments,
    })
    print(f"[Agent3] ✅ Email wysłany do: {recipient_email}")

    # ── KOPIA POTWIERDZENIA DO ZAMAWIAJĄCEGO ──────────────────
    if is_direct and order["buyer_email"] != recipient_email:
        confirm_html = f"""
<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family: Georgia, serif; background: #FAF6F0; margin: 0; padding: 0;">
  <div style="max-width: 560px; margin: 40px auto; background: white;
              border-radius: 16px; overflow: hidden;
              box-shadow: 0 4px 24px rgba(201,150,58,0.15);">
    <div style="background: #1A1208; padding: 32px; text-align: center;">
      <div style="font-size: 2rem; color: #C9963A; font-style: italic; font-weight: bold;">
        🎵 NutaNaŻyczenie
      </div>
    </div>
    <div style="padding: 36px 32px;">
      <p style="font-size: 1.1rem; color: #1A1208;">Cześć {order['buyer_name']}!</p>
      <p style="color: #3D2B1F; line-height: 1.7;">
        ✅ Twój prezent dla <b>{order['recipient_name']}</b> został właśnie
        wysłany bezpośrednio na adres: <b>{recipient_email}</b>
      </p>
      <p style="color: #3D2B1F; line-height: 1.7;">
        Dziękujemy za zamówienie! Mamy nadzieję że {order['recipient_name']}
        będzie zachwycona/y 💛
      </p>
      <p style="color: #7A6A5A; font-size: 0.9rem;">
        Pytania? Napisz: <a href="mailto:{FROM_EMAIL}" style="color: #C9963A;">{FROM_EMAIL}</a>
      </p>
    </div>
    <div style="background: #1A1208; padding: 20px; text-align: center;">
      <p style="color: rgba(250,246,240,0.4); font-size: 0.78rem; margin: 0;">
        © 2026 NutaNaŻyczenie &nbsp;·&nbsp;
        <a href="https://nutanazyczenie.pl" style="color: #C9963A;">nutanazyczenie.pl</a>
      </p>
    </div>
  </div>
</body>
</html>
"""
        resend.Emails.send({
            "from": f"NutaNaŻyczenie <{FROM_EMAIL}>",
            "to": [order["buyer_email"]],
            "subject": f"✅ Prezent dla {order['recipient_name']} wysłany!",
            "html": confirm_html,
        })
        print(f"[Agent3] ✅ Potwierdzenie wysłane do: {order['buyer_email']}")

    return True


def run(order: dict, song_text: str, poem: str, mp3_path: str) -> dict:
    """
    Główna funkcja Agenta 3 — uruchamiana przez main.py.

    Args:
        order: dane zamówienia
        song_text: tekst piosenki od Agenta 1
        poem: wiersz od Agenta 1
        mp3_path: ścieżka do MP3 od Agenta 2

    Returns:
        dict: {success, pdf_path, error}
    """
    try:
        # Tworzymy PDF
        pdf_path = create_pdf(order, song_text, poem, str(order["id"]))

        # Wysyłamy email z załącznikami
        send_email(order, mp3_path, pdf_path)

        return {"success": True, "pdf_path": pdf_path}

    except Exception as e:
        print(f"[Agent3] ❌ Błąd: {e}")
        return {"success": False, "pdf_path": None, "error": str(e)}
