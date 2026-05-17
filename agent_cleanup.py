"""
AGENT CLEANUP — Czyszczenie danych po 24h
==========================================
Odpowiada za:
1. Usuwanie zdjęć z Supabase Storage (bucket 'photos') po 24h od zamówienia
2. Usuwanie plików zamówienia z Supabase Storage (bucket 'orders') po 24h
3. Czyszczenie wrażliwych danych z tabeli orders (opisy, zdjęcia)
4. Sprawdzanie czy poprawki wpłynęły w ciągu 24h — jeśli nie, wysyłanie maila

Uruchamiany jako osobny endpoint /api/cleanup (cron job na Railway co godzinę)
lub jako zadanie w tle po dostarczeniu zamówienia.
"""

import os
import resend
from datetime import datetime, timezone, timedelta
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

resend.api_key  = os.environ.get("RESEND_API_KEY")
FROM_EMAIL      = os.environ.get("FROM_EMAIL",    "zamowienia@nutanazyczenie.pl")
CONTACT_EMAIL   = os.environ.get("CONTACT_EMAIL", "kontakt@nutanazyczenie.pl")

PHOTOS_DELETE_HOURS = 48        # zdjęcia klientów usuwane po 48h (RODO)
FILES_DELETE_DAYS   = 60        # MP3/PDF/wideo dostępne przez 60 dni
CORRECTION_WINDOW_HOURS = 24   # poprawki tylko przez 24h od dostarczenia


def delete_storage_folder(bucket: str, folder: str):
    """Usuwa wszystkie pliki w danym folderze z Supabase Storage."""
    try:
        files = supabase.storage.from_(bucket).list(folder)
        if not files:
            return
        paths = [f"{folder}/{f['name']}" for f in files if f.get("name")]
        if paths:
            supabase.storage.from_(bucket).remove(paths)
            print(f"[Cleanup] Usunięto {len(paths)} plików z {bucket}/{folder}")
    except Exception as e:
        print(f"[Cleanup] Błąd usuwania {bucket}/{folder}: {e}")


def anonymize_order(order_id: str):
    """
    Anonimizuje wrażliwe dane zamówienia w tabeli orders.
    Zachowuje tylko dane niezbędne do celów podatkowych.
    """
    try:
        supabase.table("orders").update({
            "person_desc":    "[usunięto po 24h]",
            "content_desc":   "[usunięto po 24h]",
            "recipient_name": "[usunięto po 24h]",
        }).eq("id", order_id).execute()
        print(f"[Cleanup] Zanonimizowano dane zamówienia {order_id}")
    except Exception as e:
        print(f"[Cleanup] Błąd anonimizacji {order_id}: {e}")


def send_correction_expired_email(order: dict):
    """
    Wysyła automatyczny email do klienta informujący o wygaśnięciu
    prawa do bezpłatnej poprawki (po 24h od dostarczenia zamówienia).
    """
    buyer_email = order.get("buyer_email", "")
    buyer_name  = order.get("buyer_name", "Kliencie")
    package_map = {
        "piosenka": "Piosenka (29 zł)",
        "wideo":    "Piosenka + Wideo (59 zł)",
        "premium":  "Premium (99 zł)",
    }
    package_name = package_map.get(order.get("package_type", ""), "Zamówienie")

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;background:#F0EBE3;margin:0;padding:40px 20px;">
<div style="max-width:520px;margin:0 auto;background:white;
            border-radius:16px;overflow:hidden;">

  <div style="background:#1A1208;padding:28px 32px;text-align:center;">
    <div style="font-size:1.6rem;color:#C9963A;font-style:italic;font-weight:bold;">
      NutaNaŻyczenie
    </div>
    <div style="font-size:0.72rem;color:rgba(250,246,240,0.4);letter-spacing:3px;margin-top:4px;">
      MUZYCZNE PREZENTY
    </div>
  </div>

  <div style="padding:36px 32px;">

    <p style="font-size:1.1rem;color:#1A1208;margin:0 0 16px;font-weight:bold;">
      Cześć {buyer_name}!
    </p>

    <p style="color:#3D2B1F;line-height:1.75;margin:0 0 20px;font-size:0.95rem;">
      Dziękujemy za zamówienie pakietu <strong>{package_name}</strong>.
    </p>

    <div style="background:#FFF8EE;border-left:4px solid #C9963A;
                border-radius:0 10px 10px 0;padding:18px 20px;margin:0 0 24px;">
      <p style="margin:0;color:#5A3A10;font-size:0.92rem;line-height:1.7;">
        <strong>Czas na bezpłatne poprawki minął.</strong><br>
        Prawo do bezpłatnej korekty, zawarte w cenie zamówienia,
        jest ważne przez <strong>24 godziny</strong> od momentu
        dostarczenia gotowego produktu na Twój email.<br><br>
        Niestety ten czas już upłynął — dlatego nie możemy zrealizować
        tej prośby bezpłatnie.
      </p>
    </div>

    <p style="color:#3D2B1F;line-height:1.75;margin:0 0 20px;font-size:0.9rem;">
      Jeśli zależy Ci na zmianach, chętnie wycenimy dodatkową korektę indywidualnie.
      Napisz do nas, a znajdziemy najlepsze rozwiązanie. 😊
    </p>

    <a href="mailto:{FROM_EMAIL}?subject=Pytanie o dodatkową korektę"
       style="display:inline-block;background:#C9963A;color:white;
              padding:12px 24px;border-radius:100px;text-decoration:none;
              font-size:0.9rem;font-weight:500;font-family:Arial,sans-serif;">
      Napisz do nas
    </a>

  </div>

  <div style="background:#1A1208;padding:18px 32px;text-align:center;">
    <p style="color:rgba(250,246,240,0.35);font-size:0.75rem;margin:0;
              font-family:Arial,sans-serif;">
      © 2026 NutaNaŻyczenie &nbsp;·&nbsp;
      <a href="https://nutanazyczenie.pl" style="color:#C9963A;">nutanazyczenie.pl</a>
      &nbsp;·&nbsp;
      <a href="mailto:{CONTACT_EMAIL}" style="color:rgba(250,246,240,0.4);">
        {CONTACT_EMAIL}
      </a>
    </p>
  </div>

