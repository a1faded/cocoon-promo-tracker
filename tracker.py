import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.cocoonbysealy.com/"
WEBHOOK = os.environ.get("WEBHOOK_URL")
LAST_FILE = "last_promo.txt"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)


# -------------------------
# DISCORD
# -------------------------
def send(msg):
    if not WEBHOOK:
        print("WEBHOOK_URL missing. Message would have been:")
        print(msg)
        return

    try:
        requests.post(WEBHOOK, json={"content": msg[:1900]}, timeout=20)
    except Exception as e:
        print("Discord send failed:", e)


# -------------------------
# TEXT HELPERS
# -------------------------
def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def is_challenge_page(page_html):
    t = (page_html or "").lower()
    challenge_signals = [
        "awswaf",
        "gokuprops",
        "window.gokuprops",
        "challenge.js",
        "captcha",
        "recaptcha",
        "access denied",
    ]
    return any(signal in t for signal in challenge_signals)


def is_likely_promo(text):
    t = text.lower()
    promo_words = [
        "save",
        "sale",
        "ends",
        "mattress",
        "mattresses",
        "gift",
        "card",
        "visa",
        "bundle",
        "off",
        "prepaid",
        "reward",
        "bonus",
    ]
    return sum(1 for word in promo_words if word in t) >= 2


# -------------------------
# PROMO EXTRACTION
# -------------------------
def extract_from_html(page_html):
    soup = BeautifulSoup(page_html, "html.parser")

    selectors = [
        ".home-oct16-hero__description--desktop",
        ".home-oct16-hero__description--mobile",
        ".home-oct16-hero__description",
        ".home-oct16-hero__copy",
        ".hero.home-oct16-hero",
    ]

    candidates = []

    for selector in selectors:
        for el in soup.select(selector):
            text = normalize(el.get_text(" ", strip=True))
            if text and is_likely_promo(text):
                candidates.append(text)

    # Fallback: promo callout span, usually the "Ends Today / Ends Monday" text
    for el in soup.select(".promo_callout_RTF"):
        parent = el.find_parent()
        text = normalize(parent.get_text(" ", strip=True) if parent else el.get_text(" ", strip=True))
        if text and is_likely_promo(text):
            candidates.append(text)

    # Regex fallback if classes change but copy is still in the page
    raw_text = normalize(soup.get_text(" ", strip=True))
    regex_patterns = [
        r"((?:memorial day|weekend|super|summer|flash|holiday)?\s*sale.{0,220}?(?:save|get|receive).{0,220}?(?:mattress|mattresses|visa|gift card|prepaid card))",
        r"((?:save|get|receive).{0,220}?(?:mattress|mattresses|visa|gift card|prepaid card).{0,120}?(?:ends\s+\w+)?)",
    ]

    for pattern in regex_patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            text = normalize(match.group(1))
            if text and is_likely_promo(text):
                candidates.append(text)

    candidates = [c for c in candidates if c and len(c) > 10]
    candidates = list(dict.fromkeys(candidates))

    if not candidates:
        return None

    return max(candidates, key=len)


# -------------------------
# BROWSER FETCH
# -------------------------
def browser_fetch_once():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1440, "height": 1200},
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = context.new_page()

        status = "unknown"
        final_html = ""

        try:
            response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            if response:
                status = response.status

            # Give WAF / JS hydration time to settle
            page.wait_for_timeout(10000)

            for cycle in range(4):
                final_html = page.content()
                promo = extract_from_html(final_html)

                print(f"Browser cycle {cycle + 1} status:", status)
                print(f"Browser cycle {cycle + 1} challenge:", is_challenge_page(final_html))
                print(f"Browser cycle {cycle + 1} promo:", promo)

                if promo:
                    browser.close()
                    return promo, status, final_html

                # If WAF/challenge page, wait and reload once or twice
                if is_challenge_page(final_html):
                    page.wait_for_timeout(8000)
                    try:
                        response = page.reload(wait_until="domcontentloaded", timeout=60000)
                        if response:
                            status = response.status
                        page.wait_for_timeout(8000)
                    except PlaywrightTimeoutError:
                        print("Reload timed out during WAF challenge handling.")
                else:
                    page.wait_for_timeout(5000)

        except Exception as e:
            print("Browser fetch failed:", e)

        browser.close()
        return None, status, final_html


def fetch_promo_stable():
    first, first_status, first_html = browser_fetch_once()

    time.sleep(5)

    second, second_status, second_html = browser_fetch_once()

    print("First browser fetch:", first)
    print("Second browser fetch:", second)

    # Prefer second result if it exists and changed after hydration
    if second and second != first:
        return second

    if first:
        return first

    if second:
        return second

    final_html = second_html or first_html or ""
    snippet = final_html[:900]

    send(
        "⚠️ Could not find promo section after browser fetch.\n"
        f"HTTP status: {second_status or first_status}\n"
        f"Possible WAF/challenge page: {is_challenge_page(final_html)}\n"
        f"Page snippet:\n```{snippet}```"
    )

    return None


# -------------------------
# PROMO BUG FIXES / DETECTION
# -------------------------
def fix_end_day_bug(text):
    today = datetime.now().strftime("%A").lower()
    return re.sub(f"ends {today}", "ends today", text, flags=re.IGNORECASE)


def extract_end_phrase(text):
    match = re.search(r"ends\s+\w+", text.lower())
    return match.group(0) if match else "no end date found"


def gift_card_score(text):
    t = text.lower()
    keywords = ["visa", "gift", "card", "prepaid", "reward", "bonus"]
    return sum(1 for word in keywords if word in t)


def is_gift_card_promo(text):
    t = text.lower()
    score = gift_card_score(t)

    if "visa" in t:
        return True

    if "gift card" in t:
        return True

    if "prepaid card" in t:
        return True

    return score >= 2


# -------------------------
# STORAGE
# -------------------------
def load_last():
    if os.path.exists(LAST_FILE):
        with open(LAST_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def save_current(promo):
    with open(LAST_FILE, "w", encoding="utf-8") as f:
        f.write(promo)


# -------------------------
# MAIN
# -------------------------
def main():
    promo = fetch_promo_stable()

    if not promo:
        return

    promo = fix_end_day_bug(promo)
    last_promo = load_last()

    print("Final promo:", promo)
    print("Last promo:", last_promo)

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
