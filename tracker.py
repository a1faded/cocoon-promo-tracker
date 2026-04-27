import requests
from bs4 import BeautifulSoup
import os
import re
from datetime import datetime

URL = "https://www.cocoonbysealy.com/"
WEBHOOK = os.environ.get("WEBHOOK_URL")

LAST_FILE = "last_promo.txt"


def send(msg):
    if WEBHOOK:
        requests.post(WEBHOOK, json={"content": msg})


def fetch_promo():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    hero = soup.select_one(".home-oct16-hero__description")
    if not hero:
        return None

    return hero.get_text(" ", strip=True)


def extract_end_phrase(text):
    match = re.search(r"ends\s+\w+", text.lower())
    return match.group(0) if match else "no end date found"


def load_last():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_current(promo):
    with open(LAST_FILE, "w") as f:
        f.write(promo)


def main():
    promo = fetch_promo()

    if not promo:
        send("⚠️ Could not find promo section")
        return

    last_promo = load_last()

    print("Current promo:", promo)

    # 🔁 Only act if promo changed
    if promo != last_promo:
        end_info = extract_end_phrase(promo)

        message = f"🔄 Promo changed:\n{promo}\n\n📅 {end_info}"

        send(message)

        # 🔥 Visa detection
        if "visa" in promo.lower() and "gift card" in promo.lower():
            send("🚨 VISA GIFT CARD PROMO LIVE 🚨")

        save_current(promo)
    else:
        print("No change. Skipping notification.")


if __name__ == "__main__":
    main()
