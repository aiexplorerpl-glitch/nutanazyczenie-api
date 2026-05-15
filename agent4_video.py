"""
AGENT 4 — REŻYSER WIDEO (Shotstack API)
=========================================
Odpowiada za:
1. Pobranie zdjęć z Supabase Storage (wgranych przez klienta)
2. Złożenie animowanego wideo slideshow przez Shotstack API
3. Dodanie podkładu muzycznego (MP3 z Agenta 2)
4. Dodanie animowanego tekstu (tytuł, imię, okazja)
5. Wgranie gotowego wideo do Supabase Storage
6. Zwrócenie publicznego URL wideo

WYMAGANIA:
- Konto Shotstack: shotstack.io
- Klucz API: SHOTSTACK_API_KEY w zmiennych środowiskowych
- Zdjęcia klienta wgrane do Supabase Storage bucket "photos"
"""

import os
import time
import requests
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

SHOTSTACK_API_KEY = os.environ.get("SHOTSTACK_API_KEY")
SHOTSTACK_URL     = "https://api.shotstack.io/v1"

# Czas wyświetlania każdego zdjęcia w sekundach
PHOTO_DURATION = 3.0
# Czas przejścia między zdjęciami
TRANSITION_DURATION = 0.8


def get_photo_urls(order_id: str) -> list:
    """
    Pobiera listę publicznych URL zdjęć klienta z Supabase Storage.
    Zdjęcia są przechowywane w bucket 'photos' pod ścieżką order_id/
    """
    try:
        files = supabase.storage.from_("photos").list(order_id)
        urls  = []
        for f in files:
            if f["name"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                url = supabase.storage.from_("photos").get_public_url(
                    f"{order_id}/{f['name']}"
                )
                urls.append(url)
        print(f"[Agent4] Znaleziono {len(urls)} zdjęć dla zamówienia {order_id}")
        return urls
    except Exception as e:
        raise Exception(f"Błąd pobierania zdjęć z Supabase: {e}")


def build_shotstack_timeline(
    photo_urls: list,
    audio_url:  str,
    recipient_name: str,
    occasion:   str,
) -> dict:
    """
    Buduje obiekt timeline dla Shotstack API.
    Tworzy animowany slideshow ze zdjęć z podkładem muzycznym i tekstem.
    """
    clips = []

    # ── Zdjęcia w tle ────────────────────────────────────────
    for i, url in enumerate(photo_urls):
        start = i * (PHOTO_DURATION - TRANSITION_DURATION)
        clips.append({
            "asset": {
                "type":    "image",
                "src":     url,
                "crop":    {"top": 0, "bottom": 0, "left": 0, "right": 0},
            },
            "start":    round(start, 2),
            "length":   PHOTO_DURATION,
            "fit":      "cover",
            "scale":    1.05,
            "effect":   "zoomIn" if i % 2 == 0 else "zoomOut",
            "transition": {
                "in":  "fade",
                "out": "fade",
            },
        })

    total_duration = len(photo_urls) * (PHOTO_DURATION - TRANSITION_DURATION) + TRANSITION_DURATION

    # ── Tekst — imię i okazja na początku ────────────────────
    clips.append({
        "asset": {
            "type":     "title",
            "text":     recipient_name,
            "style":    "minimal",
            "color":    "#FFFFFF",
            "size":     "x-large",
            "position": "center",
            "offset":   {"x": 0, "y": 0.1},
            "background": "rgba(0,0,0,0.3)",
        },
        "start":  0.5,
        "length": 3.0,
        "transition": {"in": "fade", "out": "fade"},
    })

    clips.append({
        "asset": {
            "type":     "title",
            "text":     occasion,
            "style":    "minimal",
            "color":    "#E8B95A",
            "size":     "medium",
            "position": "center",
            "offset":   {"x": 0, "y": -0.1},
        },
        "start":  0.5,
        "length": 3.0,
        "transition": {"in": "fade", "out": "fade"},
    })

    # Tekst końcowy
    clips.append({
        "asset": {
            "type":     "title",
            "text":     "NutaNaŻyczenie",
            "style":    "minimal",
            "color":    "#E8B95A",
            "size":     "medium",
            "position": "bottom",
        },
        "start":  max(0, total_duration - 3.0),
        "length": 2.5,
        "transition": {"in": "fade", "out": "fade"},
    })

    # ── Podkład muzyczny ─────────────────────────────────────
    soundtrack = {
        "src":    audio_url,
        "effect": "fadeOut",
        "volume": 1.0,
    }

    return {
        "timeline": {
            "soundtrack": soundtrack,
            "background": "#000000",
            "tracks":     [{"clips": clips}],
        },
        "output": {
            "format":     "mp4",
            "resolution": "hd",    # 1280x720
            "fps":        25,
            "quality":    "high",
        },
    }


def render_video(timeline: dict) -> str:
    """
    Wysyła timeline do Shotstack i czeka na wyrenderowanie wideo.
    Zwraca URL gotowego pliku MP4.
    """
    headers = {
        "x-api-key":    SHOTSTACK_API_KEY,
        "Content-Type": "application/json",
    }

    print(f"[Agent4] Wysyłam do Shotstack...")
    resp = requests.post(
        f"{SHOTSTACK_URL}/render",
        json=timeline,
        headers=headers,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise Exception(f"Shotstack error {resp.status_code}: {resp.text}")

    render_id = resp.json()["response"]["id"]
    print(f"[Agent4] Render ID: {render_id} — polling co 10s...")

    # Polling max 10 minut
    for attempt in range(60):
        time.sleep(10)
        waited = (attempt + 1) * 10

        poll = requests.get(
            f"{SHOTSTACK_URL}/render/{render_id}",
            headers=headers,
            timeout=30,
        )

        if poll.status_code != 200:
            print(f"[Agent4] Polling error: {poll.status_code}")
            continue

        response = poll.json()["response"]
        status   = response.get("status", "")
        print(f"[Agent4] Status: {status} ({waited}s)")

        if status == "done":
            video_url = response.get("url")
            print(f"[Agent4] ✅ Wideo gotowe: {video_url}")
            return video_url

        elif status in ("failed", "error"):
            raise Exception(f"Shotstack render failed: {response.get('error', 'unknown')}")

    raise Exception("Timeout — Shotstack nie wyrenderował wideo w 600s")


def upload_video_to_supabase(video_url: str, order_id: str) -> str:
    """
    Pobiera wideo z Shotstack i wgrywa do Supabase Storage bucket 'orders'.
    Zwraca publiczny URL.
    """
    print(f"[Agent4] Pobieram wideo...")
    resp = requests.get(video_url, timeout=120)
    if resp.status_code != 200:
        raise Exception(f"Nie mogę pobrać wideo: {resp.status_code}")

    filename = f"{order_id}/video.mp4"
    supabase.storage.from_("orders").upload(
        path=filename,
        file=resp.content,
        file_options={"content-type": "video/mp4"},
    )

    public_url = supabase.storage.from_("orders").get_public_url(filename)
    size_mb    = len(resp.content) // (1024 * 1024)
    print(f"[Agent4] ✅ Wideo wgrane ({size_mb} MB): {public_url}")
    return public_url


def run(order: dict, audio_url: str) -> dict:
    """
    Główna funkcja Agenta 4 — uruchamiana przez main.py.

    Args:
        order:     dane zamówienia z Supabase
        audio_url: publiczny URL MP3 z Agenta 2 (z Supabase Storage)

    Returns:
        dict: {success, video_url, error}
    """
    try:
        order_id = str(order["id"])

        # Pobieramy URL-e zdjęć z Supabase
        photo_urls = get_photo_urls(order_id)
        if len(photo_urls) < 1:
            raise Exception("Brak zdjęć w Supabase Storage dla tego zamówienia")

        # Ograniczamy do max 15 zdjęć
        photo_urls = photo_urls[:15]

        # Budujemy timeline Shotstack
        timeline = build_shotstack_timeline(
            photo_urls,
            audio_url,
            order["recipient_name"],
            order["occasion"],
        )

        # Renderujemy wideo
        shotstack_url = render_video(timeline)

        # Wgrywamy do Supabase
        public_url = upload_video_to_supabase(shotstack_url, order_id)

        return {"success": True, "video_url": public_url}

    except Exception as e:
        print(f"[Agent4] ❌ Błąd: {e}")
        return {"success": False, "video_url": None, "error": str(e)}
