import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import pandas as pd

DOMAINS_FILE = "domains.txt"

results = []


def detect_platform(html):

    text = html.lower()

    if "cdn.shopify.com" in text or "shopify" in text:
        return "Shopify"

    if "woocommerce" in text:
        return "WooCommerce"

    if "magento" in text:
        return "Magento"

    return "Unknown"


def extract_product_titles(html):

    soup = BeautifulSoup(html, "html.parser")

    titles = []

    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)

        if len(text) > 10 and len(text) < 120:
            titles.append(text)

    return list(set(titles))[:5]


async def google_search(page, query):

    url = f"https://www.google.com/search?q={query}"

    await page.goto(url, timeout=20000)

    html = await page.content()

    return html.lower()


def detect_dropship(html):

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
    "manheim",
    "ebay motors",
    "google",
    "being",
    "firefox",
    "uc browser"
]

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
            await page.goto(url, timeout=20000)
        except:
            url = f"http://{domain}"
            await page.goto(url, timeout=20000)

        html = await page.content()

        platform = detect_platform(html)

        titles = extract_product_titles(html)

        dropship_found = False

        for title in titles:

            search_html = await google_search(page, title)

            if detect_dropship_from_google(search_html):
                dropship_found = True
                break

        if dropship_found:
            classification = "Dropshipping Likely"
        else:
            classification = "Possibly Original"

        print(domain, classification)

        results.append({
            "domain": domain,
            "platform": platform,
            "classification": classification,
            "error": ""
        })

    except Exception as e:

        reason = str(e)

        if "ERR_NAME_NOT_RESOLVED" in reason:
            reason = "DNS Not Found"

        elif "ERR_CERT" in reason:
            reason = "SSL Certificate Error"

        elif "Timeout" in reason:
            reason = "Timeout"

        elif "ERR_HTTP2_PROTOCOL_ERROR" in reason:
            reason = "Blocked by Server"

        else:
            reason = "Other Error"

        print(domain, reason)

        results.append({
            "domain": domain,
            "platform": "",
            "classification": "",
            "error": reason
        })

    finally:

        if page:
            await page.close()


async def main():

    with open(DOMAINS_FILE) as f:
        domains = [d.strip() for d in f if d.strip()]

    async with async_playwright() as p:

        browser = await p.chromium.launch(headless=True)

        context = await browser.new_context(ignore_https_errors=True)

        semaphore = asyncio.Semaphore(5)

        async def task(domain):
            async with semaphore:
                await analyze_domain(context, domain)

        await asyncio.gather(*[task(d) for d in domains])

        await browser.close()

    df = pd.DataFrame(results)

    df.to_csv("results.csv", index=False)


asyncio.run(main())