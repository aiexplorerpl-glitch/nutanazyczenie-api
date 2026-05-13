"""
MAIN.PY — ORKIESTRATOR v2 (Finalna wersja pod domenę .pl)
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
# Ustawiamy domyślnie na .pl zgodnie z Twoją prośbą
BASE_URL                = os.environ.get("BASE_URL", "https://www.nutanazyczenie.pl")

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

import agent1_text
import agent2_music
import agent3_pack
import agent4_video

app = FastAPI(title="NutaNaZyczenie API v2")

# Pozwalamy na ruch z obu domen (.pl i .com)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nutanazyczenie.pl",
        "https://www.nutanazyczenie.pl",
        "https://nutanazyczenie.com",
        "https://www.nutanazyczenie.com",
        "http://localhost"
    ],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# ... (reszta kodu create_order i webhook pozostaje bez zmian jak w wersji v2) ...

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
    photos:          List[UploadFile] = File(default=[]),
):
    price_map = {
        "piosenka": os.environ.get("STRIPE_PRICE_PIOSENKA"),
        "wideo":    os.environ.get("STRIPE_PRICE_WIDEO"),
        "premium":  os.environ.get("STRIPE_PRICE_PREMIUM"),
    }
    price_id = price_map.get(package_type)
    if not price_id: raise HTTPException(400, "Nieprawidłowy pakiet")

    if package_type in ("wideo", "premium") and len(photos) == 0:
        raise HTTPException(400, "Pakiet z wideo wymaga załączenia zdjęć")

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
        "status":          "pending",
    }
    result   = supabase.table("orders").insert(order_row).execute()
    order_id = result.data[0]["id"]

    if photos:
        for i, photo in enumerate(photos):
            if photo.filename:
                ext = photo.filename.rsplit(".", 1)[-1].lower()
                supabase.storage.from_("photos").upload(
                    path=f"{order_id}/photo_{i:02d}.{ext}",
                    file=await photo.read(),
                    file_options={"content-type": photo.content_type or "image/jpeg"}
                )

    session = stripe.checkout.Session.create(
        payment_method_types=["card", "blik", "p24"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="payment",
        success_url=f"{BASE_URL}/sukces?order={order_id}",
        cancel_url=f"{BASE_URL}/#zamow",
        metadata={"order_id": str(order_id)},
        customer_email=buyer_email,
    )
    return {"checkout_url": session.url, "order_id": order_id}

@app.post("/api/webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except: raise HTTPException(400)
    if event["type"] == "checkout.session.completed":
        oid = event["data"]["object"]["metadata"].get("order_id")
        if oid: background_tasks.add_task(run_pipeline, oid)
    return {"status": "ok"}

async def run_pipeline(order_id: str):
    res = supabase.table("orders").select("*").eq("id", order_id).execute()
    if not res.data: return
    order = res.data[0]
    r1 = agent1_text.run(order)
    r2 = agent2_music.run(r1["song_text"], order)
    v_url = None
    if order["package_type"] in ("wideo", "premium"):
        r4 = agent4_video.run(order, r2["audio_url"])
        if r4["success"]: v_url = r4["video_url"]
    r3 = agent3_pack.run(order, r1["song_text"], r1["poem"], r2["audio_url"], r2["ext"], v_url)
    upd = {"status": "completed", "song_url": r2["audio_url"], "pdf_url": r3["pdf_url"]}
    if v_url: upd["video_url"] = v_url
    supabase.table("orders").update(upd).eq("id", order_id).execute()

@app.get("/api/order/{order_id}")
async def get_order(order_id: str):
    res = supabase.table("orders").select("id,status,recipient_name").eq("id", order_id).execute()
    return res.data[0] if res.data else None

@app.get("/")
async def health(): return {"status": "ok"}
