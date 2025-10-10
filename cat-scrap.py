import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# --- CONFIG ---
API_KEY = "a951041ff4365c6f9fb1b8f084520aca152366bdfacdd1a42742e0499dde3e45"  # replace with your SerpAPI key
SEARCH_KEYWORDS = [
    "site:ravelry.com knitting pattern sphere",
    "site:ravelry.com knitting pattern ball",
    "site:ravelry.com knitting pattern cone",
    "site:ravelry.com knitting pattern cube",
    "site:ravelry.com knitting pattern pyramid",
    "site:ravelry.com amigurumi knit pattern",
    "site:ravelry.com knitted toy pattern",
    "site:ravelry.com 3D knitting pattern",
    "site:ravelry.com pattern worked in the round",
    "site:ravelry.com modular knitting pattern"
]

def google_search(query):
    """Perform a Google search using SerpAPI."""
    url = "https://serpapi.com/search"
    params = {
        "engine": "google",
        "q": query,
        "num": "10",
        "api_key": API_KEY
    }
    r = requests.get(url, params=params)
    data = r.json()
    links = []
    for result in data.get("organic_results", []):
        link = result.get("link")
        if link and "ravelry.com/patterns" in link:
            links.append(link)
    return links

def scrape_ravelry_category(url):
    """Scrape a Ravelry pattern page to extract 'Craft' and 'Category' information."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Find all field blocks (each field has a label and value)
        fields = soup.find_all("div", class_="field core_item_content__field")

        craft, category = None, None

        for field in fields:
            label = field.find("label", class_="core_item_content__label")
            value_div = field.find("div", class_="value")

            if not label or not value_div:
                continue

            label_text = label.get_text(strip=True)
            if label_text == "Craft":
                craft = value_div.get_text(strip=True)
            elif label_text == "Category":
                # Extract nested categories like “Softies → Other”
                category_links = value_div.find_all("span")
                if category_links:
                    category = " → ".join([c.get_text(strip=True) for c in category_links])
                else:
                    category = value_div.get_text(strip=True)

        # Combine or return both
        if not craft and not category:
            return "N/A"
        elif craft and category:
            return f"{craft} / {category}"
        else:
            return craft or category

    except Exception as e:
        return f"Error: {e}"


def main():
    all_data = []

    for keyword in SEARCH_KEYWORDS:
        print(f"\n🔍 Searching for: {keyword}")
        links = google_search(keyword)
        print(f"  Found {len(links)} links")

        for link in links:
            print(f"   Scraping: {link}")
            category = scrape_ravelry_category(link)
            all_data.append({
                "Search Keyword": keyword,
                "URL": link,
                "Category": category
            })
            time.sleep(2)  # be polite

    # Save to Excel
    df = pd.DataFrame(all_data)
    df.to_excel("ravelry_search_results.xlsx", index=False)
    print("\n✅ Saved results to ravelry_search_results.xlsx")

if __name__ == "__main__":
    main()
