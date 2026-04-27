import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

URL = "https://www.cocoonbysealy.com/"
WEBHOOK = os.environ.get("WEBHOOK_URL")

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

def main():
    promo = fetch_promo()

    if not promo:
        send("⚠️ Could not find promo section")
        return

    promo_lower = promo.lower()

    print("Current promo:", promo)

    # 🔥 Detect Visa promo
    if "visa" in promo_lower and "gift card" in promo_lower:
        send("🚨 VISA GIFT CARD PROMO LIVE 🚨\n" + promo)

    # Optional: always log promo
    send("ℹ️ Current promo:\n" + promo)


if __name__ == "__main__":
    main()
