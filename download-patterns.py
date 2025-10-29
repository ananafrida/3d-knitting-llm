#!/usr/bin/env python3
"""

Pipeline:
- Read categories from category_formatted.xlsx column Formatted_Category
- For each category, build search URL:
    https://www.ravelry.com/patterns/search#craft=knitting&availability=free&pc={placeholder}&view=captioned_thumbs
- Use Selenium to login to Ravelry, visit search page, scroll and collect /patterns/library/ links
- Transfer cookies to requests.Session and download each pattern HTML to ./html_patterns/{N}.html
- Parse Title/Craft/Category and save rows to patterns_data.xlsx

Requires: selenium, webdriver-manager, pandas, requests, beautifulsoup4, openpyxl, python-dotenv
"""
import os
import time
import re
from urllib.parse import quote_plus

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --------------------------
# CONFIG / CONSTANTS
# --------------------------
load_dotenv()  # load .env if present

EXCEL_IN = "category_formatted.xlsx"
CATEGORY_COLUMN = "Formatted_Category"
SEARCH_URL_TEMPLATE = "https://www.ravelry.com/patterns/search#craft=knitting&availability=free&pc={placeholder}&view=captioned_thumbs"

HTML_OUT_DIR = "downloaded_patterns"
EXCEL_OUT = "patterns_data.xlsx"

# Selenium / crawling params
MAX_SCROLLS_PER_CATEGORY = 25
SCROLL_PAUSE_SEC = 1.2
REQUEST_PAUSE_SEC = 1.0
SELENIUM_WAIT_SEC = 20
TIMEOUT_SEC = 30

# Auth (set in env or .env)
RAVELRY_USER = os.getenv("RAVELRY_USER")
RAVELRY_PASS = os.getenv("RAVELRY_PASS")
SHOW_BROWSER = os.getenv("SHOW_BROWSER", "false").lower() in ("1", "true", "yes")

if not RAVELRY_USER or not RAVELRY_PASS:
    raise RuntimeError("RAVELRY_USER and RAVELRY_PASS must be set in environment or .env file.")

# --------------------------
# Utilities
# --------------------------
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def init_driver(headless=True):
    chrome_options = Options()
    if headless:
        # "new" headless mode if supported
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1200,2000")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    # optional: avoid images for speed (can be added)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(TIMEOUT_SEC)
    return driver

def login_ravelry(driver, username, password, wait_sec=SELENIUM_WAIT_SEC):
    driver.get("https://www.ravelry.com/account/login")

    # Optional: Close cookie consent if present
    try:
        cookie_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Accept')]"))
        )
        cookie_button.click()
        print("[login] Closed cookie pop-up.")
    except:
        pass  # no cookie popup

    # Wait for login fields
    WebDriverWait(driver, wait_sec).until(EC.presence_of_element_located((By.ID, "user_login")))
    driver.find_element(By.ID, "user_login").send_keys(username)
    driver.find_element(By.ID, "user_password").send_keys(password)

    # Click "Log In" button (new selector)
    login_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Log In') and @type='submit']")
    login_btn.click()
    time.sleep(2)

    # Validate login success
    if "/account/login" in driver.current_url:
        print("[login] Still on login page — login may have failed or requires 2FA.")
        return False

    print("✅ Login successful!")
    return True


def collect_pattern_links_from_search(driver, url, max_scrolls=15, pause=1.2, max_links=None):
    """
    Load the JS-driven Ravelry search page and scroll to collect pattern links.
    """
    links = []
    try:
        driver.get(url)
    except WebDriverException as e:
        print(f"[collect] Page load failed for {url}: {e}")
        return links

    # wait for search tiles (or for a "no results" indicator)
    try:
        WebDriverWait(driver, SELENIUM_WAIT_SEC).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/patterns/library/']"))
        )
    except TimeoutException:
        # No patterns loaded (maybe zero results or requires extra waiting)
        # return empty list
        return links

    last_height = driver.execute_script("return document.body.scrollHeight")
    stagnant = 0
    for i in range(max_scrolls):
        # collect hrefs via JavaScript to avoid stale WebElement references
        try:
            hrefs = driver.execute_script(
                "return Array.from(document.querySelectorAll(\"a[href*='/patterns/library/']\")).map(a => a.href);"
            )
        except Exception:
            hrefs = []

        for href in hrefs:
            if href and "/patterns/library/" in href and href not in links:
                links.append(href)
        if max_links and len(links) >= max_links:
            break

        # scroll
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            stagnant += 1
        else:
            stagnant = 0
            last_height = new_height
        if stagnant >= 2:
            break

    return links

