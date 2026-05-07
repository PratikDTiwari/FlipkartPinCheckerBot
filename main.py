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
    "Agartala": ["799001", "799007"],
    "Agra": ["282001", "282010"],
    "Ahmedabad": ["380001", "380054"],
    "Aizawl": ["796001", "796007"],
    "Aligarh": ["202001"],
    "Ambernath": ["421501", "421503"],
    "Amritsar": ["143001", "143010"],
    "Ara": ["802301", "802302"],
    "Asansol": ["713301"],
    "Aurangabad": ["431001", "431005", "431010"],
    "Balasore": ["756001", "756003"],
    "Bathinda": ["151001", "151005"],
    "Begusarai": ["851101", "851128"],
    "Bengaluru": ["560001", "560100"],
    "Bhilai": ["490001", "490023"],
    "Bhopal": ["462001", "462047"],
    "Bhubaneswar": ["751001", "751031"],
    "Bikaner": ["334001", "334002", "334003", "334006", "334022", "334023"],
    "Bilaspur CG": ["495001", "495003"],
    "Bokaro": ["827001", "827004"],
    "Chandigarh": ["160001", "160036"],
    "Chennai": ["600001", "600119"],
    "Coimbatore": ["641001", "641062"],
    "Cuttack": ["753001", "753014"],
    "Darbhanga": ["846001", "846003"],
    "Delhi": ["110001", "110008", "110009", "110010", "110053", "110097"],
    "Deoghar": ["814112", "814113"],
    "Dhanbad": ["826001", "826004"],
    "Dibrugarh": ["786001", "786003"],
    "Dimapur": ["797112", "797115"],
    "Durg": ["491001", "491003"],
    "Durgapur": ["713201", "713216"],
    "Faridabad": ["121001", "121007"],
    "Gangtok": ["737101", "737103"],
    "Gaya": ["823001", "823003"],
    "Gajsinghpur": ["335024"],
    "Ghaziabad": ["201013"],
    "Gurgaon": ["122001", "122018"],
    "Guwahati": ["781001", "781007"],
    "Haldia": ["721601", "721604"],
    "Hanumangarh": ["335512", "335513"],
    "Hazaribagh": ["825301", "825303"],
    "Hisar": ["125001", "125005"],
    "Howrah": ["711101", "711413"],
    "Hyderabad": ["500001", "500097"],
    "Imphal": ["795001", "795004"],
    "Indore": ["452001", "453331", "453551"],
    "Itanagar": ["791111", "791113"],
    "Jabalpur": ["482001", "482011"],
    "Jaipur": ["302001", "302020", "302029", "302040", "303012"],
    "Jagraon": ["142026"],
    "Jalandhar": ["144001", "144014"],
    "Jalpaiguri": ["735101"],
    "Jammu": ["180001", "180019"],
    "Jamshedpur": ["831001", "831005"],
    "Jodhpur": ["342001", "342014"],
    "Jorhat": ["785001", "785003"],
    "Karanpur": ["322243"],
    "Kanpur": ["208001", "208027"],
    "Karnal": ["132001"],
    "Kharagpur": ["721301", "721306"],
    "Kochi": ["682001", "682040"],
    "Kohima": ["797001", "797003"],
    "Kolkata": ["700001"],
    "Korba": ["495677", "495678"],
    "Kota": ["324001", "324010"],
    "Kozhikode": ["673001"],
    "Lucknow": ["226001", "226030"],
    "Ludhiana": ["141001", "141002", "141003"],
    "Malda": ["732101", "732103"],
    "Mangaluru": ["575001", "575010"],
    "Meerut": ["250001", "250005"],
    "Mohali": ["160055", "160062"],
    "Mumbai": ["400001", "400020", "400067", "400095"],
    "Muzaffarpur": ["842001", "842003"],
    "Mysuru": ["570001", "570012"],
    "Nagpur": ["440001", "440037"],
    "Nashik": ["422001", "422013"],
    "Navi Mumbai": ["400703", "410209"],
    "Panchkula": ["134112", "134116", "160101"],
    "Panipat": ["132103", "132105", "132106", "132108"],
    "Patiala": ["147001", "147007"],
    "Patna": ["800001", "800020", "801503"],
    "Prayagraj": ["211001", "211018"],
    "Pune": ["411001", "411036", "412207"],
    "Puri": ["752001", "752003"],
    "Purnia": ["854301", "854303"],
    "Raiganj": ["733130", "733134"],
    "Raisinghnagar": ["335051"],
    "Raipur": ["492001", "492010"],
    "Ranchi": ["834001", "834006"],
    "Rohtak": ["124001", "124003"],
    "Rourkela": ["769001", "769012"],
    "Salem": ["636001", "636016"],
    "Sambalpur": ["768001", "768006"],
    "Shillong": ["793001", "793004"],
    "Silchar": ["788001", "788003"],
    "Siliguri": ["734001", "734013"],
    "Sriganganagar": ["335001"],
    "Surat": ["395001", "395007"],
    "Suratgarh": ["335804"],
    "Thane": ["400601", "400612"],
    "Thiruvananthapuram": ["695001", "695036"],
    "Udaipur": ["313001", "313011"],
    "Ujjain": ["456001", "456010"],
    "Ulhasnagar": ["421001", "421005"],
    "Vadodara": ["390001", "390023"],
    "Varanasi": ["221001", "221012"],
    "Vijaynagar": ["335704"],
    "Vijayawada": ["520001", "520010"],
    "Visakhapatnam": ["530001", "530016"],
    "Warangal": ["506001", "506013"],
    "Pune": [ "411001","411002","411003","411004","411005","411006","411007","411008","411009","411010",
    "411011","411012","411013","411014","411015","411016","411017","411018","411019","411020",
    "411021","411022","411023","411024","411025","411026","411027","411028","411029","411030",
    "411031","411032","411033","411034","411035","411036","411037","411038","411039","411040",
    "411041","411042","411043","411044","411045","411046","411047","411048","411052","411057",
    "412105","412114","412207","412208","412307","412308"],
    "Nagpur": ["440001","440002","440003","440004","440005","440006","440007","440008","440009","440010",
    "440011","440012","440013","440014","440015","440016","440017","440018","440019","440020",
    "440021","440022","440023","440024","440025","440026","440027","440028","440029","440030",
    "440032","440033","440034","440035","440036","440037"]
    
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
