"""
MAIN.PY — ORKIESTRATOR
======================
Serwer FastAPI uruchamiany na Railway.app (NIE na Vercel).
Railway utrzymuje serwer przez cały czas — BackgroundTasks działają poprawnie.
Vercel jest serverless i zabija procesy po zwróceniu odpowiedzi — nie używaj go dla backendu.
"""

import os
import stripe
import uvicorn
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
BASE_URL = os.environ.get("BASE_URL", "https://nutanazyczenie.pl")

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

import agent1_text
import agent2_music
import agent3_pack

app = FastAPI(title="NutaNaZyczenie API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[BASE_URL, f"www.{BASE_URL}", "http://localhost"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


# ── Przyjmowanie zamówień ─────────────────────────────────────────────────────
@app.post("/api/order")
async def create_order(request: Request):
    data = await request.json()

    required = ["buyer_name","buyer_email","recipient_name",
                "occasion","package_type","person_desc","content_desc"]
    for f in required:
        if not data.get(f):
            raise HTTPException(400, f"Brak pola: {f}")

    price_map = {
        "piosenka": os.environ.get("STRIPE_PRICE_PIOSENKA"),
        "wideo":    os.environ.get("STRIPE_PRICE_WIDEO"),
        "premium":  os.environ.get("STRIPE_PRICE_PREMIUM"),
    }
    price_id = price_map.get(data["package_type"])
    if not price_id:
        raise HTTPException(400, "Nieprawidłowy pakiet")

    # Zapis zamówienia w Supabase
    row = {
        "buyer_name":      data["buyer_name"],
        "buyer_email":     data["buyer_email"],
        "recipient_name":  data["recipient_name"],
        "occasion":        data["occasion"],
        "package_type":    data["package_type"],
        "price":           {"piosenka":29,"wideo":59,"premium":99}[data["package_type"]],
        "person_desc":     data["person_desc"],
        "content_desc":    data["content_desc"],
        "music_style":     data.get("music_style","pop"),
        "recipient_email": data.get("recipient_email"),
        "status":          "pending",
    }
    result = supabase.table("orders").insert(row).execute()
    order_id = result.data[0]["id"]

    # Stripe Checkout Session
    session = stripe.checkout.Session.create(
        payment_method_types=["card","blik","p24"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=f"{BASE_URL}/sukces?order={order_id}",
        cancel_url=f"{BASE_URL}/#zamow",
        metadata={"order_id": str(order_id)},
        customer_email=data["buyer_email"],
    )

    print(f"[Main] Zamówienie {order_id} | Stripe: {session.id}")
    return {"checkout_url": session.url, "order_id": order_id}


# ── Webhook Stripe ────────────────────────────────────────────────────────────
@app.post("/api/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        raise HTTPException(400, str(e))

    if event["type"] == "checkout.session.completed":
        order_id = event["data"]["object"]["metadata"].get("order_id")
        if order_id:
            print(f"[Main] Płatność OK → {order_id}")
            background_tasks.add_task(run_pipeline, order_id)

    return {"status": "ok"}


# ── Pipeline agentów ──────────────────────────────────────────────────────────
async def run_pipeline(order_id: str):
    print(f"\n{'='*50}\n[Main] START pipeline: {order_id}\n{'='*50}")

    # Pobieramy zamówienie
    res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not res.data:
        print(f"[Main] Nie znaleziono zamówienia: {order_id}")
        return

    order = res.data[0]
    _set_status(order_id, "processing")

    # Agent 1 — tekst
    print("[Main] Agent 1 (tekst)...")
    r1 = agent1_text.run(order)
    if not r1["success"]:
        _set_status(order_id, "error")
        print(f"[Main] Agent1 błąd: {r1['error']}")
        return

    # Agent 2 — muzyka
    print("[Main] Agent 2 (muzyka)...")
    r2 = agent2_music.run(r1["song_text"], order)
    if not r2["success"]:
        _set_status(order_id, "error")
        print(f"[Main] Agent2 błąd: {r2['error']}")
        return

    # Agent 3 — PDF + email
    print("[Main] Agent 3 (pakowanie + email)...")
    r3 = agent3_pack.run(
        order,
        r1["song_text"],
        r1["poem"],
        r2["audio_url"],
        r2["ext"],
    )
    if not r3["success"]:
        _set_status(order_id, "error")
        print(f"[Main] Agent3 błąd: {r3['error']}")
        return

    # Zapisujemy URL-e w Supabase
    supabase.table("orders").update({
        "status":   "completed",
        "song_url": r2["audio_url"],
        "pdf_url":  r3["pdf_url"],
    }).eq("id", order_id).execute()

    print(f"\n[Main] SUKCES — zamówienie {order_id} zakończone!\n{'='*50}\n")


def _set_status(order_id: str, status: str):
    supabase.table("orders").update({"status": status}).eq("id", order_id).execute()
    print(f"[Main] Status → {status}")


# ── Status zamówienia ─────────────────────────────────────────────────────────
@app.get("/api/order/{order_id}")
async def get_order(order_id: str):
    res = supabase.table("orders").select(
        "id,status,recipient_name,occasion,package_type,created_at"
    ).eq("id", order_id).execute()
    if not res.data:
        raise HTTPException(404, "Nie znaleziono")
    return res.data[0]


@app.get("/")
async def health():
    return {"status": "ok", "service": "NutaNaZyczenie API"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
