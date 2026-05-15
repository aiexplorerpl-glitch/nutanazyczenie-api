"""
AGENT 1 — TEKŚCIARZ
===================
Odpowiada za:
1. Odebranie danych zamówienia
2. Wygenerowanie spersonalizowanego tekstu piosenki przez OpenAI GPT-4o
3. Wygenerowanie krótkiego wiersza (4 wersy) jako gratis
4. Zwrócenie gotowych tekstów do main.py
"""

import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def get_song_structure(package_type: str) -> dict:
    """
    Zwraca wymaganą strukturę i długość piosenki w zależności od pakietu.
    - piosenka / wideo  → ~2 minuty  (36-44 linijki)
    - premium           → 2.5-3 min  (72-92 linijki)
    """
    if package_type == "premium":
        return {
            "dlugosc": "2,5 do 3 minut",
            "struktura": (
                "[Intro] - 6-8 słów mówionych\n"
                "[Verse 1] - 10-12 linijek\n"
                "[Pre-Chorus] - 4 linijki\n"
                "[Chorus] - 8-10 linijek (chwytliwy, powtarzalny)\n"
                "[Verse 2] - 10-12 linijek\n"
                "[Pre-Chorus] - 4 linijki\n"
                "[Chorus] - 8-10 linijek\n"
                "[Bridge] - 6-8 linijek (emocjonalny)\n"
                "[Final Chorus] - 8-10 linijek (z wariacją)\n"
                "[Outro] - 6-8 słów mówionych\n"
                "ŁĄCZNIE: 72-92 linijki"
            ),
        }
    else:
        return {
            "dlugosc": "około 2 minut",
            "struktura": (
                "[Intro] - 4-6 słów mówionych\n"
                "[Verse 1] - 8 linijek\n"
                "[Chorus] - 6-8 linijek (chwytliwy, powtarzalny)\n"
                "[Verse 2] - 8 linijek\n"
                "[Chorus] - 6-8 linijek (powtórzenie)\n"
                "[Outro] - 4-6 słów mówionych\n"
                "ŁĄCZNIE: 36-44 linijki"
            ),
        }


def generate_song_text(order: dict) -> str:
    """Generuje spersonalizowany tekst piosenki na podstawie zamówienia."""

    structure = get_song_structure(order["package_type"])

    prompt = f"""Napisz spersonalizowaną piosenkę według poniższych wytycznych.

DANE ZAMÓWIENIA:
- Imię osoby obdarowywanej: {order["recipient_name"]}
- Okazja: {order["occasion"]}
- Opis osoby: {order["person_desc"]}
- Co ma zawierać piosenka: {order["content_desc"]}
- Styl muzyczny: {order.get("music_style", "pop")}
- Wymagana długość: {structure["dlugosc"]}

WYMAGANA STRUKTURA:
{structure["struktura"]}

ZASADY:
1. Użyj imienia "{order["recipient_name"]}" minimum 3 razy
2. Uwzględnij minimum 2 szczegóły z opisu osoby
3. Refren musi być chwytliwy i łatwy do zapamiętania
4. Styl muzyczny: {order.get("music_style", "pop")}
5. Pisz PO POLSKU
6. Zachowaj tagi struktury w [ ] nawiasach
7. Tylko tekst — bez komentarzy i wstępów"""

    print(f"[Agent1] Generuję piosenkę dla: {order['recipient_name']}...")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Jesteś profesjonalnym autorem tekstów piosenek po polsku. "
                    "Tworzysz wzruszające, śmieszne lub energiczne piosenki na zamówienie. "
                    "Zawsze uwzględniasz personalizację i szczegóły z opisu osoby."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.85,
        max_tokens=3000,  # 3000 żeby premium (72-92 linijki) nie było ucinane
    )

    text = response.choices[0].message.content.strip()
    print(f"[Agent1] ✅ Tekst piosenki gotowy ({len(text)} znaków)")
    return text


def generate_poem(order: dict) -> str:
    """Generuje krótki wiersz 4-wersowy jako gratis do zamówienia."""

    prompt = f"""Napisz wiersz dokładnie 4 linijki dla {order["recipient_name"]}.

Okazja: {order["occasion"]}

ZASADY:
1. Dokładnie 4 linijki — nie więcej, nie mniej
2. Musi się rymować (ABAB lub AABB)
3. Zawiera imię {order["recipient_name"]}
4. Nawiązuje do okazji: {order["occasion"]}
5. Pisz PO POLSKU — używaj naturalnych, poprawnych gramatycznie zwrotów
6. Każda linijka musi być sensownym, pełnym zdaniem lub frazą
7. Sprawdź że każde słowo pasuje do kontekstu i ma sens w tym miejscu
8. NIE używaj słów które nie pasują do zdania (np. "barwny, wiosny" jest błędem)
9. Tylko 4 linijki — bez tytułu, bez komentarzy"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "Jesteś poetą tworzącym krótkie, piękne wiersze po polsku.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=200,
    )

    poem = response.choices[0].message.content.strip()
    print(f"[Agent1] ✅ Wiersz gotowy")
    return poem


def run(order: dict) -> dict:
    """
    Główna funkcja Agenta 1 — uruchamiana przez main.py.

    Args:
        order: dane zamówienia (dict z Supabase)

    Returns:
        dict: {success, song_text, poem, error}
    """
    try:
        song_text = generate_song_text(order)
        poem = generate_poem(order)
        return {"success": True, "song_text": song_text, "poem": poem}
    except Exception as e:
        print(f"[Agent1] ❌ Błąd: {e}")
        return {"success": False, "song_text": None, "poem": None, "error": str(e)}
