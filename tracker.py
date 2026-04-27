import requests
from bs4 import BeautifulSoup
import os
import re
import time
from datetime import datetime

URL = "https://www.cocoonbysealy.com/"
WEBHOOK = os.environ.get("WEBHOOK_URL")

LAST_FILE = "last_promo.txt"


# -------------------------
# DISCORD
# -------------------------
def send(msg):
    if WEBHOOK:
        requests.post(WEBHOOK, json={"content": msg})


# -------------------------
# FETCH (DOUBLE CHECK)
# -------------------------
def fetch_promo_stable():
    headers = {"User-Agent": "Mozilla/5.0"}

    def get_text():
        r = requests.get(URL, headers=headers)
        soup = BeautifulSoup(r.text, "html.parser")
        hero = soup.select_one(".home-oct16-hero__description")
        return hero.get_text(" ", strip=True) if hero else None

    first = get_text()
    time.sleep(5)  # wait for site to stabilize
    second = get_text()

    print("First fetch:", first)
    print("Second fetch:", second)

    if second and first != second:
        return second

    return first


# -------------------------
# FIX "ENDS MONDAY" BUG
# -------------------------
def fix_end_day_bug(text):
    text_lower = text.lower()
    today = datetime.now().strftime("%A").lower()

    if f"ends {today}" in text_lower:
        text = re.sub(
            f"ends {today}",
            "ends today",
            text,
            flags=re.IGNORECASE
        )

    return text


# -------------------------
# EXTRACT END TEXT
# -------------------------
def extract_end_phrase(text):
    match = re.search(r"ends\s+\w+", text.lower())
    return match.group(0) if match else "no end date found"


# -------------------------
# SMART GIFT CARD DETECTION
# -------------------------
def gift_card_score(text):
    text = text.lower()
    keywords = ["visa", "gift", "card", "prepaid", "reward", "bonus"]
    return sum(1 for word in keywords if word in text)


def is_gift_card_promo(text):
    score = gift_card_score(text)

    if "visa" in text.lower():
        return True

    if "gift card" in text.lower():
        return True

    return score >= 2


# -------------------------
# STORAGE
# -------------------------
def load_last():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_current(promo):
    with open(LAST_FILE, "w") as f:
        f.write(promo)


# -------------------------
# MAIN
# -------------------------
def main():
    promo = fetch_promo_stable()

    if not promo:
        send("⚠️ Could not find promo section")
        return

    promo = fix_end_day_bug(promo)

    last_promo = load_last()

    print("Final promo:", promo)

    # Only act if changed
    if promo != last_promo:
        end_info = extract_end_phrase(promo)

        send(f"🔄 Promo changed:\n{promo}\n\n📅 {end_info}")

        # Gift card detection
        score = gift_card_score(promo)
        if is_gift_card_promo(promo):
            send(f"🚨 POSSIBLE GIFT CARD PROMO (score={score}) 🚨\n{promo}")

        save_current(promo)

    else:
        print("No change detected.")


if __name__ == "__main__":
    main()
