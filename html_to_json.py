import os
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from deep_translator import GoogleTranslator

# === CONFIG ===
HTML_DIR = "downloaded_patterns"
OUT_DIR = "json_patterns_full"
MASTER_JSON = "patterns_dataset.json"

def translate_to_english(text):
    try:
        # detect language automatically & translate to English
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception as e:
        print(f"[warn] Translation skipped ({e})")
        return text

def ensure_dir(p):
    if not os.path.exists(p):
        os.makedirs(p)

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

US_NEEDLES = {
    "0": 2.0, "1": 2.25, "2": 2.75, "3": 3.25, "4": 3.5,
    "5": 3.75, "6": 4.0, "7": 4.5, "8": 5.0, "9": 5.5,
    "10": 6.0, "10.5": 6.5, "11": 8.0, "13": 9.0, "15": 10.0
}

def normalize_needle(val):
    if not val:
        return ""
    val = val.lower()
    mm_match = re.findall(r"(\d+(\.\d+)?)\s*mm", val)
    us_match = re.findall(r"us\s*([\d\.]+)", val)
    mm_vals = [float(m[0]) for m in mm_match]
    us_vals = [m for m in us_match]
    results = []
    for mm in mm_vals:
        us = None
        for k,v in US_NEEDLES.items():
            if abs(v - mm) < 0.15:
                us = k
        if us:
            results.append(f"US {us} ({mm} mm)")
        else:
            results.append(f"{mm} mm")
    for us in us_vals:
        mm = US_NEEDLES.get(us)
        if mm:
            results.append(f"US {us} ({mm} mm)")
        else:
            results.append(f"US {us}")
    return ", ".join(results) if results else val

TECHNIQUES = [
    "short rows", "increases", "decreases",
    "worked flat", "worked in the round", "top-down", "bottom-up",
    "modular", "seamed", "pick up stitches", "grafting",
]

SHAPE_RULES = {
    "sphere": ["ball", "round", "sphere", "egg"],
    "cube": ["cube", "box", "square plush", "block"],
    "cone": ["cone", "tree", "hat cone"],
    "pyramid": ["pyramid", "tetra"],
    "cylinder": ["tube", "sock", "sleeve", "leg warmer"],
    "softie": ["toy", "amigurumi", "softie", "plush"],
}

def detect_shape(text):
    text = text.lower()
    for shape, keys in SHAPE_RULES.items():
        if any(k in text for k in keys):
            return shape
    return "unknown"

def extract_download_links(soup):
    urls = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(x in href.lower() for x in [".pdf", "download", "pattern"]):
            if "ravelry" in href or href.startswith("http"):
                urls.append(href)
    return list(set(urls))

def parse_html(filepath):
    soup = BeautifulSoup(open(filepath, encoding="utf-8", errors="ignore"), "html.parser")
    result = {}

    # Add page URL from canonical or flag/report link
    report = soup.find("a", href=re.compile(r"/patterns/library/[^/]+/report"))
    if report:
        page_link = report["href"].replace("/report", "")
        result["pattern_page"] = urljoin("https://www.ravelry.com", page_link)

    # JSON-LD structured data
    script = soup.find("script", {"type": "application/ld+json"})
    if script:
        try:
            j = json.loads(script.string)
            result["name"] = clean(j.get("name"))
            result["description"] = clean(j.get("description"))
            result["designer"] = clean(j.get("brand", {}).get("name", ""))
        except:
            pass

    fields = soup.select("div.field.core_item_content__field, div.core_item_content__field--languages")
    yarns = []

    for f in fields:
        lab = f.find("label", class_="core_item_content__label")
        val = f.find("div", class_="value")
        if not lab or not val:
            continue
        key = clean(lab.text).lower()
        v = clean(val.text)
        if "craft" in key:
            result["craft"] = v
        if "category" in key:
            result["category"] = v
        if "needle" in key:
            result["needle_size"] = normalize_needle(v)
        if "yarn" in key:
            yarns.append(v)
        if "sizes available" in key:
            result["sizes_available"] = v
        if "languages" in key:
            result["languages"] = [clean(lang.text) for lang in val.find_all("span")]

    if yarns:
        result["suggested_yarn"] = list(set(yarns))

    # Attributes (the square tags)
    attrs = []
    tag_list = soup.select("ul.tag_set li.tag a")
    for tag in tag_list:
        attrs.append(clean(tag.text))
    if attrs:
        result["attributes"] = attrs

    # Notes text (main pattern notes/description)
    notes_block = soup.find("div", class_="notes")
    if notes_block:
        raw_text = clean(notes_block.get_text(separator=" "))
        translated_text = translate_to_english(raw_text)
        result["full_text"] = translated_text

    # Detect shape and techniques
    text = (result.get("description", "") + " " + result.get("full_text", "")).lower()
    result["techniques"] = sorted({t for t in TECHNIQUES if t in text})
    result["shape"] = detect_shape(text)
    result["download_links"] = extract_download_links(soup)

    if "name" not in result and soup.title:
        result["name"] = clean(soup.title.text)

    return result

def main():
    ensure_dir(OUT_DIR)
    all_patterns = []
    html_files = sorted(f for f in os.listdir(HTML_DIR) if f.endswith(".html"))

    print(f"🔍 Found {len(html_files)} HTML files to parse.")

    for i, file in enumerate(html_files, start=1):
        path = os.path.join(HTML_DIR, file)
        data = parse_html(path)

        # Save individual JSON
        out_path = os.path.join(OUT_DIR, file.replace(".html", ".json"))
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        all_patterns.append(data)
        print(f"[{i}/{len(html_files)}] ✅ Parsed {file}")

    # Save master dataset
    with open(MASTER_JSON, "w", encoding="utf-8") as out:
        json.dump(all_patterns, out, indent=2, ensure_ascii=False)

    print(f"\n🎉 All patterns converted and merged into {MASTER_JSON}")

if __name__ == "__main__":
    main()
