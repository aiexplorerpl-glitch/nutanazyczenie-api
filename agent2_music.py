"""
AGENT 2 — MUZYK
===============
Odpowiada za:
1. Odebranie tekstu piosenki od Agenta 1
2. Wysłanie do Suno API z odpowiednim promptem stylu
3. Polling — sprawdzanie co 10s czy muzyka gotowa
4. Wgranie MP3 do Supabase Storage (bezpieczne współdzielenie plików)
5. Zwrócenie publicznego URL do pliku

UWAGA O SUNO API:
Oficjalne Suno nie udostępnia publicznego API.
Korzystamy z suno-api (self-hosted wrapper lub usługa zewnętrzna).
Popularne opcje:
  - https://github.com/gcui-art/suno-api (self-hosted na Railway)
  - https://www.sunoapi.pro (zewnętrzna usługa)
Ustaw SUNO_API_URL w .env na adres swojego wrappera.
"""

import os
import time
import requests
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

# URL do Twojego wrappera Suno — ustaw w .env
SUNO_API_URL = os.environ.get("SUNO_API_URL", "http://localhost:3000")
SUNO_API_KEY = os.environ.get("SUNO_API_KEY", "")

# Mapowanie stylów muzycznych na tagi Suno
STYLE_MAP = {
    "pop":       "polish pop, upbeat, catchy, modern",
    "ballada":   "polish ballad, emotional, piano, slow tempo",
    "hip-hop":   "polish hip hop, rap, boom bap, 95 bpm",
    "folk":      "polish folk, accordion, biesiadna, festive, 130 bpm",
    "rock":      "polish rock, guitar, energetic, powerful",
    "jazz":      "polish jazz, saxophone, smooth, relaxed",
    "klasyczna": "classical, orchestral, elegant, emotional",
}

OCCASION_MOOD = {
    "urodziny":  "celebratory, birthday, joyful, happy",
    "imieniny":  "celebratory, joyful, warm",
    "ślub":      "romantic, wedding, emotional, love",
    "rocznica":  "romantic, emotional, nostalgic",
    "walentynki":"romantic, love song, tender",
    "absolutorium": "triumphant, proud, celebratory",
}


def get_style_prompt(music_style: str, occasion: str, package_type: str) -> str:
    """Buduje prompt stylu dla Suno."""
    style_key = music_style.lower().split("/")[0].strip()
    base = STYLE_MAP.get(style_key, "polish pop, upbeat, modern")

    # Nastrój na podstawie okazji
    mood = "warm, celebratory, personal"
    for key, val in OCCASION_MOOD.items():
        if key in occasion.lower():
            mood = val
            break

    # Długość zależna od pakietu
    duration = "2.5 to 3 minute song, verse pre-chorus chorus bridge outro" \
               if package_type == "premium" else \
               "2 minute song, verse chorus verse chorus outro"

    return f"{base}, {mood}, {duration}, Polish vocals, high quality"


def generate_and_poll(song_text: str, style: str, title: str) -> dict:
    """
    Wysyła tekst do Suno API i odpytuje co 10s aż muzyka będzie gotowa.
    Zwraca {audio_url, file_extension}.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUNO_API_KEY}",
    }

    payload = {
        "prompt": song_text,
        "tags": style,
        "title": title,
        "make_instrumental": False,
        "wait_audio": False,
    }

    print(f"[Agent2] Wysyłam do Suno ({SUNO_API_URL})...")
    resp = requests.post(
        f"{SUNO_API_URL}/api/custom_generate",
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code != 200:
        raise Exception(f"Suno generate error {resp.status_code}: {resp.text}")

    data = resp.json()
    song_id = data[0]["id"] if isinstance(data, list) else data["id"]
    print(f"[Agent2] ID: {song_id} — polling...")

    # Polling max 5 minut
    for attempt in range(30):
        time.sleep(10)
        poll = requests.get(
            f"{SUNO_API_URL}/api/get?ids={song_id}",
            headers=headers,
            timeout=30,
        )
        if poll.status_code != 200:
            continue

        items = poll.json()
        item = items[0] if isinstance(items, list) else items
        status = item.get("status", "")
        print(f"[Agent2] Status: {status} ({(attempt+1)*10}s)")

        if status == "complete":
            audio_url = item.get("audio_url", "")
            if not audio_url:
                raise Exception("Brak audio_url w odpowiedzi Suno")
            # Sprawdzamy rozszerzenie pliku
            ext = "mp3"
            if ".wav" in audio_url.lower():
                ext = "wav"
            print(f"[Agent2] ✅ Audio gotowe: {audio_url}")
            return {"audio_url": audio_url, "ext": ext}

        elif status in ("error", "failed"):
            raise Exception(f"Suno failed: {item.get('error', 'unknown')}")

    raise Exception("Timeout — Suno nie wygenerował w 300s")


def upload_to_supabase(audio_url: str, order_id: str, ext: str) -> str:
    """
    Pobiera plik audio i wgrywa go do Supabase Storage.
    Dzięki temu Agent 3 może go pobrać nawet jeśli działa na innym serwerze.
    Zwraca publiczny URL pliku.
    """
    print(f"[Agent2] Pobieram audio...")
    resp = requests.get(audio_url, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"Nie mogę pobrać audio: {resp.status_code}")

    filename = f"{order_id}/song.{ext}"
    content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"

    print(f"[Agent2] Wgrywam do Supabase Storage ({filename})...")
    supabase.storage.from_("orders").upload(
        path=filename,
        file=resp.content,
        file_options={"content-type": content_type},
    )

    # Pobieramy publiczny URL
    public_url = supabase.storage.from_("orders").get_public_url(filename)
    print(f"[Agent2] ✅ Wgrano: {public_url}")
    return public_url


def run(song_text: str, order: dict) -> dict:
    """
    Główna funkcja Agenta 2.

    Args:
        song_text: tekst piosenki od Agenta 1
        order: dane zamówienia

    Returns:
        dict: {success, audio_url, ext, error}
    """
    try:
        style = get_style_prompt(
            order.get("music_style", "pop"),
            order.get("occasion", "urodziny"),
            order["package_type"],
        )

        # Generujemy muzykę
        result = generate_and_poll(
            song_text,
            style,
            f"Piosenka dla {order['recipient_name']}",
        )

        # Wgrywamy do Supabase Storage
        public_url = upload_to_supabase(
            result["audio_url"],
            str(order["id"]),
            result["ext"],
        )

        return {
            "success":   True,
            "audio_url": public_url,
            "ext":       result["ext"],
        }

    except Exception as e:
        print(f"[Agent2] ❌ Błąd: {e}")
        return {"success": False, "audio_url": None, "ext": "mp3", "error": str(e)}
