"""
AGENT 2 — MUZYK (sunor.cc)
===========================
Generuje muzykę przez sunor.cc — działające API Suno V5.5
Endpoint: https://sunor.cc/api/v1/task
"""

import os
import time
import requests
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

SUNO_API_KEY  = os.environ.get("SUNO_API_KEY")
SUNOR_API_URL = "https://sunor.cc/api/v1"

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
    "pożegnanie":   "warm, nostalgic, bittersweet",
}


def get_style_prompt(music_style: str, occasion: str, package_type: str) -> str:
    style_key = music_style.lower().split("/")[0].strip()
    base  = STYLE_MAP.get(style_key, "polish pop, upbeat, modern")
    mood  = "warm, celebratory, personal"
    for key, val in OCCASION_MOOD.items():
        if key in occasion.lower():
            mood = val
            break
    duration = "2.5 to 3 minute song" if package_type == "premium" else "2 minute song"
    return f"{base}, {mood}, {duration}, Polish vocals, high quality"


def generate_and_poll(song_text: str, style: str, title: str) -> dict:
    headers = {
        "x-api-key":    SUNO_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "model":     "suno",
        "task_type": "music",
        "input": {
            "prompt":           song_text,
            "tags":             style,
            "title":            title,
            "make_instrumental": False,
        }
    }

    print(f"[Agent2] Wysyłam do sunor.cc...")
    resp = requests.post(
        f"{SUNOR_API_URL}/task",
        json=payload,
        headers=headers,
        timeout=30,
    )

    if resp.status_code not in (200, 201, 202):
        raise Exception(f"sunor.cc error {resp.status_code}: {resp.text}")

    data    = resp.json()
    # sunor.cc zwraca task_id w data.data.task_id
    task_id = (
        data.get("task_id") or
        data.get("data", {}).get("task_id") or
        data.get("id")
    )
    if not task_id:
        raise Exception(f"Brak task_id w odpowiedzi: {data}")

    print(f"[Agent2] Task ID: {task_id} — polling co 15s (max 6 min)...")

    for attempt in range(24):
        time.sleep(15)
        waited = (attempt + 1) * 15

        poll = requests.get(
            f"{SUNOR_API_URL}/task/{task_id}",
            headers=headers,
            timeout=30,
        )

        if poll.status_code != 200:
            print(f"[Agent2] Polling error: {poll.status_code} — próba {attempt+1}")
            continue

        result = poll.json()
        # sunor.cc: status może być w root lub w data
        status = (
            result.get("status") or
            result.get("data", {}).get("status", "")
        )
        print(f"[Agent2] Status: {status} ({waited}s)")

        if status in ("completed", "success", "complete"):
            # sunor.cc: audio_url jest w data.output.result[0].audio_url
            inner  = result.get("data", result)
            output = inner.get("output", {})
            results_list = output.get("result", [])

            audio_url = None
            if results_list and isinstance(results_list, list):
                audio_url = results_list[0].get("audio_url")

            # Fallback — szukaj wszędzie
            if not audio_url:
                audio_url = (
                    inner.get("audio_url") or
                    output.get("audio_url")
                )

            if audio_url:
                ext = "wav" if ".wav" in audio_url.lower() else "mp3"
                print(f"[Agent2] ✅ Audio gotowe: {audio_url[:60]}...")
                return {"audio_url": audio_url, "ext": ext}
            else:
                print(f"[Agent2] ⚠️ Brak audio_url mimo status completed")

        elif status in ("failed", "error"):
            raise Exception(f"sunor.cc failed: {result.get('error', result)}")

    raise Exception("Timeout — sunor.cc nie wygenerował w 360s")


def upload_to_supabase(audio_url: str, order_id: str, ext: str) -> str:
    print(f"[Agent2] Pobieram audio ({ext.upper()})...")
    resp = requests.get(audio_url, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"Nie mogę pobrać audio: {resp.status_code}")

    filename     = f"{order_id}/song.{ext}"
    content_type = "audio/mpeg" if ext == "mp3" else "audio/wav"

    # Usuń stary plik jeśli istnieje (obsługa retry)
    try:
        supabase.storage.from_("orders").remove([filename])
    except Exception:
        pass

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
    try:
        style = get_style_prompt(
            order.get("music_style", "pop"),
            order.get("occasion",    "urodziny"),
            order["package_type"],
        )

        result = generate_and_poll(
            song_text,
            style,
            f"Piosenka dla {order['recipient_name']}",
        )

        public_url = upload_to_supabase(
            result["audio_url"],
            str(order["id"]),
            result["ext"],
        )

        return {"success": True, "audio_url": public_url, "ext": result["ext"]}

    except Exception as e:
        print(f"[Agent2] ❌ Błąd: {e}")
        return {"success": False, "audio_url": None, "ext": "mp3", "error": str(e)}