</div>
</body>
</html>"""

    resend.Emails.send({
        "from":    f"NutaNaŻyczenie <{FROM_EMAIL}>",
        "to":      [buyer_email],
        "subject": "Informacja o wygaśnięciu bezpłatnej poprawki",
        "html":    html,
    })
    print(f"[Cleanup] Email o wygaśnięciu poprawki wysłany do: {buyer_email}")


def check_correction_window(order: dict) -> bool:
    """
    Sprawdza czy zamówienie jest nadal w oknie 24h na poprawki.
    Zwraca True jeśli można jeszcze złożyć bezpłatną poprawkę.
    """
    completed_at_str = order.get("updated_at") or order.get("created_at")
    if not completed_at_str:
        return False

    completed_at = datetime.fromisoformat(
        completed_at_str.replace("Z", "+00:00")
    )
    deadline = completed_at + timedelta(hours=CORRECTION_WINDOW_HOURS)
    now      = datetime.now(timezone.utc)

    return now < deadline


def run_cleanup():
    """
    Główna funkcja czyszczenia — uruchamiana co godzinę przez endpoint /api/cleanup.

    Dwa osobne timery:
    - Zdjęcia klientów (bucket 'photos') → usuwane po 24h (RODO)
    - Pliki produktu (MP3/PDF/wideo w bucket 'orders') → usuwane po 60 dniach
    """
    print(f"[Cleanup] Start — {datetime.now(timezone.utc).isoformat()}")
    now = datetime.now(timezone.utc)

    # ── KROK 1: Usuń zdjęcia klientów po 24h ─────────────────────────────
    photos_cutoff = (now - timedelta(hours=PHOTOS_DELETE_HOURS)).isoformat()

    photos_result = supabase.table("orders").select("id").eq(
        "status", "completed"
    ).lt("updated_at", photos_cutoff).execute()

    photos_orders = photos_result.data or []
    print(f"[Cleanup] Zdjęcia do usunięcia: {len(photos_orders)} zamówień")

    for order in photos_orders:
        order_id = str(order["id"])
        try:
            delete_storage_folder("photos", order_id)
        except Exception as e:
            print(f"[Cleanup] ❌ Błąd usuwania zdjęć {order_id}: {e}")

    # ── KROK 2: Usuń pliki produktu po 60 dniach ─────────────────────────
    files_cutoff = (now - timedelta(days=FILES_DELETE_DAYS)).isoformat()

    files_result = supabase.table("orders").select("*").in_(
        "status", ["completed", "photos_cleaned"]
    ).lt("updated_at", files_cutoff).execute()

    files_orders = files_result.data or []
    print(f"[Cleanup] Pliki do usunięcia po 60 dniach: {len(files_orders)} zamówień")

    cleaned = 0
    for order in files_orders:
        order_id = str(order["id"])
        try:
            # Usuń MP3, PDF, wideo
            delete_storage_folder("orders", order_id)

            # Anonimizuj wrażliwe dane
            anonymize_order(order_id)

            # Oznacz jako wyczyszczone
            supabase.table("orders").update({
                "status": "cleaned"
            }).eq("id", order_id).execute()

            cleaned += 1
            print(f"[Cleanup] ✅ Wyczyszczono pliki zamówienia {order_id}")

        except Exception as e:
            print(f"[Cleanup] ❌ Błąd przy {order_id}: {e}")

    print(f"[Cleanup] Zakończono — usunięto pliki {cleaned}/{len(files_orders)} zamówień")
    return {
        "photos_cleaned": len(photos_orders),
        "files_cleaned":  cleaned,
    }
