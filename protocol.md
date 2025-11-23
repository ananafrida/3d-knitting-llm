# Pattern JSON → Schema Population Protocol (README)

## Goals and Picture

We want a consistent procedure for turning a raw pattern JSON (from Ravelry or other sites) into a populated instance of our `schema.json`. This protocol should be followed by both humans and the LLM so that:

- Everyone interprets fields the same way.
- Ambiguous or missing information is handled in a predictable way.
- Our seed data is clean, coherent, and good enough to use as few-shot examples in prompts.

**Input:** a pattern JSON like the “Elegant Knit Crown” example (plus, if needed, the original webpage).
**Output:** one JSON object that conforms to `schema.json`, with as many fields filled as possible.

---

## General Labeling Rules

### Use only observable information
- Prefer fields in the pattern JSON (e.g., `name`, `description`, `category`, `full_text`, `suggested_yarn`, `needle_size`, `languages`, `attributes`, `techniques`, `shape`, `pattern_page`).
- If something is unclear in the JSON, you may open the original `pattern_page` URL and use what’s visibly on that page.

### No guessing beyond the evidence
- If you cannot reasonably infer something, set it to `null` (or `[]` for lists) rather than inventing it.
  Example: if we only know “Worsted (9 wpi) ?” and nothing else, brand and fiber stay `null`.

### Prefer normalized vocabularies where defined
- `shape_category` and `construction_method` must use the allowed enums in the schema.
- Don’t invent new labels unless the schema is explicitly extended.

### Record ambiguity using lists or raw strings
- If there are multiple possible labels, include all reasonable ones in the array (e.g., `shape_category: ["softie","organic"]`).
- Preserve raw text in `text.full_text`, `text.description`, and `materials.*` so we can revisit decisions later.

### If information is missing
- Use `null` for scalars or empty list `[]` for arrays.
- Do not put `"unknown"` unless the schema explicitly lists `"other"` or `"unknown"` as a valid category.

---

## Field-by-field protocol

### Basic identity

**title**
- Take from `pattern_json.name`
- If missing, put `null`

**url**
- Use `pattern_json.pattern_page` if present
- Otherwise, put `null`

**source**
- If the URL host contains `ravelry.com` → `"ravelry"`
- If it’s a personal blog domain → `"blog"`
- If it’s a publisher or book site → `"book"`
- Otherwise → `"other"`

**language**
- Use `pattern_json.languages` as a list of strings
- If empty/missing, use `[]`

**license**
- Only fill if the pattern page clearly states a license (e.g., “CC BY-NC-SA”, “free for personal use”, etc.)
- Otherwise `null`

**attribution**
- `designer`: from `pattern_json.designer` (or equivalent field)
- `publisher`: if a separate publisher is mentioned on the page (e.g., “Interweave Knits”, “Knitty”, “Ravelry Store Name”). If none, `null`
- `year`: year of first publication if clearly visible (e.g., 2015). If unclear, `null`

---

## Classification

### classification.shape_category (array)
Use a combination of:
- `pattern_json.shape` (if present)
- category text
- attributes and full_text (e.g. “blanket”, “sock”, “toy”, “square”, “sphere”, etc.)

Map into schema enums:
- Hats, crowns, sweaters, blankets that are mostly flat/surface-like → `"flat"`
- Toys, plushies, crowns, stuffed forms → `"softie"` or `"organic"` depending on form
- Explicit words like ball, sphere, round ornament → include `"sphere"`
- cube, box, block → `"cube"`
- cone, tree-shaped hat → `"cone"`
- Tubes like sock, leg warmer, sleeve → `"cylinder"`

If it’s clearly one type, you can use a single label; if it fits multiple, use multiple.
If you truly can’t decide, use `["other"]`.

### classification.construction_method (array)

Look at `pattern_json.techniques`, `attributes`, `full_text`, and `category` for keywords:

- Contains “in the round” → include `"in_the_round"`
- Mentions “worked flat”, “flat” and seaming → `"flat_seamed"`
- “short rows” → `"short_rows"`
- “increase”, “inc”, “kfb”, etc. → `"increases"`
- “decrease”, “dec”, “k2tog”, etc. → `"decreases"`
- “modular”, “mitered squares”, “joined modules” → `"modular"`
- “top-down“ / “top down” → `"top_down"`
- “bottom-up“ / “bottom up” → `"bottom_up"`
- Explicit grafting / Kitchener stitch → `"grafting"`
- “pick up stitches” → `"pick_up_stitches"`

Include every construction method that is clearly used in the pattern.

### classification.attributes
- Copy `pattern_json.attributes` verbatim (list of strings)
- If additional relevant labels appear on Ravelry (e.g. “chart”, “written-pattern”, “lace”), include them

---

## Materials

We always try to keep both a normalized view and the original text.

### materials.suggested_yarns
Use `pattern_json.suggested_yarn` list.
For each non-empty string:

- **name**: the yarn name if a specific yarn is given (e.g., `"Alize Superwash Comfort Socks"`).
  If only weight is given (“Worsted (9 wpi)”), put that in `name` and leave `brand` `null`.
