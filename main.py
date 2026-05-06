import asyncio, logging, os, re
from typing import Optional
from urllib.parse import urlparse
from curl_cffi import requests
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = "8784990195:AAGBiLJ42VhBweXHF6ghg1m9kcxz2xxgmCk"
SERVICEABILITY_URL = "https://2.rome.api.flipkart.net/3/product/serviceability"
USER_AGENT = "Mozilla/5.0 (Linux; Android 11; Pixel 5 Build/RQ3A.211001.001) FKUA/Retail/2270300/Android/Tablet (Google/Pixel 5/7f807eaf4b2cdcf4a607bad2f8811b0d)"
DEFAULT_HEADERS = {"content-type": "application/json", "user-agent": "okhttp/4.9.2", "x-user-agent": USER_AGENT, "accept-encoding": "gzip"}
TRACKED_DOMAINS = {"www.flipkart.com", "flipkart.com", "dl.flipkart.com"}

PID_REGEX = re.compile(r"[?&]pid=([A-Za-z0-9]+)")
PID_ENCODED_REGEX = re.compile(r"pid%3D([A-Za-z0-9]+)", re.IGNORECASE)
FLIPKART_URL_REGEX = re.compile(r"(https?://(?:www\.)?flipkart\.com/[\w-]+/p/[\w-]+(?:\?[^&\s]*)?|https?://dl\.flipkart\.com/[^\s]+)")


PINCODE_CITY_MAPPING = {
    "Panipat": ["132103", "132106", "132108", "132105"],
    "Delhi": ["110008", "110001", "110010", "110053","110009"],
    "Panchkula": ["160101","134112"],
    "Gurgaon": ["122001"],
    "Bathinda": ["151001"],
    "Jagraon": ["142026"],
    "Ulhasnagar": ["421005"],
    "Ambernath": ["421501"],
    "Pune": ["412207", "411036"],
    "Jaipur": ["302020", "302029", "303012"],
    "Bikaner": ["334001", "334002", "334003", "334022", "334023"],
    "Gajsinghpur": ["335024"],
    "Raisinghnagar": ["335051"],
    "Sriganganagar": ["335001"],
    "Aurangabad": ["431001", "431005"],
    "Navi Mumbai": ["410209"],
    "Ludhiana": ["141001", "141002", "141003"],
    "Vijaynagar": ["335704"],
    "Jammu": ["180001"],
    "Hanumangarh": ["335512", "335513"],
    "Karanpur": ["322243"],
    "Suratgarh": ["335804"],
    "Indore": ["453331"],
    "Ghaziabad": ["201013"],
    "Mumbai": ["400095", "400067", "400020"],
    "Bihar": ["801503"]
}

PINCODES_TO_CHECK = [pin for city_pincodes in PINCODE_CITY_MAPPING.values() for pin in city_pincodes]

def get_city(pin: str) -> str:
    return next((city for city, pins in PINCODE_CITY_MAPPING.items() if pin in pins), "Unknown")

def extract_urls(text: str) -> list[str]:
    return FLIPKART_URL_REGEX.findall(text or "")

def get_domain(url: str) -> str:
    try: return urlparse('https://' + url if not url.startswith(('http://', 'https://')) else url).netloc.lower()
    except: return ""

def extract_pid(url: str) -> Optional[str]:
    if not url: return None
    return (match := PID_REGEX.search(url)) and match.group(1) or (match := PID_ENCODED_REGEX.search(url)) and match.group(1)

async def resolve_url(session: requests.AsyncSession, url: str) -> Optional[str]:
    try: return str((await session.get(url, impersonate="chrome110", timeout=30)).url)
    except Exception as e: logger.warning(f"Failed to resolve URL {url}: {e}"); return None

async def get_product_id(text: str) -> Optional[str]:
    urls = extract_urls(text)
    if not urls: return None
    async with requests.AsyncSession() as session:
        for url in urls:
            domain = get_domain(url)
            if domain not in TRACKED_DOMAINS: continue
            if "flipkart.com" in domain:
                if pid := extract_pid(url): return pid
                if pid := extract_pid(await resolve_url(session, url) or ""): return pid
            elif "dl.flipkart.com" in domain:
                final_url = await resolve_url(session, url) or ""
                if "/p/" in final_url and "flipkart.com" in final_url and (pid := extract_pid(final_url)): return pid
    return None

def build_payload(pid: str, pin: str) -> dict:
    return {"requestContext": {"marketplace": "FLIPKART", "products": [{"productId": pid}]}, "locationContext": {"pincode": str(pin)}}


async def check_pin(pin: str, pid: str, session: requests.AsyncSession, sem: asyncio.Semaphore) -> tuple[str, bool]:
    try:
        async with sem:
            resp = await session.post(SERVICEABILITY_URL, json=build_payload(pid, pin), headers=DEFAULT_HEADERS, impersonate="chrome110", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return pin, bool(data.get("RESPONSE", {}).get(pid, {}).get("listingSummary", {}).get("serviceable", False))
    except Exception as e: logger.error(f"Error checking {pin}: {e}"); return pin, False

async def check_all_pins(pid: str, pins: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    sem = asyncio.Semaphore(50)
    async with requests.AsyncSession() as session:
        results = await asyncio.gather(*[check_pin(pin, pid, session, sem) for pin in pins])
    available = [pin for pin, ok in results if ok]
    cities = {}
    for pin in available:
        city = get_city(pin)
        cities.setdefault(city, []).append(pin)
    for city in cities: cities[city].sort()
    return sorted(cities.keys()), cities


async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text or ""
    if not any(d in text for d in ("flipkart.com", "dl.flipkart.com")): return
    if not (pid := await get_product_id(text)): return
    await context.bot.send_message(update.effective_chat.id, f"🔎 Checking {len(PINCODES_TO_CHECK)} pincodes...")
    cities, city_pins = await check_all_pins(pid, PINCODES_TO_CHECK)
    if not cities: await update.effective_message.reply_text("❌ Product is not available ❌"); return
    total = sum(len(pins) for pins in city_pins.values())
    lines = [f"✅ Available in {total} pincodes ✅"]
    for city in cities:
        pins = city_pins[city]
        lines.append(f"• {city}: {', '.join(pins)}" if len(pins) <= 5 else f"• {city}: {pins[0][:3]}0xx ({len(pins)} codes: {', '.join(p[-3:] for p in pins)})")
    await update.effective_message.reply_text("\n".join(lines))

def main():
    if not TELEGRAM_BOT_TOKEN: print("Set TELEGRAM_BOT_TOKEN in .env file."); return
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).connect_timeout(30).read_timeout(30).write_timeout(30).pool_timeout(30).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🤖 started")
    try: app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, close_loop=False)
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__": main()