def selenium_cookies_to_requests_session(driver):
    """
    Copy cookies from Selenium driver to a requests.Session() so we can download HTML with same auth.
    """
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    for c in driver.get_cookies():
        cookie = {k: c[k] for k in ("name", "value") if k in c}
        s.cookies.set(cookie["name"], cookie["value"], domain=c.get("domain", None), path=c.get("path", "/"))
    return s

def download_html(session, url, out_path):
    try:
        resp = session.get(url, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"[download] Failed {url}: {e}")
        return False

def parse_pattern_html(html_text):
    """
    Parse Title, Craft, Category from Ravelry pattern HTML
    """
    soup = BeautifulSoup(html_text, "html.parser")
    # Title
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # clean common "Ravelry: X pattern by Y"
        title = re.sub(r"^Ravelry:\s*", "", title)
    h1 = soup.find("h1")
    if (not title or title == "") and h1:
        title = h1.get_text(strip=True)

    craft, category = "", ""
    field_blocks = soup.find_all("div", class_="field core_item_content__field")
    for fb in field_blocks:
        lab = fb.find("label", class_="core_item_content__label")
        val = fb.find("div", class_="value")
        if not lab or not val:
            continue
        lab_text = lab.get_text(strip=True).lower()
        if lab_text == "craft":
            craft = val.get_text(strip=True)
        elif lab_text == "category":
            spans = val.find_all("span")
            if spans:
                category = " → ".join([s.get_text(strip=True) for s in spans if s.get_text(strip=True)])
            else:
                category = val.get_text(strip=True)

    return title, craft, category

# --------------------------
# Main
# --------------------------
def main():
    ensure_dir(HTML_OUT_DIR)

    # Read categories Excel
    if not os.path.exists(EXCEL_IN):
        raise FileNotFoundError(f"{EXCEL_IN} not found in current directory.")
    df_cats = pd.read_excel(EXCEL_IN)
    if CATEGORY_COLUMN not in df_cats.columns:
        raise ValueError(f"Column '{CATEGORY_COLUMN}' not found in {EXCEL_IN}")
    categories = [str(x).strip() for x in df_cats[CATEGORY_COLUMN].dropna().tolist() if str(x).strip()]
    categories = list(set(categories))
    print(categories)
    if not categories:
        print("[main] No categories found in Excel.")
        return

    # Init webdriver
    driver = init_driver(headless=not SHOW_BROWSER)

    try:
        # Login
        ok = login_ravelry(driver, RAVELRY_USER, RAVELRY_PASS)
        if not ok:
            print("[main] Login failed. Exiting.")
            return

        # Prepare requests session with Selenium cookies
        session = selenium_cookies_to_requests_session(driver)

        rows = []
        idx = 1

        for cat in categories:
            encoded = quote_plus(cat)
            search_url = SEARCH_URL_TEMPLATE.format(placeholder=encoded)
            print(f"\n[main] Processing category '{cat}' -> {search_url}")

            links = collect_pattern_links_from_search(driver, search_url, max_scrolls=MAX_SCROLLS_PER_CATEGORY, pause=SCROLL_PAUSE_SEC)
            print(f"[main] Found {len(links)} pattern links for category '{cat}'")

            for url in links:
                html_name = f"{idx}.html"
                out_path = os.path.join(HTML_OUT_DIR, html_name)
                success = download_html(session, url, out_path)
                if not success:
                    rows.append({
                        "Pattern_ID": idx,
                        "HTML_File": html_name,
                        "URL": url,
                        "Title": "",
                        "Craft": "",
                        "Category": "",
                        "Source_Category": cat,
                        "Source_Search_URL": search_url
                    })
                    idx += 1
                    time.sleep(REQUEST_PAUSE_SEC)
                    continue

                # parse saved HTML
                try:
                    with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                        html_text = f.read()
                    title, craft, category = parse_pattern_html(html_text)
                except Exception as e:
                    print(f"[main] Parse error for {out_path}: {e}")
                    title, craft, category = "", "", ""

                rows.append({
                    "Pattern_ID": idx,
                    "HTML_File": html_name,
                    "URL": url,
                    "Title": title,
                    "Craft": craft,
                    "Category": category,
                    "Source_Category": cat,
                    "Source_Search_URL": search_url
                })
                idx += 1
                time.sleep(REQUEST_PAUSE_SEC)

        # Save results to Excel
        out_df = pd.DataFrame(rows, columns=[
            "Pattern_ID",
            "HTML_File",
            "URL",
            "Title",
            "Craft",
            "Category",
            "Source_Category",
            "Source_Search_URL"
        ])
        out_df.to_excel(EXCEL_OUT, index=False)
        print(f"\n[main] Saved {len(out_df)} rows to {EXCEL_OUT}")
        print(f"[main] HTML files saved under: {HTML_OUT_DIR}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
