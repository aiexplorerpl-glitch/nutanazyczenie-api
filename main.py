"""
MAIN.PY — ORKIESTRATOR v2
==========================
Zmiany względem v1:
- Endpoint /api/order przyjmuje FormData zamiast JSON
  (obsługa przesyłania zdjęć klientów)
- Zdjęcia wgrywane do Supabase Storage bucket "photos"
- Pipeline uruchamia Agent 4 (wideo) dla pakietów wideo/premium
- Agent 3 otrzymuje video_url i wysyła email z linkiem do wideo
"""

import os
import uuid
import stripe
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

stripe.api_key          = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET   = os.environ.get("STRIPE_WEBHOOK_SECRET")
BASE_URL                = os.environ.get("BASE_URL", "https://nutanazyczenie.pl")

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

import agent1_text
import agent2_music
import agent3_pack
import agent4_video
import agent_cleanup

app = FastAPI(title="NutaNaZyczenie API v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nutanazyczenie.pl",
                   "https://www.nutanazyczenie.pl",
                   "http://localhost"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


# ── Przyjmowanie zamówień (FormData + zdjęcia) ────────────────────────────────
@app.post("/api/order")
async def create_order(
    buyer_name:      str            = Form(...),
    buyer_email:     str            = Form(...),
    recipient_name:  str            = Form(...),
    occasion:        str            = Form(...),
    package_type:    str            = Form(...),
    person_desc:     str            = Form(...),
    content_desc:    str            = Form(...),
    music_style:     str            = Form("pop"),
    recipient_email: Optional[str]  = Form(None),
    # Pola drugiej piosenki (tylko Premium)
    recipient_name2:  Optional[str]  = Form(None),
    occasion2:        Optional[str]  = Form(None),
    person_desc2:     Optional[str]  = Form(None),
    content_desc2:    Optional[str]  = Form(None),
    music_style2:     Optional[str]  = Form(None),
    recipient_email2: Optional[str]  = Form(None),
    photos:           List[UploadFile] = File(default=[]),
):
    """
    Przyjmuje dane formularza jako FormData.
    Zdjęcia (opcjonalne dla pakietu piosenka) wgrywane do Supabase Storage.
    Tworzy sesję Stripe Checkout i zwraca URL do płatności.
    """
    # Walidacja pakietu
    price_map = {
        "piosenka": os.environ.get("STRIPE_PRICE_PIOSENKA"),
        "wideo":    os.environ.get("STRIPE_PRICE_WIDEO"),
        "premium":  os.environ.get("STRIPE_PRICE_PREMIUM"),
    }
    if package_type not in price_map:
        raise HTTPException(400, f"Nieprawidłowy pakiet: {package_type}")

    price_id = price_map[package_type]
    if not price_id:
        raise HTTPException(500, "Brak konfiguracji ceny dla tego pakietu")

    # Walidacja zdjęć dla pakietów z wideo
    if package_type in ("wideo", "premium") and len(photos) == 0:
        raise HTTPException(400, "Pakiet z wideo wymaga załączenia zdjęć")

    # Zapis zamówienia w Supabase
    order_row = {
        "buyer_name":      buyer_name,
        "buyer_email":     buyer_email,
        "recipient_name":  recipient_name,
        "occasion":        occasion,
        "package_type":    package_type,
        "price":           {"piosenka": 29, "wideo": 59, "premium": 99}[package_type],
        "person_desc":     person_desc,
        "content_desc":    content_desc,
        "music_style":     music_style,
        "recipient_email": recipient_email,
        # Dane drugiej piosenki — zapisane jako JSON w osobnych polach
        "recipient_name2": recipient_name2,
        "occasion2":       occasion2,
        "person_desc2":    person_desc2,
        "content_desc2":   content_desc2,
        "music_style2":    music_style2 or music_style,
        "recipient_email2": recipient_email2,
        "status":          "pending",
    }

    result   = supabase.table("orders").insert(order_row).execute()
    order_id = result.data[0]["id"]
    print(f"[Main] Zamówienie zapisane: {order_id} ({package_type})")

    # Wgrywamy zdjęcia do Supabase Storage bucket "photos"
    if photos and len(photos) > 0:
        print(f"[Main] Wgrywam {len(photos)} zdjęć...")
        for i, photo in enumerate(photos):
            if photo.filename:
                ext      = photo.filename.rsplit(".", 1)[-1].lower()
                filename = f"{order_id}/photo_{i:02d}.{ext}"
                content  = await photo.read()
                supabase.storage.from_("photos").upload(
                    path=filename,
                    file=content,
                    file_options={"content-type": photo.content_type or "image/jpeg"},
                )
        print(f"[Main] ✅ Zdjęcia wgrane do Supabase")

    # Tworzymy sesję Stripe Checkout
    session = stripe.checkout.Session.create(
        payment_method_types=["card", "blik"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        allow_promotion_codes=True,
        success_url=f"{BASE_URL}/sukces?order={order_id}",
        cancel_url=f"{BASE_URL}/#zamow",
        metadata={"order_id": str(order_id)},
        customer_email=buyer_email,
    )

    print(f"[Main] Stripe session: {session.id}")
    return {"checkout_url": session.url, "order_id": order_id}


# ── Webhook Stripe ────────────────────────────────────────────────────────────
@app.post("/api/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise HTTPException(400, str(e))

    if event["type"] == "checkout.session.completed":
        order_id = event["data"]["object"]["metadata"].get("order_id")
        if order_id:
            print(f"[Main] ✅ Płatność potwierdzona → {order_id}")
            background_tasks.add_task(run_pipeline, order_id)

    return {"status": "ok"}


# ── Pipeline agentów ──────────────────────────────────────────────────────────
async def run_pipeline(order_id: str):
    print(f"\n{'='*55}\n[Main] START pipeline: {order_id}\n{'='*55}")

    res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not res.data:
        print(f"[Main] ❌ Nie znaleziono zamówienia: {order_id}")
        return

    order        = res.data[0]
    package_type = order["package_type"]
    has_video    = package_type in ("wideo", "premium")
    is_premium   = package_type == "premium"

    print(f"[Main] Pakiet: {package_type} | Wideo: {has_video} | Premium: {is_premium}")
    _set_status(order_id, "processing")

    # ── Piosenka 1 ────────────────────────────────────────────
    print("\n[Main] 📝 Agent 1 — piosenka 1...")
    r1 = agent1_text.run(order)
    if not r1["success"]:
        _set_status(order_id, "error")
        print(f"[Main] ❌ Agent1: {r1['error']}")
        return

    print("\n[Main] 🎵 Agent 2 — muzyka 1...")
    r2 = agent2_music.run(r1["song_text"], order)
    if not r2["success"]:
        _set_status(order_id, "error")
        print(f"[Main] ❌ Agent2: {r2['error']}")
        return

    video_url = None
    if has_video:
        print("\n[Main] 🎬 Agent 4 — wideo 1...")
        r4 = agent4_video.run(order, r2["audio_url"])
        video_url = r4.get("video_url") if r4["success"] else None
        if not r4["success"]:
            print(f"[Main] ⚠️ Agent4 błąd (kontynuuję): {r4['error']}")

    # ── Piosenka 2 — tylko Premium ────────────────────────────
    audio_url2 = None
    video_url2 = None
    song_text2 = None
    poem2      = None

    if is_premium and order.get("recipient_name2"):
        print("\n[Main] 📝 Agent 1 — piosenka 2 (Premium)...")
        order2 = {
            **order,
            "recipient_name":  order["recipient_name2"],
            "occasion":        order["occasion2"],
            "person_desc":     order["person_desc2"],
            "content_desc":    order["content_desc2"],
            "music_style":     order.get("music_style2", order["music_style"]),
            # Osobny email odbiorcy dla drugiej piosenki
            "recipient_email": order.get("recipient_email2") or order["buyer_email"],
        }
        r1b = agent1_text.run(order2)
        if r1b["success"]:
            song_text2 = r1b["song_text"]
            poem2      = r1b["poem"]

            print("\n[Main] 🎵 Agent 2 — muzyka 2 (Premium)...")
            r2b = agent2_music.run(song_text2, order2)
            if r2b["success"]:
                audio_url2 = r2b["audio_url"]

                print("\n[Main] 🎬 Agent 4 — wideo 2 (Premium)...")
                r4b = agent4_video.run(order2, audio_url2)
                video_url2 = r4b.get("video_url") if r4b["success"] else None

    # ── Agent 3 — dwa osobne maile dla Premium ────────────────
    print("\n[Main] 📦 Agent 3 — email 1 (piosenka 1)...")
    r3 = agent3_pack.run(
        order,
        r1["song_text"],
        r1["poem"],
        r2["audio_url"],
        r2["ext"],
        video_url,
    )
    if not r3["success"]:
        _set_status(order_id, "error")
        print(f"[Main] ❌ Agent3 email 1: {r3['error']}")
        return

    # Drugi email dla Premium — piosenka 2 (z opóźnieniem 5s)
    if is_premium and audio_url2 and order.get("recipient_name2"):
        import asyncio
        await asyncio.sleep(5)  # krótkie opóźnienie żeby maile przyszły osobno
        print("\n[Main] 📦 Agent 3 — email 2 (piosenka 2 Premium)...")
        agent3_pack.run(
            order2,
            song_text2,
            poem2,
            audio_url2,
            r2b.get("ext", "mp3"),
            video_url2,
        )

    update_data = {
        "status":   "completed",
        "song_url": r2["audio_url"],
        "pdf_url":  r3["pdf_url"],
    }
    if video_url:  update_data["video_url"]  = video_url
    if audio_url2: update_data["song_url2"]  = audio_url2

    supabase.table("orders").update(update_data).eq("id", order_id).execute()
    print(f"\n[Main] 🎉 SUKCES — zamówienie {order_id} zakończone!\n{'='*55}\n")


def _set_status(order_id: str, status: str):
    supabase.table("orders").update({"status": status}).eq("id", order_id).execute()
    print(f"[Main] Status → {status}")


# ── Status zamówienia ─────────────────────────────────────────────────────────
@app.post("/api/retry/{order_id}")
async def retry_order(order_id: str, request: Request, background_tasks: BackgroundTasks):
    """
    Ponawia pipeline dla zamówienia które zakończyło się błędem.
    Zabezpieczony tym samym tokenem co cleanup.
    """
    auth = request.headers.get("Authorization", "")
    cleanup_token = os.environ.get("CLEANUP_TOKEN", "")
    if cleanup_token and auth != f"Bearer {cleanup_token}":
        raise HTTPException(401, "Unauthorized")

    res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not res.data:
        raise HTTPException(404, "Zamówienie nie znalezione")

    order = res.data[0]
    print(f"[Main] 🔄 Retry zamówienia: {order_id} (status: {order['status']})")

    # Resetujemy status i uruchamiamy pipeline ponownie
    supabase.table("orders").update({"status": "pending"}).eq("id", order_id).execute()
    background_tasks.add_task(run_pipeline, order_id)

    return {"status": "ok", "message": f"Pipeline ponownie uruchomiony dla {order_id}"}


async def get_order(order_id: str):
    res = supabase.table("orders").select(
        "id,status,recipient_name,occasion,package_type,created_at"
    ).eq("id", order_id).execute()
    if not res.data:
        raise HTTPException(404, "Nie znaleziono zamówienia")
    return res.data[0]


@app.get("/")
async def health():
    return {"status": "ok", "service": "NutaNaZyczenie API v2"}


# ── Cleanup — uruchamiany co godzinę przez Railway Cron ───────────────────────
@app.post("/api/cleanup")
async def run_cleanup(request: Request):
    """
    Endpoint czyszczący — usuwa dane zamówień starszych niż 24h.
    Zabezpieczony tokenem — wywołuj tylko z Railway Cron lub ręcznie.
    """
    # Prosta weryfikacja tokena
    auth = request.headers.get("Authorization", "")
    cleanup_token = os.environ.get("CLEANUP_TOKEN", "")
    if cleanup_token and auth != f"Bearer {cleanup_token}":
        raise HTTPException(401, "Unauthorized")

    result = agent_cleanup.run_cleanup()
    return result


# ── Sprawdzanie okna poprawek ────────────────────────────────────────────────
@app.post("/api/correction/{order_id}")
async def request_correction(order_id: str, request: Request):
    """
    Klient wysyła prośbę o poprawkę — sprawdzamy czy mieści się w 24h oknie.
    Jeśli tak: przyjmujemy i oznaczamy w bazie.
    Jeśli nie: wysyłamy automatyczny email o wygaśnięciu i zwracamy błąd.
    """
    res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not res.data:
        raise HTTPException(404, "Zamówienie nie znalezione")

    order = res.data[0]

    # Sprawdzamy okno 24h
    if not agent_cleanup.check_correction_window(order):
        # Wysyłamy email o wygaśnięciu
        agent_cleanup.send_correction_expired_email(order)
        raise HTTPException(410, "Czas na bezpłatną poprawkę (24h) minął")

    # Okno aktywne — zapisujemy prośbę o poprawkę
    data = await request.json()
    correction_note = data.get("note", "")

    supabase.table("orders").update({
        "status": "correction_requested",
        "correction_note": correction_note,
    }).eq("id", order_id).execute()

    print(f"[Main] Poprawka przyjęta dla zamówienia {order_id}")
    return {"status": "ok", "message": "Poprawka przyjęta — realizacja w ciągu 55 minut"}


@app.get("/api/force-run/{order_id}")
async def force_run(order_id: str, background_tasks: BackgroundTasks):
    """Proste wejście do testowania pipeline w przeglądarce — bez tokena."""
    print(f"[Force Run] Wymuszam start dla: {order_id}")
    # Resetujemy status żeby pipeline mógł wystartować
    supabase.table("orders").update({"status": "pending"}).eq("id", order_id).execute()
    background_tasks.add_task(run_pipeline, order_id)
    return {"status": "Wymuszono start maszyny! Sprawdz okno logow w Railway."}


@app.get("/api/force-run/{order_id}")
async def force_run(order_id: str, background_tasks: BackgroundTasks):
    """Proste wejście do testowania pipeline w przeglądarce — bez tokena"""
    print(f"[Force Run] Wymuszam start dla: {order_id}")
    background_tasks.add_task(run_pipeline, order_id)
    return {"status": "Wymuszono start maszyny! Sprawdz okno logow w Railway."}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
