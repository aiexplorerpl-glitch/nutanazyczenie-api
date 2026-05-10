"""
MAIN.PY — ORKIESTRATOR
======================
Główny plik który:
1. Odbiera webhook od Stripe (potwierdzenie płatności)
2. Pobiera dane zamówienia z Supabase
3. Uruchamia Agentów 1, 2, 3 po kolei
4. Aktualizuje status zamówienia w Supabase
5. Obsługuje błędy i retry

Uruchamiany jako serwer FastAPI na Railway.app
"""

import os
import json
import stripe
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv

# Ładujemy zmienne środowiskowe z pliku .env (lokalnie)
# Na Railway zmienne są ustawione w panelu
load_dotenv()

# Inicjalizacja klientów
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

# Importujemy agentów
import agent1_text
import agent2_music
import agent3_pack

app = FastAPI(title="NutaNaŻyczenie API")

# CORS — pozwalamy na requesty ze strony
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://nutanazyczenie.pl", "https://www.nutanazyczenie.pl"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT: Przyjmowanie zamówień ze strony
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/order")
async def create_order(request: Request, background_tasks: BackgroundTasks):
    """
    Przyjmuje dane formularza ze strony.
    Tworzy sesję płatności Stripe i zwraca URL do płatności.
    """
    data = await request.json()

    # Walidacja wymaganych pól
    required = ["buyer_name", "buyer_email", "recipient_name",
                "occasion", "package_type", "person_desc", "content_desc"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"Brak wymaganego pola: {field}")

    # Mapowanie pakietu na cenę Stripe
    price_map = {
        "piosenka": os.environ.get("STRIPE_PRICE_PIOSENKA"),
        "wideo":    os.environ.get("STRIPE_PRICE_WIDEO"),
        "premium":  os.environ.get("STRIPE_PRICE_PREMIUM"),
    }
    price_id = price_map.get(data["package_type"])
    if not price_id:
        raise HTTPException(status_code=400, detail="Nieprawidłowy typ pakietu")

    # Zapisujemy zamówienie w Supabase ze statusem 'pending'
    order_data = {
        "buyer_name":     data["buyer_name"],
        "buyer_email":    data["buyer_email"],
        "recipient_name": data["recipient_name"],
        "occasion":       data["occasion"],
        "package_type":   data["package_type"],
        "price":          {"piosenka": 29, "wideo": 59, "premium": 99}[data["package_type"]],
        "person_desc":    data["person_desc"],
        "content_desc":   data["content_desc"],
        "music_style":    data.get("music_style", "pop"),
        "recipient_email": data.get("recipient_email"),
        "status":         "pending",
    }

    result = supabase.table("orders").insert(order_data).execute()
    order_id = result.data[0]["id"]
    print(f"[Main] Zamówienie zapisane: {order_id}")

    # Tworzymy sesję płatności Stripe Checkout
    session = stripe.checkout.Session.create(
        payment_method_types=["card", "blik", "p24"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=f"https://nutanazyczenie.pl/sukces?order={order_id}",
        cancel_url="https://nutanazyczenie.pl/#zamow",
        metadata={"order_id": str(order_id)},  # przekazujemy ID zamówienia
        customer_email=data["buyer_email"],
    )

    print(f"[Main] Stripe session: {session.id}")

    return {
        "checkout_url": session.url,
        "order_id": order_id,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT: Webhook od Stripe (potwierdzenie płatności)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Odbiera powiadomienie od Stripe gdy płatność zostanie zrealizowana.
    Uruchamia pipeline agentów w tle.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Weryfikujemy podpis Stripe (bezpieczeństwo)
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Obsługujemy tylko zdarzenie "płatność zakończona"
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session["metadata"].get("order_id")

        if order_id:
            print(f"[Main] ✅ Płatność potwierdzona! Order ID: {order_id}")
            # Uruchamiamy pipeline agentów w tle
            # (nie blokujemy odpowiedzi dla Stripe)
            background_tasks.add_task(run_agents_pipeline, order_id)

    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE AGENTÓW
# ─────────────────────────────────────────────────────────────────────────────
async def run_agents_pipeline(order_id: str):
    """
    Uruchamia wszystkich 3 agentów po kolei.
    Aktualizuje status zamówienia w Supabase na każdym etapie.
    """
    print(f"\n{'='*50}")
    print(f"[Main] 🚀 Start pipeline dla zamówienia: {order_id}")
    print(f"{'='*50}")

    # ── Pobieramy dane zamówienia z Supabase ──────────────────
    result = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not result.data:
        print(f"[Main] ❌ Nie znaleziono zamówienia: {order_id}")
        return

    order = result.data[0]
    print(f"[Main] Zamówienie: {order['package_type']} dla {order['recipient_name']}")

    # Aktualizujemy status
    update_status(order_id, "processing")

    # ── AGENT 1: Generowanie tekstu ───────────────────────────
    print(f"\n[Main] 📝 Uruchamiam Agenta 1 (tekst)...")
    result1 = agent1_text.run(order)

    if not result1["success"]:
        print(f"[Main] ❌ Agent 1 failed: {result1['error']}")
        update_status(order_id, "error", f"Agent1: {result1['error']}")
        return

    song_text = result1["song_text"]
    poem = result1["poem"]
    print(f"[Main] ✅ Agent 1 zakończony")

    # ── AGENT 2: Generowanie muzyki ───────────────────────────
    print(f"\n[Main] 🎵 Uruchamiam Agenta 2 (muzyka)...")
    result2 = agent2_music.run(song_text, order)

    if not result2["success"]:
        print(f"[Main] ❌ Agent 2 failed: {result2['error']}")
        update_status(order_id, "error", f"Agent2: {result2['error']}")
        return

    mp3_path = result2["mp3_path"]
    print(f"[Main] ✅ Agent 2 zakończony")

    # ── AGENT 3: PDF + Email ──────────────────────────────────
    print(f"\n[Main] 📦 Uruchamiam Agenta 3 (pakowanie + email)...")
    result3 = agent3_pack.run(order, song_text, poem, mp3_path)

    if not result3["success"]:
        print(f"[Main] ❌ Agent 3 failed: {result3['error']}")
        update_status(order_id, "error", f"Agent3: {result3['error']}")
        return

    # ── Sukces! ───────────────────────────────────────────────
    update_status(order_id, "completed")
    print(f"\n{'='*50}")
    print(f"[Main] 🎉 Pipeline zakończony sukcesem!")
    print(f"[Main] Zamówienie {order_id} — COMPLETED")
    print(f"{'='*50}\n")


def update_status(order_id: str, status: str, error_msg: str = None):
    """Aktualizuje status zamówienia w Supabase."""
    data = {"status": status}
    supabase.table("orders").update(data).eq("id", order_id).execute()
    print(f"[Main] Status → {status}")


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT: Sprawdzanie statusu zamówienia (dla strony sukcesu)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/order/{order_id}")
async def get_order_status(order_id: str):
    """Zwraca status zamówienia — używany przez stronę sukcesu."""
    result = supabase.table("orders").select(
        "id, status, recipient_name, occasion, package_type, created_at"
    ).eq("id", order_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Zamówienie nie znalezione")

    return result.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "ok", "service": "NutaNaŻyczenie API"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
