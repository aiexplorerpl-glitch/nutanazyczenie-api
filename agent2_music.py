"""
AGENT 2 — MUZYK (GoAPI / Suno)
================================
Odpowiada za:
1. Odebranie tekstu piosenki od Agenta 1
2. Wysłanie do GoAPI (Suno) z odpowiednim promptem stylu
3. Polling co 15s aż muzyka będzie gotowa
4. Wgranie MP3 do Supabase Storage
5. Zwrócenie publicznego URL do pliku
"""

import os
import time
import requests
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

SUNO_API_KEY   = os.environ.get("SUNO_API_KEY")
GOAPI_BASE_URL = "https://api.goapi.ai/api/suno/v1/music"

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
    "urodziny":     "celebratory, birthday, joyful, happy",
    "imieniny":     "celebratory, joyful, warm",
    "ślub":         "romantic, wedding, emotional, love",
    "rocznica":     "romantic, emotional, nostalgic",
    "walentynki":   "romantic, love song, tender",
    "absolutorium": "triumphant, proud, celebratory",
}


def get_style_prompt(music_style: str, occasion: str, package_type: str) -> str:
    """Buduje prompt stylu dla Suno przez GoAPI."""
    style_key = music_style.lower().split("/")[0].strip()
    base = STYLE_MAP.get(style_key, "polish pop, upbeat, modern")

    mood = "warm, celebratory, personal"
    for key, val in OCCASION_MOOD.items():
        if key in occasion.lower():
            mood = val
            break

    # Długość zależna od pakietu
    if package_type == "premium":
        duration = "2.5 to 3 minute song, extended with bridge and final chorus"
    else:
        duration = "2 minute song, verse chorus verse chorus outro"

    return f"{base}, {mood}, {duration}, Polish vocals, high quality"


def generate_and_poll(song_text: str, style: str, title: str) -> dict:
    """
    Wysyła żądanie do GoAPI i odpytuje co 15s aż muzyka będzie gotowa.
    GoAPI zwraca task_id → polling → clips z audio_url.
    """
    headers = {
        "X-API-Key": SUNO_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "custom_mode":       True,
        "prompt":            song_text,
        "tags":              style,
        "title":             title,
        "make_instrumental": False,
    }

    print(f"[Agent2] Wysyłam do GoAPI...")
    print(f"[Agent2] Styl: {style[:80]}...")

    resp = requests.post(
        GOAPI_BASE_URL,
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code != 200:
        raise Exception(f"GoAPI error {resp.status_code}: {resp.text}")

    data    = resp.json()
    task_id = data.get("data", {}).get("task_id")
    if not task_id:
        raise Exception(f"GoAPI nie zwróciło task_id: {data}")

    print(f"[Agent2] Task ID: {task_id} — polling co 15s (max 6 min)...")

    # Polling max 6 minut (24 próby × 15s)
    for attempt in range(24):
        time.sleep(15)
        waited = (attempt + 1) * 15

        poll = requests.get(
            f"{GOAPI_BASE_URL}/{task_id}",
            headers=headers,
            timeout=30,
        )

        if poll.status_code != 200:
            print(f"[Agent2] Polling error: {poll.status_code} — próba {attempt+1}")
            continue

        task_data = poll.json().get("data", {})
        status    = task_data.get("status", "")
        print(f"[Agent2] Status: {status} ({waited}s)")

        if status in ("success", "completed"):
            clips = task_data.get("clips", {})
            if clips:
                first_id  = list(clips.keys())[0]
                audio_url = clips[first_id].get("audio_url")
                if audio_url:
                    print(f"[Agent2] ✅ Audio gotowe!")
                    # Sprawdzamy format pliku
                    ext = "wav" if ".wav" in audio_url.lower() else "mp3"
                    return {"audio_url": audio_url, "ext": ext}

        elif status in ("failed", "error"):
            raise Exception(f"GoAPI failed: {task_data.get('error', 'unknown')}")

    raise Exception("Timeout — GoAPI nie wygenerowało muzyki w 360s")


def upload_to_supabase(audio_url: str, order_id: str, ext: str) -> str:
    """
    Pobiera plik audio z GoAPI i wgrywa do Supabase Storage.
    Agent 3 pobierze go stamtąd przez publiczny URL.
    """
    print(f"[Agent2] Pobieram audio ({ext.upper()})...")
    resp = requests.get(audio_url, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"Nie mogę pobrać audio: {resp.status_code}")

    filename     = f"{order_id}/song.{ext}"
    content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"

    print(f"[Agent2] Wgrywam do Supabase Storage...")
    supabase.storage.from_("orders").upload(
        path=filename,
        file=resp.content,
        file_options={"content-type": content_type},
    )

    public_url = supabase.storage.from_("orders").get_public_url(filename)
    size_kb    = len(resp.content) // 1024
    print(f"[Agent2] ✅ Wgrano ({size_kb} KB): {public_url}")
    return public_url


def run(song_text: str, order: dict) -> dict:
    """
    Główna funkcja Agenta 2 — uruchamiana przez main.py.

    Args:
        song_text: tekst piosenki od Agenta 1
        order:     dane zamówienia z Supabase

    Returns:
        dict: {success, audio_url, ext, error}
    """
    try:
        style = get_style_prompt(
            order.get("music_style", "pop"),
            order.get("occasion",    "urodziny"),
            order["package_type"],
        )

        # Generujemy i czekamy na muzykę
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
        return {
            "success":   False,
            "audio_url": None,
            "ext":       "mp3",
            "error":     str(e),
        }
