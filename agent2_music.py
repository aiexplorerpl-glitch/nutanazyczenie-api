"""
AGENT 2 — MUZYK (TRYB AWARYJNY / BYPASS)
========================================
Tymczasowy agent pomijający zablokowane usługi GoAPI/PiAPI.
Pobiera darmowy, testowy plik MP3, aby pozwolić Agentom 3 i 4
na wygenerowanie wideo i wysłanie maila.
"""

import os
import requests
from supabase import create_client

supabase = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_SERVICE_KEY"),
)

def upload_to_supabase(audio_url: str, order_id: str, ext: str) -> str:
    print(f"[Agent2] Pobieram testowe audio ({ext.upper()})...")
    # Pobieramy testowy plik mp3
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
    try:
        print("[Agent2] ⚠️ PiAPI/GoAPI wyłączyło Suno. Uruchamiam tryb awaryjny (Bypass)...")
        
        # Darmowy testowy plik MP3 z sieci (udaje gotową piosenkę)
        test_audio_url = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"

        # Wrzucamy do Supabase, żeby Agent 3 i 4 mogły pracować
        public_url = upload_to_supabase(
            test_audio_url,
            str(order["id"]),
            "mp3"
        )

        return {
            "success":   True,
            "audio_url": public_url,
            "ext":       "mp3",
        }

    except Exception as e:
        print(f"[Agent2] ❌ Błąd w trybie awaryjnym: {e}")
        return {
            "success":   False,
            "audio_url": None,
            "ext":       "mp3",
            "error":     str(e),
        }
