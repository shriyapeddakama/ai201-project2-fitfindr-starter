# FitFindr 🛍️

FitFindr is a tool-using agent that helps you shop secondhand. You describe what
you're looking for in plain English; the agent finds a matching listing, styles it
against your wardrobe, and writes a shareable "fit card" caption — orchestrating
three tools through a conditional planning loop with shared session state.

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file in the project root (free key at
[console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the web app:

```bash
python app.py
```

Open the URL printed in your terminal (usually http://localhost:7860, but **check
the terminal output** — the port can differ). On Windows, if emoji print oddly in a
terminal, prefix with `set PYTHONIOENCODING=utf-8 &&`.

Run the agent from the CLI (happy path + no-results path):

```bash
python agent.py
```

Run the tests:

```bash
pytest tests/
```

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # The 3 tools: search_listings, suggest_outfit, create_fit_card
├── agent.py                   # run_agent() planning loop + query parsing + session state
├── app.py                     # Gradio UI — handle_query() maps the session to 3 panels
├── tests/test_tools.py        # Pytest coverage incl. one test per failure mode
├── planning.md                # Spec written before implementation
└── README.md
```

---

## Tool Inventory

All signatures below match the actual functions in [`tools.py`](tools.py).

### 1. `search_listings(description, size, max_price) -> list[dict]`

- **Purpose:** Search the 40-item mock listings dataset for items matching the
  user's keywords, optional size, and optional price ceiling. Deterministic — no LLM.
- **Inputs:**
  - `description` (`str`) — free-text keywords, e.g. `"vintage graphic tee"`. Required.
  - `size` (`str | None`, default `None`) — size filter; case-insensitive substring
    match (`"m"` matches `"S/M"`, `"8"` matches `"US 8"`). `None` skips size filtering.
  - `max_price` (`float | None`, default `None`) — inclusive price ceiling in dollars.
    `None` skips price filtering.
- **Output:** `list[dict]` — full listing dicts sorted by keyword-relevance score
  (best first), tie-broken by lowest price. Each dict has: `id`, `title`,
  `description`, `category`, `style_tags` (list), `size`, `condition`, `price`
  (float), `colors` (list), `brand` (str or `None`), `platform`. Returns `[]` when
  nothing matches — **never raises**.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

- **Purpose:** Given a listing and the user's wardrobe, use the LLM to propose 1–2
  complete outfits built around the item, naming real wardrobe pieces. Falls back to
  general styling advice when the wardrobe is empty.
- **Inputs:**
  - `new_item` (`dict`) — a single listing dict (typically the top search result).
  - `wardrobe` (`dict`) — `{"items": [...]}`, where each item has `id`, `name`,
    `category`, `colors`, `style_tags`, optional `notes`. May have an empty `items` list.
- **Output:** `str` — a non-empty styling suggestion. With wardrobe items, it names
  specific pieces; with an empty wardrobe, it gives general advice. Never returns `""`.

### 3. `create_fit_card(outfit, new_item) -> str`

- **Purpose:** Turn the outfit + item into a short, shareable social-media caption
  (OOTD style). Uses high LLM temperature so output varies across runs.
- **Inputs:**
  - `outfit` (`str`) — the suggestion string from `suggest_outfit()`. Required, non-empty.
  - `new_item` (`dict`) — the listing dict; its `title`, `price`, and `platform` are
    woven into the caption once each.
- **Output:** `str` — a 2–4 sentence caption with a few hashtags/emoji. Returns a
  descriptive message string (not an exception) if `outfit` is empty/whitespace.

Helper: `agent.run_agent(query: str, wardrobe: dict) -> dict` orchestrates the three
tools and returns the completed session dict.

---

## How the Planning Loop Works

The loop lives in [`run_agent()`](agent.py) and is a linear pipeline with **conditional
early-exit branches** — it is *not* a fixed "call all three tools no matter what" chain.

1. **Initialize** a fresh `session` dict (single source of truth).
2. **Parse** the raw query with `_parse_query()` (regex) into `description`, `size`,
   `max_price`, stored in `session["parsed"]`.
   - `max_price`: a number following `under`/`below`/`less than`/`<=`/`$`.
   - `size`: an explicit `size <token>` phrase, or an unambiguous standalone token
     (`XS`/`XL`/`XXS`/`XXL`). Bare single letters are intentionally *not* auto-detected
     (see Spec Reflection).
   - `description`: the query with the matched size/price spans removed.
3. **Branch point — `search_listings(...)`.** This is where the loop reacts to results:
   - **If `search_results == []`** → set `session["error"]` to a specific, actionable
     message and **`return` immediately**. `suggest_outfit` and `create_fit_card` are
     never called; `outfit_suggestion` and `fit_card` stay `None`.
   - **Else** → set `session["selected_item"] = search_results[0]` and continue.
4. **`suggest_outfit(selected_item, wardrobe)`** → stored in `outfit_suggestion`. The
   tool internally branches on whether the wardrobe has items (specific outfits vs.
   general advice), so the loop always receives a usable non-empty string.
5. **`create_fit_card(outfit_suggestion, selected_item)`** → stored in `fit_card`.
6. **Return** the session.

The loop knows it is **done** when either `fit_card` is set (success) or `error` is set
(early exit). Callers check `session["error"]` first.

---

## State Management

A single `session` dict, created by `_new_session()` in [`agent.py`](agent.py), is the
one source of truth for an interaction. Each tool writes its output into a named field;
the next tool reads from that field — the user never re-enters anything mid-flow.

| Field | Type | Written by | Read by |
|-------|------|-----------|---------|
| `query` | str | caller | parse step |
| `parsed` | dict | parse step | `search_listings` args |
| `search_results` | list[dict] | `search_listings` | empty-check; source of `selected_item` |
| `selected_item` | dict / None | loop (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | caller | `suggest_outfit` |
| `outfit_suggestion` | str / None | `suggest_outfit` | `create_fit_card` |
| `fit_card` | str / None | `create_fit_card` | final return / UI |
| `error` | str / None | loop on early exit | caller checks first; UI panel 1 |

**Flow:** `search_listings` returns a list → loop stores it and copies `[0]` into
`selected_item` → `suggest_outfit(selected_item, wardrobe)` returns a string into
`outfit_suggestion` → `create_fit_card(outfit_suggestion, selected_item)` returns into
`fit_card`. The item found in step 3 reaches both later tools with no re-entry.

**Verified by object identity** (not just equality): in testing I wrapped the tools to
capture their arguments and confirmed `session["selected_item"] is` the exact object
passed into both `suggest_outfit` and `create_fit_card`, and `session["outfit_suggestion"]
is` the exact string passed into `create_fit_card`. State genuinely flows; nothing is
re-derived or hardcoded between steps.

---

## Error Handling Strategy (per tool)

Every tool owns its failure mode and degrades gracefully — no silent failures, no crashes.

**`search_listings` — no matches.** Returns `[]` (never raises). The planning loop
detects the empty list, sets a specific `session["error"]`, and stops before any styling.

> **Concrete example from testing.** Query `"designer ballgown size XXS under $5"`:
> the direct call returned `[]`, and the full agent returned:
> *"No listings matched 'designer ballgown' in size XXS, under $5. Try removing the
> size filter, raising your budget, or using broader keywords (e.g. 'graphic tee'
> instead of a specific print)."* — naming what failed **and** what to try. A spy
> confirmed `suggest_outfit`/`create_fit_card` were called **0 times** and `fit_card`
> stayed `None`.

**`suggest_outfit` — empty wardrobe.** Detects `wardrobe["items"] == []` and switches to
a general-styling-advice prompt instead of inventing pieces. Any LLM/API error is caught
and falls back to a deterministic string built from the item's own attributes.

> **Concrete example from testing.** `suggest_outfit(<Y2K Baby Tee>, get_empty_wardrobe())`
> returned: *"This graphic tee is perfect for a laid-back, grunge-inspired look… it would
> pair well with distressed denim jeans or a flowy skirt in neutral colors like blue,
> black, or gray…"* — a useful non-empty string, no exception.

**`create_fit_card` — empty/incomplete outfit.** Guards an empty/whitespace `outfit` at
the top and returns a descriptive message; LLM/API errors fall back to a template caption
from the item fields.

> **Concrete example from testing.** `create_fit_card("", <item>)` returned:
> *"I need an outfit suggestion before I can write a fit card. Try searching again so I
> can style a specific piece."* — a message string, not a Python exception.

**UI layer.** `handle_query()` guards empty queries and, when `session["error"]` is set,
shows the message in panel 1 and leaves the outfit/fit-card panels blank.

---

## Spec Reflection

**One way the spec helped.** Writing the Planning Loop section of `planning.md` as
explicit branches ("if `search_results == []`, set error and return *before* calling
`suggest_outfit`") meant the implementation was almost a transcription. The agent
diagram's labeled error branch made it obvious that the empty-results path must
terminate early, so I never accidentally wrote a fixed three-tool chain — the
conditional was designed in from the start.

**One way implementation diverged.** My spec said the parser would also detect a
"standalone size token (XS|S|M|L|XL|XXL)." In practice, bare single letters matched far
too eagerly — the walkthrough query *"…What's out there…"* parsed `size="S"` because the
apostrophe in "What's" acts as a word boundary, producing a false size filter. I overrode
the spec and restricted standalone detection to the unambiguous multi-letter tokens
(`XS`/`XL`/`XXS`/`XXL`); single-letter sizes now require explicit `size M` phrasing, which
every example query already uses. This made parsing correct without losing any real
functionality.

---

## AI Usage

**Instance 1 — `search_listings` implementation.** I gave Claude the **Tool 1** block
from `planning.md` (inputs, the full list of return fields, and the "returns `[]`, never
raises" failure mode) plus the `load_listings()` docstring. It produced a working filter +
keyword-scoring function. **What I changed:** its first version scored every field
equally; I revised it to weight `title`/`style_tags` hits higher than body/color/category
hits so a query like `"graphic tee"` surfaces an actual graphic tee at the top, and I
added a stopword list so filler words ("looking", "for", "the") don't inflate scores.

**Instance 2 — `run_agent` planning loop.** I gave Claude the **Planning Loop**, **State
Management**, and **Architecture** (ASCII diagram) sections, plus the `_new_session()`
field list and the tool signatures. It generated the conditional pipeline. **What I
overrode:** I reviewed it specifically against the diagram's error branch and confirmed
the empty-`search_results` case returns *before* the styling tools; I also tightened the
error message to name the active filters ("in size XXS, under $5") rather than a generic
"no results," and I replaced its over-eager single-letter size parsing as described in
Spec Reflection. I verified the result by spying on tool calls to prove state flows by
object identity and that styling tools never run on the no-results path.

---

## The Mock Listings Dataset

`data/listings.json` contains 40 mock secondhand listings across categories (tops,
bottoms, outerwear, shoes, accessories) and styles (vintage, y2k, grunge, cottagecore,
streetwear, and more). Each listing has: `id`, `title`, `description`, `category`,
`style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

`data/wardrobe_schema.json` defines the wardrobe format and includes `example_wardrobe`
(10 items) and `empty_wardrobe` (new-user template).

---

## Demo Video

A 3–5 minute walkthrough is included with the submission. It shows:

1. **A complete multi-step interaction** — query *"vintage graphic tee under $30"* with
   the example wardrobe, running all three tools from query → listing → outfit → fit card.
2. **Narration of each step** — which tool is called and why (search → select top result
   → suggest outfit → create fit card).
3. **State passing between tools** — the item found by `search_listings` flows into
   `suggest_outfit` and `create_fit_card` without re-entry (shown via the populated panels
   and narrated).
4. **A triggered failure** — the no-results query *"designer ballgown size XXS under $5"*,
   showing the agent's specific, actionable error message and the empty styling panels.
