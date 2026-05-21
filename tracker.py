import os
import re
import time
import json
import html as html_lib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://www.cocoonbysealy.com/"
WEBHOOK = os.environ.get("WEBHOOK_URL")
LAST_FILE = "last_promo.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def send(msg):
    if WEBHOOK:
        try:
            requests.post(WEBHOOK, json={"content": msg[:1900]}, timeout=20)
        except Exception as e:
            print("Discord send failed:", e)


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_page():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    return r.status_code, r.text


def extract_from_html(page_html):
    soup = BeautifulSoup(page_html, "html.parser")

    selectors = [
        ".home-oct16-hero__description--desktop",
        ".home-oct16-hero__description--mobile",
        ".home-oct16-hero__description",
        ".home-oct16-hero__copy",
        ".hero.home-oct16-hero",
        ".promo-condtional-block .banner-block",
        ".promo-conditional-block .banner-block",
    ]

    candidates = []

    for sel in selectors:
        for el in soup.select(sel):
            text = normalize(el.get_text(" ", strip=True))
            if is_likely_promo(text):
                candidates.append(text)

    # Fallback: promo callout spans near promo copy
    for el in soup.select(".promo_callout_RTF"):
        parent_text = normalize(el.find_parent().get_text(" ", strip=True) if el.find_parent() else el.get_text(" ", strip=True))
        if parent_text:
            candidates.append(parent_text)

    # Fallback: settings JSON sometimes contains primary_promo_callout_message
    raw = page_html
    m = re.search(r'"primary_promo_callout_message"\s*:\s*"([^"]*)"', raw)
    if m:
        candidates.append(normalize(html_lib.unescape(m.group(1))))

    # Fallback: regex around mattress sale text
    m2 = re.search(
        r"(?:Memorial Day sale|weekend super sale|sale).{0,250}?(?:Save\s+\d+%[^<]{0,100}Mattress[^<]{0,100})",
        raw,
        flags=re.I | re.S,
    )
    if m2:
        cleaned = BeautifulSoup(m2.group(0), "html.parser").get_text(" ", strip=True)
        candidates.append(normalize(cleaned))

    # Prefer richest candidate
    candidates = [c for c in candidates if c and len(c) > 8]
    candidates = list(dict.fromkeys(candidates))

    if candidates:
        return max(candidates, key=len)

    return None


def is_likely_promo(text):
    t = text.lower()
    promo_words = ["save", "sale", "ends", "mattress", "gift", "card", "visa", "bundle", "off"]
    return sum(1 for w in promo_words if w in t) >= 2


def fetch_promo_stable():
    results = []

    for i in range(3):
        status, page = get_page()
        promo = extract_from_html(page)

        print(f"Fetch {i+1} status:", status)
        print(f"Fetch {i+1} promo:", promo)

        results.append((status, promo, page[:500]))

        time.sleep(5)

    promos = [p for _, p, _ in results if p]

    if promos:
        # If multiple found, use the latest successful one
        return promos[-1]

    # Debug failure
    last_status, _, snippet = results[-1]
    challenge_words = ["challenge", "captcha", "awswaf", "recaptcha", "access denied"]
    challenge_detected = any(w in snippet.lower() for w in challenge_words)

    send(
        "⚠️ Could not find promo section.\n"
        f"HTTP status: {last_status}\n"
        f"Possible WAF/challenge page: {challenge_detected}\n"
        f"Page snippet:\n```{snippet[:900]}```"
    )

    return None


def fix_end_day_bug(text):
    today = datetime.now().strftime("%A").lower()
    return re.sub(f"ends {today}", "ends today", text, flags=re.IGNORECASE)


def extract_end_phrase(text):
    match = re.search(r"ends\s+\w+", text.lower())
    return match.group(0) if match else "no end date found"


def gift_card_score(text):
    text = text.lower()
    keywords = ["visa", "gift", "card", "prepaid", "reward", "bonus"]
    return sum(1 for word in keywords if word in text)


def is_gift_card_promo(text):
    t = text.lower()
    score = gift_card_score(t)
    return "visa" in t or "gift card" in t or score >= 2


def load_last():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r") as f:
            return f.read().strip()
    return None


def save_current(promo):
    with open(LAST_FILE, "w") as f:
        f.write(promo)


def main():
    promo = fetch_promo_stable()

    if not promo:
        return

    promo = fix_end_day_bug(promo)
    last_promo = load_last()

    print("Final promo:", promo)

    if promo != last_promo:
        end_info = extract_end_phrase(promo)
        send(f"🔄 Promo changed:\n{promo}\n\n📅 {end_info}")

        score = gift_card_score(promo)
        if is_gift_card_promo(promo):
            send(f"🚨 POSSIBLE GIFT CARD PROMO DETECTED score={score} 🚨\n{promo}")

        save_current(promo)
    else:
        print("No change detected.")


if __name__ == "__main__":
    main()
