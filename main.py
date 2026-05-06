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

TELEGRAM_BOT_TOKEN = os.getenv("8784990195:AAHJKR3nVqvd4P2y2AqpvZahvQ5fBW2JzfQ")

SERVICEABILITY_URL = "https://2.rome.api.flipkart.net/3/product/serviceability"
USER_AGENT = "Mozilla/5.0 (Linux; Android 11; Pixel 5 Build/RQ3A.211001.001) FKUA/Retail/2270300/Android/Tablet (Google/Pixel 5/7f807eaf4b2cdcf4a607bad2f8811b0d)"

DEFAULT_HEADERS = {
    "content-type": "application/json",
    "user-agent": "okhttp/4.9.2",
    "x-user-agent": USER_AGENT,
    "accept-encoding": "gzip",
}

TRACKED_DOMAINS = {"www.flipkart.com", "flipkart.com", "dl.flipkart.com"}

PID_REGEX = re.compile(r"[?&]pid=([A-Za-z0-9]+)")
PID_ENCODED_REGEX = re.compile(r"pid%3D([A-Za-z0-9]+)", re.IGNORECASE)
FLIPKART_URL_REGEX = re.compile(
    r"(https?://(?:www\.)?flipkart\.com/[^\s]+|https?://dl\.flipkart\.com/[^\s]+)"
)

PINCODE_CITY_MAPPING = {
    "Panipat": ["132103", "132106", "132108", "132105"],
    "Delhi": ["110008", "110001", "110010", "110053", "110009"],
    "Panchkula": ["160101", "134112"],
    "Gurgaon": ["122001"],
    "Bathinda": ["151001"],
    "Jagraon": ["142026"],
    "Ulhasnagar": ["421005"],
    "Ambernath": ["421501"],
    "Pune": ["412207", "411036", "411001", "411002", "411004", "411005", "411007", "411014", "411028"],
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
    "Amravati": ["444601", "444602", "444603", "444604"],
    "Yavatmal": ["445001", "445002", "445003"],
    "Nagpur": ["440001", "440002", "440003", "440010", "440015", "440022"],
    "Akola": ["444001", "444002", "444003", "444004"],
    "Hyderabad": ["500001", "500002", "500003", "500004", "500007", "500008", "500012"],
}

PINCODES_TO_CHECK = [
    pin for city_pincodes in PINCODE_CITY_MAPPING.values() for pin in city_pincodes
]

def get_city(pin: str) -> str:
    return next((city for city, pins in PINCODE_CITY_MAPPING.items() if pin in pins), "Unknown")

def extract_urls(text: str) -> list[str]:
    return FLIPKART_URL_REGEX.findall(text or "")

def get_domain(url: str) -> str:
    try:
        parsed = urlparse(url if url.startswith(("http://", "https://")) else "https://" + url)
        return parsed.netloc.lower()
    except Exception:
        return ""

def extract_pid(url: str) -> Optional[str]:
    if not url:
        return None

    match = PID_REGEX.search(url)
    if match:
        return match.group(1)

    match = PID_ENCODED_REGEX.search(url)
    if match:
        return match.group(1)

    return None

async def resolve_url(session: requests.AsyncSession, url: str) -> Optional[str]:
    try:
        response = await session.get(url, impersonate="chrome110", timeout=30)
        return str(response.url)
    except Exception as e:
        logger.warning(f"Failed to resolve URL {url}: {e}")
        return None

async def get_product_id(text: str) -> Optional[str]:
    urls = extract_urls(text)
    if not urls:
        return None

    async with requests.AsyncSession() as session:
        for url in urls:
            domain = get_domain(url)

            if domain not in TRACKED_DOMAINS:
                continue

            pid = extract_pid(url)
            if pid:
                return pid

            final_url = await resolve_url(session, url)
            pid = extract_pid(final_url or "")
            if pid:
                return pid

    return None

def build_payload(pid: str, pin: str) -> dict:
    return {
        "requestContext": {
            "marketplace": "FLIPKART",
            "products": [{"productId": pid}],
        },
        "locationContext": {
            "pincode": str(pin),
        },
    }

async def check_pin(
    pin: str,
    pid: str,
    session: requests.AsyncSession,
    sem: asyncio.Semaphore,
) -> tuple[str, bool]:
    try:
        async with sem:
            resp = await session.post(
                SERVICEABILITY_URL,
                json=build_payload(pid, pin),
                headers=DEFAULT_HEADERS,
                impersonate="chrome110",
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            serviceable = bool(
                data.get("RESPONSE", {})
                .get(pid, {})
                .get("listingSummary", {})
                .get("serviceable", False)
            )

            return pin, serviceable

    except Exception as e:
        logger.error(f"Error checking {pin}: {e}")
        return pin, False

async def check_all_pins(pid: str, pins: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    sem = asyncio.Semaphore(50)

    async with requests.AsyncSession() as session:
        results = await asyncio.gather(
            *[check_pin(pin, pid, session, sem) for pin in pins]
        )

    available = [pin for pin, ok in results if ok]

    cities: dict[str, list[str]] = {}
    for pin in available:
        city = get_city(pin)
        cities.setdefault(city, []).append(pin)

    for city in cities:
        cities[city].sort()

    return sorted(cities.keys()), cities

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    chat = update.effective_chat

    if not message or not chat:
        return

    text = message.text or ""

    if not any(d in text for d in ("flipkart.com", "dl.flipkart.com")):
        return

    pid = await get_product_id(text)
    if not pid:
        await message.reply_text("❌ Could not find product ID from this Flipkart link.")
        return

    await context.bot.send_message(
        chat.id,
        f"🔎 Checking {len(PINCODES_TO_CHECK)} pincodes...",
    )

    cities, city_pins = await check_all_pins(pid, PINCODES_TO_CHECK)

    if not cities:
        await message.reply_text("❌ Product is not available ❌")
        return

    total = sum(len(pins) for pins in city_pins.values())

    lines = [f"✅ Available in {total} pincodes ✅"]

    for city in cities:
        pins = city_pins[city]

        if len(pins) <= 5:
            lines.append(f"• {city}: {', '.join(pins)}")
        else:
            short_codes = ", ".join(pin[-3:] for pin in pins)
            lines.append(f"• {city}: {pins[0][:3]}0xx ({len(pins)} codes: {short_codes})")

    await message.reply_text("\n".join(lines))

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "PASTE_NEW_TOKEN_HERE":
        print("Set TELEGRAM_BOT_TOKEN environment variable or paste your new bot token.")
        return

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

    print("🤖 started")

    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False,
        )
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
