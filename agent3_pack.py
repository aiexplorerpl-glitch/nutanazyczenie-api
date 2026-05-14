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
import base64
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
import agent3_qr

resend.api_key  = os.environ.get("RESEND_API_KEY")
FROM_EMAIL      = os.environ.get("FROM_EMAIL",    "zamowienia@nutanazyczenie.pl")
CONTACT_EMAIL   = os.environ.get("CONTACT_EMAIL", "kontakt@nutanazyczenie.pl")

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


def send_email(order: dict, audio_url: str, pdf_url: str, audio_ext: str,
               video_url: str = None, poem: str = "",
               audio_url2: str = None, video_url2: str = None):
    """Wysyła email z piosenką. Dla Premium dodaje drugą piosenkę i wideo."""
    """
    Wysyła email z linkami do pobrania.
    Zawiera podgląd wiersza inline, info o poprawce i nowe adresy email.
    """
    recipient_email = order.get("recipient_email") or order["buyer_email"]
    is_direct       = bool(order.get("recipient_email"))
    poprawki        = "2 bezpłatne poprawki" if order["package_type"] == "premium" else "1 bezpłatną poprawkę"

    if is_direct:
        subject  = f"🎵 Masz wyjątkowy prezent muzyczny od {order['buyer_name']}!"
        greeting = f"Cześć {order['recipient_name']}! 🎁"
        intro    = (
            f"{order['buyer_name']} zamówił/a dla Ciebie spersonalizowaną "
            f"piosenkę i wiersz na okazję: <strong>{order['occasion']}</strong> 💛"
        )
    else:
        subject  = f"🎵 Twój prezent dla {order['recipient_name']} jest gotowy!"
        greeting = f"Cześć {order['buyer_name']}! 🎁"
        intro    = (
            f"Twoja spersonalizowana piosenka i wiersz dla "
            f"<strong>{order['recipient_name']}</strong> są gotowe!"
        )

    # Przycisk wideo (tylko dla pakietów wideo/premium)
    video_btn = ""
    if video_url:
        video_btn = f"""
      <a href="{video_url}"
         style="display:block;background:#E05C3A;color:white;text-align:center;
                padding:15px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;font-weight:500;margin-bottom:12px;font-family:Arial,sans-serif;">
        🎬 Obejrzyj film wideo ze zdjęć
      </a>"""

    # Sekcja drugiej piosenki — tylko dla Premium
    second_song_block = ""
    if audio_url2:
        video2_btn = ""
        if video_url2:
            video2_btn = f"""
      <a href="{video_url2}"
         style="display:block;background:#E05C3A;color:white;text-align:center;
                padding:14px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;font-weight:500;margin-bottom:12px;font-family:Arial,sans-serif;">
        🎬 Obejrzyj film wideo 2 ze zdjęć
      </a>"""
        second_song_block = f"""
    <div style="margin-top:24px;padding-top:20px;
                border-top:1px dashed rgba(201,150,58,0.3);">
      <p style="font-size:0.85rem;color:#7A6A5A;margin:0 0 14px;
                font-style:italic;font-family:Arial,sans-serif;">
        👑 Druga piosenka (Pakiet Premium):
      </p>
      {video2_btn}
      <a href="{audio_url2}"
         style="display:block;background:transparent;color:#C9963A;text-align:center;
                padding:13px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;border:1.5px solid #C9963A;font-family:Arial,sans-serif;">
        🎵 Pobierz piosenkę 2
      </a>
    </div>"""

    # Wiersz wyświetlony inline w emailu
    poem_lines = poem.strip().split("\n") if poem else []
    poem_html  = "<br>".join(f"{line.strip()}" for line in poem_lines if line.strip())
    poem_block = ""
    if poem_html:
        poem_block = f"""
    <div style="background:#FAF6F0;border:1px solid rgba(201,150,58,0.2);
                border-left:4px solid #C9963A;border-radius:0 12px 12px 0;
                padding:20px 24px;margin-bottom:24px;">
      <div style="font-size:0.72rem;color:#C9963A;letter-spacing:2px;
                  text-transform:uppercase;font-family:Arial,sans-serif;
                  margin-bottom:12px;font-weight:bold;">
        📜 Wiersz na życzenie — gratis
      </div>
      <p style="margin:0;color:#3D2B1F;font-style:italic;line-height:1.9;font-size:1rem;">
        {poem_html}
      </p>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;background:#E8E0D8;margin:0;padding:40px 20px;">
<div style="max-width:560px;margin:0 auto;background:white;
            border-radius:16px;overflow:hidden;
            box-shadow:0 4px 24px rgba(0,0,0,0.12);">

  <div style="background:#1A1208;padding:36px 32px;text-align:center;">
    <div style="font-size:2rem;color:#C9963A;font-style:italic;font-weight:bold;
                font-family:Georgia,serif;">
      🎵 NutaNaŻyczenie
    </div>
    <div style="font-size:0.75rem;color:rgba(250,246,240,0.45);letter-spacing:3px;
                margin-top:6px;font-family:Arial,sans-serif;">
      MUZYCZNE PREZENTY
    </div>
  </div>

  <div style="padding:40px 36px;">
    <p style="font-size:1.2rem;color:#1A1208;margin:0 0 16px 0;font-weight:bold;">
      {greeting}
    </p>
    <p style="color:#3D2B1F;line-height:1.75;margin:0 0 28px 0;font-size:0.95rem;">
      {intro}
    </p>

    <div style="margin:0 0 28px 0;">
      {video_btn}
      <a href="{audio_url}"
         style="display:block;background:#C9963A;color:white;text-align:center;
                padding:15px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;font-weight:500;margin-bottom:12px;font-family:Arial,sans-serif;">
        🎵 Pobierz piosenkę (.{audio_ext})
      </a>
      <a href="{pdf_url}"
         style="display:block;background:transparent;color:#C9963A;text-align:center;
                padding:15px 24px;border-radius:100px;text-decoration:none;
                font-size:1rem;border:1.5px solid #C9963A;font-family:Arial,sans-serif;">
        📜 Pobierz tekst piosenki + wiersz (PDF)
      </a>
    </div>

    {second_song_block}

    {poem_block}

    <div style="background:#FFF8EE;border:1px solid rgba(201,150,58,0.25);
                border-radius:12px;padding:18px 20px;margin-bottom:24px;">
      <p style="margin:0 0 8px 0;color:#8B5E0A;font-size:0.9rem;font-weight:bold;
                font-family:Arial,sans-serif;">
        🎁 Twój prezent jest też gotowy do wręczenia!
      </p>
      <p style="margin:0;color:#5A3A10;font-size:0.85rem;line-height:1.65;
                font-family:Arial,sans-serif;">
        W załączniku znajdziesz <strong>eleganką kartkę z kodem QR</strong>
        — wydrukuj ją i wręcz jako fizyczny prezent. Wystarczy że obdarowana
        osoba zeskanuje telefonem kod i natychmiast usłyszy swoją piosenkę
        {'lub obejrzy film' if video_url else ''}. ✨
      </p>
    </div>

    <div style="background:#F0F8FF;border-radius:12px;padding:16px 20px;margin-bottom:24px;">
      <p style="margin:0;color:#1565C0;font-size:0.88rem;line-height:1.6;font-family:Arial,sans-serif;">
        💡 <strong>Masz {poprawki}</strong> — jeśli chcesz zmienić coś
        w tekście lub muzyce, napisz do nas w ciągu 7 dni.
      </p>
    </div>

    <p style="color:#7A6A5A;font-size:0.85rem;line-height:1.7;
              font-family:Arial,sans-serif;margin:0;">
      Pytania lub chcesz skorzystać z poprawki?<br>
      Napisz: <a href="mailto:{FROM_EMAIL}" style="color:#C9963A;">{FROM_EMAIL}</a>
    </p>
  </div>

  <div style="background:#1A1208;padding:24px 32px;text-align:center;">
    <div style="margin-bottom:10px;">
      <a href="https://nutanazyczenie.pl/regulamin.html"
         style="color:rgba(250,246,240,0.4);font-size:0.75rem;text-decoration:none;
                font-family:Arial,sans-serif;margin:0 8px;">Regulamin</a>
      <span style="color:rgba(250,246,240,0.2);">·</span>
      <a href="https://nutanazyczenie.pl/regulamin.html#polityka-prywatnosci"
         style="color:rgba(250,246,240,0.4);font-size:0.75rem;text-decoration:none;
                font-family:Arial,sans-serif;margin:0 8px;">Polityka prywatności</a>
      <span style="color:rgba(250,246,240,0.2);">·</span>
      <a href="mailto:{CONTACT_EMAIL}"
         style="color:rgba(250,246,240,0.4);font-size:0.75rem;text-decoration:none;
                font-family:Arial,sans-serif;margin:0 8px;">Kontakt</a>
    </div>
    <p style="color:rgba(250,246,240,0.3);font-size:0.72rem;margin:0;font-family:Arial,sans-serif;">
      © 2026 NutaNaŻyczenie &nbsp;·&nbsp;
      <a href="https://nutanazyczenie.pl" style="color:#C9963A;">nutanazyczenie.pl</a>
    </p>
  </div>
</div>
</body></html>"""

    # ── Generujemy kartkę z QR kodem ─────────────────────────
    has_video  = bool(video_url)
    media_url  = video_url if has_video else audio_url  # QR → wideo lub MP3
    qr_card_bytes = None
    qr_attachment = []

    try:
        qr_card_bytes = agent3_qr.create_qr_card(
            order, media_url, has_video, str(order["id"])
        )
        qr_attachment = [{
            "filename": f"Kartka_QR_{order['recipient_name']}.pdf",
            "content":  base64.b64encode(qr_card_bytes).decode("utf-8"),
        }]
        print(f"[Agent3] ✅ Kartka QR gotowa")
    except Exception as e:
        print(f"[Agent3] ⚠️ QR błąd (kontynuuję bez kartki): {e}")

    # ── Wysyłamy email ────────────────────────────────────────
    email_data = {
        "from":    f"NutaNaŻyczenie <{FROM_EMAIL}>",
        "to":      [recipient_email],
        "subject": subject,
        "html":    html,
    }
    if qr_attachment:
        email_data["attachments"] = qr_attachment
    resend.Emails.send(email_data)
    print(f"[Agent3] ✅ Email wysłany do: {recipient_email}")

    # Kopia potwierdzenia do zamawiającego
    if is_direct and order["buyer_email"] != recipient_email:
        confirm_html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;background:#E8E0D8;margin:0;padding:40px 20px;">
