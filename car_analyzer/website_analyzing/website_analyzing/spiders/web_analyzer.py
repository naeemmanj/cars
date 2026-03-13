import asyncio
import re
import random
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
import pandas as pd

DOMAINS_FILE = "domains.txt"
OUTPUT_FILE = "final_results.csv"
CONCURRENCY = 2

VIN_REGEX = re.compile(r'[A-HJ-NPR-Z0-9]{17}')

results = []

def detect_platform(html):

    text = html.lower()

    if "cdn.shopify.com" in text:
        return "Shopify"

    if "woocommerce" in text:
        return "WooCommerce"

    if "magento" in text:
        return "Magento"

    return "Unknown"

#Titles

def extract_titles(html):

    soup = BeautifulSoup(html, "html.parser")

    titles = []

    for tag in soup.find_all(["h1", "h2", "h3"]):

        t = tag.get_text(strip=True)

        if 10 < len(t) < 120:
            titles.append(t)

    return list(set(titles))[:5]


#VINs


def extract_vins(html):

    return list(set(VIN_REGEX.findall(html)))[:10]

#Inventory Pages

def find_inventory_pages(html, base_url):

    soup = BeautifulSoup(html, 'html.parser')

    links = []

    for a in soup.find_all('a', href=True):

        href = a['href'].lower()

        if any(x in href for x in ['inventory', 'cars', 'vehicles', 'used', 'trucks']):

            if href.startswith('http'):
                links.append(href)

            else:
                links.append(base_url.rstrip('/') + '/' + href.lstrip('/'))

    return list(set(links))

async def google_search(page, query):

    try:

        await asyncio.sleep(random.uniform(1.5, 3))

        url = f"https://www.google.com/search?q={query}"

        await page.goto(url, timeout=20000)

        return await page.content()

    except:

        return ""

def marketplace_detect(html):

    signals = [

        "autotrader",
        "cars.com",
        "carvana",
        "carfax",
        "edmunds",
        "kbb.com",
        "truecar",
        "cargurus",
        "bringatrailer",
        "copart",
        "manheim"

    ]

    html = html.lower()

    for s in signals:
        if s in html:
            return True

    return False

async def analyze_domain(context, domain):

    page = None

    try:

        page = await context.new_page()

        url = f"https://{domain}"

        try:
            await page.goto(url, timeout=25000)

        except PlaywrightTimeoutError:

            url = f"http://{domain}"
            await page.goto(url, timeout=25000)

        html = await page.content()

        platform = detect_platform(html)

        titles = extract_titles(html)

        inventory_pages = find_inventory_pages(html, url)

        vins_found = []

        for inv in inventory_pages[:3]:

            try:

                await page.goto(inv, timeout=20000)

                page_html = await page.content()

                vins_found.extend(extract_vins(page_html))

            except:
                continue

        vins_found = list(set(vins_found))

        #VIN Verification

        dropship_vin = False

        for vin in vins_found[:3]:

            g_html = await google_search(page, vin)

            if g_html and domain.lower() not in g_html.lower():
                dropship_vin = True
                break

        #Title Verification

        dropship_title = False
        for t in titles:

            g_html = await google_search(page, t)

            if g_html and marketplace_detect(g_html):
                dropship_title = True
                break

        if dropship_vin:

            classification = "Dropship / Shared Inventory"

        elif dropship_title:

            classification = "Dropship Likely"

        else:

            classification = "Original Dealer"

        print(domain, classification)

        results.append({

            "domain": domain,
            "platform": platform,
            "titles": titles,
            "sample_vins": vins_found[:5],
            "classification": classification,
            "error": ""

        })

    except Exception as e:

        err = str(e)

        if "ERR_NAME_NOT_RESOLVED" in err:
            reason = "DNS Not Found"

        elif "ERR_CERT" in err:
            reason = "SSL Certificate Error"

        elif "Timeout" in err:
            reason = "Timeout"

        else:
            reason = "Other Error"

        print(domain, reason)

        results.append({

            "domain": domain,
            "platform": "",
            "titles": [],
            "sample_vins": [],
            "classification": "",
            "error": reason

        })

    finally:

        if page:
            try:
                await page.close()
            except:
                pass


async def main():

    with open(DOMAINS_FILE) as f:
        domains = [d.strip() for d in f if d.strip()]

    async with async_playwright() as p:

        browser = await p.chromium.launch(

            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"]

        )

        context = await browser.new_context(

            ignore_https_errors=True,

            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

        )

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def task(domain):

            async with semaphore:
                await analyze_domain(context, domain)

        await asyncio.gather(*[task(d) for d in domains])

        await browser.close()

    df = pd.DataFrame(results)

    df.to_csv(OUTPUT_FILE, index=False)


asyncio.run(main())