- **brand**: if discoverable from the same text (e.g., “Rauma Finullgarn” → `name="Finullgarn"`, `brand="Rauma"`). If ambiguous, keep the whole string in `name` and `brand = null`.
- **weight_cyc**: map standard weight terms — `lace, fingering, sport, dk, worsted, aran, bulky, etc.` to Craft Yarn Council numbers `"0–7"` if clearly identified. Otherwise `null`.
- **fiber, colorway, yardage_per_skein, grams_per_skein**: only fill if explicitly stated. Otherwise `null`.

If the list includes empty strings, ignore them.

### materials.needles
From `pattern_json.needle_size` (or similar).

- Split on commas, semicolons, or “and” to get multiple entries.
- For each entry:
  - Extract US and mm sizes if possible: `US 7 (4.5 mm)` → `us_size = "US 7"`, `mm = 4.5`.
  - `type`: if text mentions circular, DPN, straight → set accordingly; else `null`.
  - `length_mm`: if a length like “16 in 40 cm” is present, convert to mm if clear; else `null`.

### materials.notions
Scan `full_text` (and any “Materials/Notions” section if available) for items like:
- stitch markers, tapestry needle, cable needle, safety eyes, stuffing, buttons, waste yarn, etc.

Collect them as a simple string list; keep fairly coarse-grained (don’t over-parse counts unless easy).

---

## Gauge

### gauge.stitches_per_10cm & gauge.rows_per_10cm

If the pattern states gauge over 4 in / 10 cm, convert:

- If gauge is:
  `"20 sts and 28 rows = 4 in / 10 cm in stockinette"`
  → set `stitches_per_10cm = 20`, `rows_per_10cm = 28`.

- If gauge is only given per inch, multiply by 4 and round reasonably.

- If no gauge is present → `null`.

### gauge.stitch_pattern
- If gauge is specified in stockinette / garter / ribbing → use `"stockinette"`, `"garter"`, `"rib"`.
- If given in a more complex pattern, use `"other"`.
- If gauge not stated → `null`.

---

## Sizes

### sizes.sizes_available
Take `pattern_json.sizes_available` as a single string and split into a list on commas or “and”.

Example:
`"Large (Adult/Teen), Small (Toddler/Child)"` →
`["Large (Adult/Teen)", "Small (Toddler/Child)"]`

### sizes.finished_dimensions
Copy any explicit final measurement text (e.g. “Hat circumference 20–22 in (51–56 cm)”).

If not present, `null`.

---

## Components and Instructions

For the seed set, we probably don’t want to overcomplicate components for every pattern, but we should have at least a couple fully annotated examples.

### When to create components

- If the pattern has natural sub-parts: head/body/ears, top/bottom, border vs center, squares in a modular blanket, etc.
- If it’s a simple, single-piece item (like a basic hat), you can have a single component called `"body"` or `"main piece"`.

### Each component

- **name**: human-readable (e.g., `"Crown body"`, `"Square module"`, `"Left ear"`)
- **role**:
  - `"core"` for main structural parts (e.g., blanket squares, hat body)
  - `"attachment"` for things sewn on (ears, handles, pom-poms)
  - `"detail"` for purely decorative components (embroidered face, duplicate-stitch letters)
- **order**: approximate execution order (1, 2, 3, …)
- **joins**: free-text remarks about how the piece is attached to others (“seamed to body”, “picked up from brim”, etc.)

### instructions.as_text
Copy the raw instructions for that component (e.g., all rows/rounds related to the crown body).

### instructions.steps
For the seed set, we can create a coarse segmentation rather than row-by-row if full detail is too heavy.

Example for the crown:
1. Cast on and brim ribbing
2. Work body of crown
3. Work decreases / points

For each step object:
- **index**: 1, 2, 3… in the order they appear
- **howto_summary**: 1-sentence description
- **row_or_round**: `"row"` or `"round"` if the step is clearly row-based vs round-based, else `null`
- **count**: number of rows/rounds or repeats if easy to identify; else `null`
- **technique_tags**: include relevant techniques (`short_rows`, `increases`, `decreases`, `in_the_round`, `modular`, etc.)
- **stitch_count_after**: fill only if the pattern clearly says “you now have X sts”; else `null`
- **chart_ref**: name/ID if step refers to a chart, else `null`

---

## Text, Downloads, Media, Provenance

### text.full_text
Use `pattern_json.full_text` (the main notes area from the page).

If not available, you can copy the main pattern description block from the HTML.

### text.description
Use `pattern_json.description` if available (shorter summary).

If absent, you can re-use the first paragraph of `full_text` or leave `null`.

### downloads.links
From `pattern_json.download_links`, only keep links that directly lead to a pattern file or external pattern instructions, e.g.:

- URLs ending in `.pdf`
- External pattern pages (off Ravelry) that contain the full instructions

Do not include navigation tabs like `/comments`, `/people`, `/threads`, `/report` in `downloads.links` (those are view navigation, not downloads).

If there are no such links, use `[]`.

### media.images
If available from the page or JSON, include the URLs of the main pattern photos.

**charts_available:**
- `true` if the page explicitly mentions charts or has chart images/downloads
- `false` if explicitly “no charts”
- `null` if not mentioned

### provenance
- **extracted_from**: file name of the original HTML file or pattern JSON identifier (e.g., `"1.html"` or `"pattern_1.json"`)
- **extraction_time**: if you have it, an ISO8601 timestamp string of when extraction was run; otherwise `null` for manual seed data
- **fields_confidence**: for the manual seed set, this can be omitted or set to `null`. Later, when the LLM fills data automatically, we can use probabilities.