<div style="max-width:560px;margin:0 auto;background:white;border-radius:16px;overflow:hidden;
            box-shadow:0 4px 24px rgba(0,0,0,0.12);">
  <div style="background:#1A1208;padding:28px;text-align:center;">
    <div style="font-size:1.8rem;color:#C9963A;font-style:italic;font-weight:bold;
                font-family:Georgia,serif;">🎵 NutaNaŻyczenie</div>
  </div>
  <div style="padding:36px 32px;">
    <p style="font-size:1.1rem;color:#1A1208;margin:0 0 16px 0;">
      Cześć {order['buyer_name']}! ✅
    </p>
    <p style="color:#3D2B1F;line-height:1.75;margin:0 0 20px 0;">
      Prezent dla <strong>{order['recipient_name']}</strong>
      został wysłany bezpośrednio na jej/jego adres email.
    </p>
    <div style="background:#F0FFF4;border-left:4px solid #2E7D32;
                border-radius:0 12px 12px 0;padding:16px 20px;margin-bottom:24px;">
      <p style="margin:0;color:#1B5E20;font-size:0.9rem;line-height:1.8;font-family:Arial,sans-serif;">
        ✅ Piosenka wygenerowana<br>
        ✅ Wiersz dołączony<br>
        {"✅ Film wideo wygenerowany<br>" if video_url else ""}
        ✅ Email wysłany do {order['recipient_name']}<br>
        ✅ Zamówienie zrealizowane
      </p>
    </div>
    <p style="color:#7A6A5A;font-size:0.85rem;line-height:1.7;font-family:Arial,sans-serif;margin:0;">
      Dziękujemy za zaufanie! Mamy nadzieję że {order['recipient_name']} będzie zachwycona/y 💛<br><br>
      Pytania lub poprawka? Napisz:
      <a href="mailto:{FROM_EMAIL}" style="color:#C9963A;">{FROM_EMAIL}</a>
    </p>
  </div>
  <div style="background:#1A1208;padding:20px;text-align:center;">
    <p style="color:rgba(250,246,240,0.3);font-size:0.72rem;margin:0;font-family:Arial,sans-serif;">
      © 2026 NutaNaŻyczenie &nbsp;·&nbsp;
      <a href="https://nutanazyczenie.pl" style="color:#C9963A;">nutanazyczenie.pl</a>
    </p>
  </div>
