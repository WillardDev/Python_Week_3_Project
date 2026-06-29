import re
import csv
import json
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from tabulate import tabulate

JUMIA_URL = "https://www.jumia.co.ke/smartphones/"
NUM_PRODUCTS = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

EXCHANGE_RATE_URL = "https://open.er-api.com/v6/latest/{base}"

SOURCE_CURRENCY = "KES" 
TARGET_CURRENCY = "USD"

def clean_price(price_text):
    """Turn 'KSh 9,999' into 9999.0. Returns None if no digits found."""
    digits = re.sub(r"[^\d.]", "", price_text)
    return float(digits) if digits else None


def fetch_exchange_rate(base, target):
    """Fetch a fresh conversion rate. Returns None on any failure."""
    try:
        resp = requests.get(EXCHANGE_RATE_URL.format(base=base), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") == "success":
            return data["rates"].get(target)
        print(f"Currency API did not return success: {data}")
    except requests.exceptions.RequestException as e:
        print(f"Currency API connection error: {e}")
    return None

soup = None
try:
    response = requests.get(JUMIA_URL, headers=HEADERS, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    print(f"Status code: {response.status_code}")
    print(f"Page title: {soup.title.string if soup.title else 'N/A'}")
except requests.exceptions.RequestException as e:
    print(f"Connection error: {e}")

products = []

if soup is not None:
    cards = soup.find_all("a", class_="core")
    print(f"Found {len(cards)} product cards on the page")

    for card in cards[:NUM_PRODUCTS]:
        name_tag = card.find("div", class_="name")
        price_tag = card.find("div", class_="prc")

        if not name_tag or not price_tag:
            continue

        name = name_tag.get_text(strip=True)
        price_text = price_tag.get_text(strip=True)
        original_price_text = price_tag.get("data-oprc", "")

        price = clean_price(price_text)
        original_price = clean_price(original_price_text) if original_price_text else None

        link = card.get("href", "")
        if link.startswith("/"):
            link = "https://www.jumia.co.ke" + link

        if name and price is not None:
            products.append({
                "name": name,
                "price_kes": price,
                "original_price_kes": original_price,
                "link": link
            })

print(f"Successfully parsed {len(products)} products")

if not products:
    print(
        "No products parsed. Possible causes:\n"
        "  - Jumia changed their markup (see troubleshooting block at the bottom)\n"
        "  - The request was blocked (check the status code above)\n"
        "  - Network/connection issue\n"
    )

exchange_rate = fetch_exchange_rate(SOURCE_CURRENCY, TARGET_CURRENCY) if products else None

if exchange_rate is not None:
    print(f"1 {SOURCE_CURRENCY} = {exchange_rate} {TARGET_CURRENCY}")

    conversion_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    target_col = f"price_{TARGET_CURRENCY.lower()}"

    for p in products:
        p[target_col] = round(p["price_kes"] * exchange_rate, 2)
        p["converted_at"] = conversion_timestamp

    print(f"Converted {len(products)} prices from {SOURCE_CURRENCY} to {TARGET_CURRENCY}")
else:
    target_col = None
    print("Skipping conversion -- no exchange rate available.")

if products:
    df = pd.DataFrame(products)

    display_df = df.copy()
    display_df["name"] = display_df["name"].str.slice(0, 45) + "..."

    columns_to_show = ["name", "price_kes"] + ([target_col] if target_col in display_df.columns else [])
    print(tabulate(display_df[columns_to_show], headers="keys", tablefmt="grid", showindex=False))

    df.to_csv("jumia_smartphone_prices.csv", index=False)
    print(f"Saved {len(df)} rows to jumia_smartphone_prices.csv")

    with open("jumia_smartphone_prices.json", "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(products)} records to jumia_smartphone_prices.json")

    if target_col and target_col in df.columns:
        fig, ax1 = plt.subplots(figsize=(12, 6))

        short_names = [n[:20] + "..." if len(n) > 20 else n for n in df["name"]]
        x = range(len(df))

        ax1.bar(x, df["price_kes"], color="#1f77b4", alpha=0.7, label=f"Price ({SOURCE_CURRENCY})")
        ax1.set_ylabel(f"Price ({SOURCE_CURRENCY})", color="#1f77b4")
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(short_names, rotation=45, ha="right")

        ax2 = ax1.twinx()
        ax2.plot(x, df[target_col], color="#d62728", marker="o", label=f"Price ({TARGET_CURRENCY})")
        ax2.set_ylabel(f"Price ({TARGET_CURRENCY})", color="#d62728")

        plt.title(f"Jumia Smartphone Prices: {SOURCE_CURRENCY} vs {TARGET_CURRENCY}")
        fig.tight_layout()
        plt.savefig("price_comparison_chart.png", dpi=150)
        plt.show()

        print("Chart saved to price_comparison_chart.png")
    else:
        print("Skipping chart -- no converted prices available.")

    new_target = "EUR"
    new_rate = fetch_exchange_rate(SOURCE_CURRENCY, new_target)

    if new_rate is not None:
        new_col = f"price_{new_target.lower()}"
        df[new_col] = (df["price_kes"] * new_rate).round(2)
        print(f"Added {new_col} column using rate 1 {SOURCE_CURRENCY} = {new_rate} {new_target}")
        print(df[["name", "price_kes", new_col]].head())
    else:
        print(f"Could not fetch rate for {new_target}")
