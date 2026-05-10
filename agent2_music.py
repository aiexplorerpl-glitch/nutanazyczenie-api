"""
AGENT 2 — MUZYK
===============
Odpowiada za:
1. Odebranie tekstu piosenki od Agenta 1
2. Wysłanie do Suno API z odpowiednim promptem stylu
3. Czekanie na wygenerowanie MP3
4. Pobranie i zapisanie pliku MP3
5. Zwrócenie ścieżki do pliku MP3
"""

import os
import time
import requests

SUNO_API_KEY = os.environ.get("SUNO_API_KEY")
SUNO_BASE_URL = "https://studio-api.suno.ai/api"

# Mapowanie stylów muzycznych na tagi Suno
STYLE_MAP = {
    "pop": "polish pop, upbeat, catchy, modern",
    "ballada": "polish ballad, emotional, piano, slow tempo",
    "hip-hop": "polish hip hop, rap, boom bap, 95 bpm",
    "folk": "polish folk, accordion, biesiadna, festive, upbeat 130 bpm",
    "rock": "polish rock, guitar, energetic, powerful",
    "jazz": "polish jazz, saxophone, smooth, relaxed",
    "klasyczna": "classical polish, orchestral, elegant, emotional",
}


def get_suno_style(music_style: str, occasion: str) -> str:
    """
    Buduje prompt stylu dla Suno na podstawie wybranego stylu i okazji.
    Suno generuje muzykę na podstawie opisu stylu — im dokładniejszy, tym lepszy efekt.
    """
    base_style = STYLE_MAP.get(
        music_style.lower().split("/")[0].strip(),
        "polish pop, upbeat, modern"
    )

    # Dodajemy nastrój zależny od okazji
    occasion_lower = occasion.lower()
    if "urodziny" in occasion_lower or "imieniny" in occasion_lower:
        mood = "celebratory, birthday, joyful, happy"
    elif "ślub" in occasion_lower or "rocznica" in occasion_lower:
        mood = "romantic, emotional, wedding, love"
    elif "walentynki" in occasion_lower:
        mood = "romantic, love song, tender"
    elif "absolutorium" in occasion_lower or "awans" in occasion_lower:
        mood = "triumphant, celebratory, proud"
    else:
        mood = "warm, celebratory, personal"

    return f"{base_style}, {mood}, Polish language vocals, complete song with intro verse chorus outro"


def generate_music(song_text: str, order: dict) -> dict:
    """
    Wysyła tekst do Suno API i czeka na wygenerowanie muzyki.

    Args:
        song_text: tekst piosenki od Agenta 1
        order: dane zamówienia

    Returns:
        dict: {success, audio_url, song_id, error}
    """
    style = get_suno_style(
        order.get("music_style", "pop"),
        order.get("occasion", "urodziny")
    )

    # Długość zależna od pakietu
    if order["package_type"] == "premium":
        duration_hint = "2.5 to 3 minute song, extended version with bridge"
    else:
        duration_hint = "2 minute song, complete with verse chorus structure"

    full_style = f"{style}, {duration_hint}"

    print(f"[Agent2] Wysyłam do Suno API...")
    print(f"[Agent2] Styl: {full_style}")

    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": song_text,
        "style": full_style,
        "title": f"Piosenka dla {order['recipient_name']}",
        "make_instrumental": False,
        "wait_audio": False,  # nie czekamy synchronicznie — polling niżej
    }

    # Wysyłamy żądanie generowania
    response = requests.post(
        f"{SUNO_BASE_URL}/generate",
        json=payload,
        headers=headers,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"Suno API error {response.status_code}: {response.text}")

    data = response.json()
    song_ids = [item["id"] for item in data]
    song_id = song_ids[0]
    print(f"[Agent2] Suno ID: {song_id} — czekam na generowanie...")

    # Polling — sprawdzamy co 10 sekund czy muzyka jest gotowa
    # Suno zazwyczaj generuje w 60-120 sekund
    audio_url = poll_for_audio(song_id, headers)
    return {"success": True, "audio_url": audio_url, "song_id": song_id}


def poll_for_audio(song_id: str, headers: dict, max_wait: int = 300) -> str:
    """
    Odpytuje Suno API co 10 sekund aż muzyka będzie gotowa.
    Maksymalny czas oczekiwania: 5 minut.
    """
    waited = 0
    while waited < max_wait:
        time.sleep(10)
        waited += 10

        response = requests.get(
            f"{SUNO_BASE_URL}/get?ids={song_id}",
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            print(f"[Agent2] Polling error: {response.status_code}")
            continue

        data = response.json()
        if not data:
            continue

        song = data[0]
        status = song.get("status", "")
        print(f"[Agent2] Status: {status} (czekam {waited}s)")

        if status == "complete":
            audio_url = song.get("audio_url")
            if audio_url:
                print(f"[Agent2] ✅ Muzyka gotowa!")
                return audio_url

        elif status == "error":
            raise Exception(f"Suno generation failed: {song.get('error', 'unknown')}")

    raise Exception(f"Timeout — Suno nie wygenerował muzyki w {max_wait}s")


def download_mp3(audio_url: str, order_id: str) -> str:
    """
    Pobiera plik MP3 z Suno i zapisuje lokalnie.
    Zwraca ścieżkę do zapisanego pliku.
    """
    os.makedirs("/tmp/nutanazyczenie", exist_ok=True)
    filepath = f"/tmp/nutanazyczenie/{order_id}_song.mp3"

    print(f"[Agent2] Pobieram MP3...")
    response = requests.get(audio_url, timeout=60)

    if response.status_code != 200:
        raise Exception(f"Nie mogę pobrać MP3: {response.status_code}")

    with open(filepath, "wb") as f:
        f.write(response.content)

    size_kb = len(response.content) // 1024
    print(f"[Agent2] ✅ MP3 zapisany: {filepath} ({size_kb} KB)")
    return filepath


def run(song_text: str, order: dict) -> dict:
    """
    Główna funkcja Agenta 2 — uruchamiana przez main.py.

    Args:
        song_text: tekst piosenki od Agenta 1
        order: dane zamówienia

    Returns:
        dict: {success, mp3_path, audio_url, error}
    """
    try:
        # Generujemy muzykę w Suno
        result = generate_music(song_text, order)

        # Pobieramy plik MP3 lokalnie
        mp3_path = download_mp3(result["audio_url"], str(order["id"]))

        return {
            "success": True,
            "mp3_path": mp3_path,
            "audio_url": result["audio_url"],
        }

    except Exception as e:
        print(f"[Agent2] ❌ Błąd: {e}")
        return {
            "success": False,
            "mp3_path": None,
            "audio_url": None,
            "error": str(e),
        }