</div>
</body></html>"""

        resend.Emails.send({
            "from":    f"NutaNaŻyczenie <{FROM_EMAIL}>",
            "to":      [order["buyer_email"]],
            "subject": f"✅ Prezent dla {order['recipient_name']} wysłany!",
            "html":    confirm_html,
        })
        print(f"[Agent3] ✅ Potwierdzenie do: {order['buyer_email']}")


def run(order: dict, song_text: str, poem: str, audio_url: str,
        audio_ext: str = "mp3", video_url: str = None,
        song_text2: str = None, poem2: str = None,
        audio_url2: str = None, video_url2: str = None) -> dict:
    """
    Główna funkcja Agenta 3.

    Piosenka / Wideo:  1 email z piosenką + wideo + wierszem
    Premium:           2 osobne emaile — każda piosenka jako oddzielna wiadomość,
                       wysyłana na osobny adres jeśli klient podał recipient_email2
    """
    try:
        is_premium = order["package_type"] == "premium"

        # ── PDF dla piosenki 1 ────────────────────────────────
        pdf_bytes = create_pdf(order, song_text, poem)
        pdf_url   = upload_pdf(pdf_bytes, str(order["id"]))

        # ── Email 1 — pierwsza piosenka ───────────────────────
        send_email(order, audio_url, pdf_url, audio_ext,
                   video_url=video_url, poem=poem)
        print(f"[Agent3] ✅ Email 1 wysłany")

        # ── Email 2 — druga piosenka (tylko Premium) ──────────
        if is_premium and audio_url2 and song_text2:
            # Budujemy dane dla drugiej piosenki
            order2 = {
                **order,
                "recipient_name":  order.get("recipient_name2", order["recipient_name"]),
                "occasion":        order.get("occasion2",       order["occasion"]),
                # Email odbiorcy — jeśli klient podał osobny adres dla piosenki 2
                "recipient_email": order.get("recipient_email2") or order.get("recipient_email"),
            }

            # PDF dla piosenki 2
            pdf_bytes2 = create_pdf(order2, song_text2, poem2 or "")
            pdf_url2   = upload_pdf(pdf_bytes2, f"{order['id']}_2")

            send_email(order2, audio_url2, pdf_url2, audio_ext,
                       video_url=video_url2, poem=poem2 or "")
            print(f"[Agent3] ✅ Email 2 (Premium) wysłany")

        return {"success": True, "pdf_url": pdf_url}

    except Exception as e:
        print(f"[Agent3] Blad: {e}")
        return {"success": False, "pdf_url": None, "error": str(e)}
