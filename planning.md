# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock secondhand-listings dataset (`data/listings.json`, loaded via `load_listings()`) for items that match the user's keywords, and optionally a size and a price ceiling. It scores every listing by how well its text overlaps the user's description, drops zero-relevance items, and returns the matches ranked best-first. This is a deterministic, non-LLM tool — pure filtering and keyword scoring.

**Input parameters:**
- `description` (str): Free-text keywords describing the desired item, e.g. `"vintage graphic tee"`. Required. Each significant word is compared (case-insensitive) against each listing's `title`, `description`, `style_tags`, `colors`, and `category`.
- `size` (str | None): Size string to filter on, e.g. `"M"`. Matching is case-insensitive substring matching so `"M"` matches `"S/M"` and `"8"` matches `"8.5"`. `None` (default) skips size filtering entirely.
- `max_price` (float | None): Inclusive upper price bound in dollars, e.g. `30.0`. A listing passes only if `listing["price"] <= max_price`. `None` (default) skips price filtering.

**What it returns:**
`list[dict]` — a list of full listing dicts, sorted by keyword-overlap score descending (best match first). Each dict contains exactly the fields from the dataset:
`id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark).
Returns an empty list `[]` when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
The function itself never raises; an empty result is a normal, expected outcome. The *planning loop* is responsible for reacting: if `search_listings` returns `[]`, the loop sets `session["error"]` to a specific, actionable message (which filters were applied and a concrete suggestion to relax them) and returns the session early **without** calling `suggest_outfit` — there is no item to style. See the Error Handling table for the exact wording.

---

### Tool 2: suggest_outfit

**What it does:**
Given one specific listing (the item the user is considering buying) and the user's wardrobe, asks the Groq LLM to propose 1–2 complete head-to-toe outfit combinations built around that item, naming actual wardrobe pieces. Falls back to general styling advice when the wardrobe is empty.

**Input parameters:**
- `new_item` (dict): A single listing dict (the top result from `search_listings`). The tool reads its `title`, `category`, `style_tags`, `colors`, and `description` to build the prompt.
- `wardrobe` (dict): A wardrobe dict shaped `{"items": [ ... ]}`, where each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. May contain an empty `items` list — this must be handled, not treated as an error.

**What it returns:**
`str` — a non-empty, human-readable outfit suggestion. When the wardrobe has items, it names 1–2 outfits referencing specific pieces by `name` (e.g. "Pair it with your *Baggy straight-leg jeans* and *Chunky white sneakers*…"). When the wardrobe is empty, it returns general styling guidance (what categories/colors/vibes pair well with the item) instead. Always returns a styling string, never an empty string.

**What happens if it fails or returns nothing:**
- **Empty wardrobe** (`wardrobe["items"]` is empty/missing): not a failure — switch to the "general styling advice" prompt branch and return that advice.
- **LLM/API failure** (network error, missing `GROQ_API_KEY`, empty completion): catch the exception and return a graceful fallback string built from `new_item`'s own attributes (e.g. "I couldn't reach the styling model, but this {style_tags} {category} in {colors} would pair well with neutral basics and your go-to shoes."). The loop still receives a usable non-empty string and proceeds to `create_fit_card`. The function never propagates an exception to the loop.

---

### Tool 3: create_fit_card

**What it does:**
Turns the chosen item plus the outfit suggestion into a short, shareable social-media caption — the kind of thing you'd post under an OOTD photo. Uses the LLM at a higher temperature so repeated/different inputs produce visibly different captions.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit()`. Required and must be non-empty/non-whitespace.
- `new_item` (dict): The listing dict for the thrifted find. The caption weaves in its `title`, `price`, and `platform` (each mentioned once, naturally).

**What it returns:**
`str` — a 2–4 sentence casual caption (with a few hashtags/emoji as appropriate) suitable for Instagram/TikTok. It mentions the item name, its price, and the platform once each, captures the outfit vibe in specific terms, and is generated at high temperature so it reads differently across runs and across different items.

**What happens if it fails or returns nothing:**
- **Empty/whitespace `outfit`**: guard at the top — return a descriptive message string such as "Couldn't generate a fit card without an outfit suggestion." instead of raising.
- **LLM/API failure or empty completion**: catch and return a deterministic template caption assembled from `new_item` (e.g. "Just thrifted the {title} for ${price} on {platform} ✨ styling it up next — stay tuned. #thriftfinds #ootd"). Never raises; always returns a usable string.

---

### Additional Tools (if any)

None for the core build. (Stretch idea, not yet implemented: `parse_query(query) -> dict` to LLM-extract `description`/`size`/`max_price`; for now this parsing lives inline in the planning loop via regex + keyword stripping — see Planning Loop.)

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a linear pipeline with **conditional early-exit branches** driven by what each tool returns and stored in `session`. It is not a fixed "call all three no matter what" sequence — an empty search result terminates the run before any styling happens, and an empty wardrobe changes how `suggest_outfit` is invoked.

1. **Initialize.** `session = _new_session(query, wardrobe)`. All output fields start `None`/`[]`, `error` starts `None`.

2. **Parse the query.** Extract `description`, `size`, `max_price` from the raw `query` and store in `session["parsed"]`.
   - `max_price`: regex for a dollar amount following "under/below/<=/$", e.g. `under $30` → `30.0`; if none found → `None`.
   - `size`: regex for `size <token>` or a standalone size token (`XS|S|M|L|XL|XXL` or a shoe number); if none found → `None`.
   - `description`: the query with the matched price/size phrases stripped out, trimmed. If stripping leaves it empty, fall back to the full original query.

3. **Branch A — call `search_listings(description, size, max_price)`.** Store in `session["search_results"]`.
   - **If `search_results == []`:** set `session["error"]` to a specific message naming the active filters and suggesting which to relax (see Error Handling), then **`return session` immediately**. Do not call `suggest_outfit` or `create_fit_card`.
   - **Else:** set `session["selected_item"] = session["search_results"][0]` (top-ranked match) and continue.

4. **Branch B — call `suggest_outfit(selected_item, wardrobe)`.** Store in `session["outfit_suggestion"]`.
   - Inside the tool: **if `wardrobe["items"]` is empty**, it returns general styling advice; **else** it returns wardrobe-specific outfits. Either way the loop receives a non-empty string and continues. (On an unexpected LLM error the tool returns its own fallback string — still non-empty — so the loop never stalls here.)

5. **Branch C — call `create_fit_card(outfit_suggestion, selected_item)`.** Store in `session["fit_card"]`.
   - The tool guards internally against an empty `outfit` and against LLM failure, always returning a usable caption.

6. **Done.** `return session`. The loop knows it is finished when `fit_card` is set (success) or when `error` is set (early exit). The caller checks `session["error"]` first; if `None`, all three output fields are populated.

**Why this is a real planning loop, not a hardcoded chain:** the transition from step 3 → step 4 is *conditional on the search result being non-empty*, and the behavior of step 4 is *conditional on whether the wardrobe has items*. Different queries therefore exercise different paths (full 3-tool flow vs. early error return vs. general-advice styling).

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict (created by `_new_session()` in `agent.py`) is the one source of truth for the entire interaction. Each tool's output is written into a named field, and the next tool reads from that field — the user never re-enters anything mid-flow.

Tracked fields and how they flow:

| Field | Written by | Read by |
|-------|-----------|---------|
| `query` | caller / `_new_session` | the parse step |
| `parsed` (`{description, size, max_price}`) | parse step | `search_listings` args |
| `search_results` (list[dict]) | `search_listings` | empty-check branch; source of `selected_item` |
| `selected_item` (dict) | loop (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` (dict) | caller / `_new_session` | `suggest_outfit` |
| `outfit_suggestion` (str) | `suggest_outfit` | `create_fit_card` |
| `fit_card` (str) | `create_fit_card` | final return / UI |
| `error` (str | None) | loop on early exit | caller checks first; UI shows it |

Concretely: `search_listings` returns a list → the loop stores it in `search_results` and copies `search_results[0]` into `selected_item` → `suggest_outfit(selected_item, wardrobe)` reads `selected_item` and returns a string into `outfit_suggestion` → `create_fit_card(outfit_suggestion, selected_item)` reads both and returns into `fit_card`. The item found in step 3 thus reaches both later tools with no re-entry. State lives only for the duration of one `run_agent()` call (per-session, in memory).

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loop sets `session["error"]` and returns early, before any styling. Message names the active filters and offers a concrete relaxation, e.g. *"No listings matched 'designer ballgown' in size XXS under $5. Try removing the size filter, raising your budget, or using broader keywords like 'formal dress'."* The UI shows this in the listing panel and leaves the outfit/fit-card panels empty. |
| suggest_outfit | Wardrobe is empty | Not treated as an error: the tool detects `wardrobe["items"] == []` and returns general styling advice instead — *"You haven't added any closet pieces yet, so here's how I'd style this on its own: pair it with neutral bottoms (black or denim), add a structured layer, and finish with clean white sneakers for an everyday look."* The flow continues to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | If `outfit` is empty/whitespace, return a clear message string — *"I need an outfit suggestion before I can write a fit card. Try searching again so I can style a specific piece."* — rather than raising. On an LLM/API error, return a deterministic template caption built from `new_item` (title, price, platform) so the user still gets a shareable result. |
| (any LLM tool) | Groq API error / missing GROQ_API_KEY / empty completion | `suggest_outfit` and `create_fit_card` each wrap their LLM call in try/except and return a non-empty fallback string assembled from the item's own fields, so a single API hiccup degrades gracefully instead of crashing the agent or blanking the UI. |

---

## Architecture

```
                              User query  +  wardrobe choice
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │   _new_session()       │  creates session dict:
                         │   PLANNING LOOP        │  {query, parsed, search_results,
                         │   (run_agent)          │   selected_item, wardrobe,
                         └───────────┬───────────┘   outfit_suggestion, fit_card, error}
                                     │
                     parse query → session["parsed"] = {description, size, max_price}
                                     │
                                     ▼
   ┌──► search_listings(description, size, max_price)  ──► returns list[dict]
   │            │
   │            │  search_results == []
   │            ├──────────────► [ERROR BRANCH]
   │            │                session["error"] = "No listings matched … try relaxing filters"
   │            │                return session  ───────────────────────────────────┐
   │            │                                                                    │
   │            │  search_results == [item, item, …]                                 │
   │            ▼                                                                    │
   │     Session: search_results = [...];  selected_item = search_results[0]         │
   │            │                                                                    │
   ├──► suggest_outfit(selected_item, wardrobe)  ──► returns str                     │
   │            │      ├─ wardrobe["items"] empty → general styling advice           │
   │            │      └─ wardrobe has items     → outfit using named pieces         │
   │            │      (LLM error → fallback string from item fields)                │
   │            ▼                                                                    │
   │     Session: outfit_suggestion = "..."                                          │
   │            │                                                                    │
   └──► create_fit_card(outfit_suggestion, selected_item)  ──► returns str           │
                │      ├─ empty outfit → "need an outfit first" message              │
                │      └─ LLM error    → template caption from item fields           │
                ▼                                                                    │
         Session: fit_card = "..."                                                   │
                │                                                                    │
                ▼                                                                    │
         Return session  ◄──────── error path returns here ◄──────────────────────┘
                │
                ▼
   UI panels:  🛍️ Top listing   👗 Outfit idea   ✨ Fit card
              (or error message in panel 1, others blank, on early exit)
```

**Component legend:** *User* (query + wardrobe radio choice) → *Planning Loop* (`run_agent`, owns the `session` state) → three *Tools* (`search_listings`, `suggest_outfit`, `create_fit_card`) → *Session state* read/written between every step. The labeled error branch from `search_listings` terminates the flow early and returns the session before any LLM tool runs.

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **`search_listings` (Claude).** Input: the **Tool 1** block above (inputs, return fields, empty-result behavior) plus the `load_listings()` docstring from `utils/data_loader.py`. Ask Claude to implement keyword-overlap scoring over `title`/`description`/`style_tags`/`colors`/`category`, case-insensitive `size` substring match, and inclusive `max_price` filter, returning sorted dicts. **Verify before use:** read the generated code to confirm it (a) applies all three filters, (b) drops score-0 items, (c) returns `[]` (never raises) when nothing matches. Then run 3 queries: `"vintage graphic tee under $30"` (expect tops, all ≤ $30), `"black combat boots size 8"` (size filter active), and `"designer ballgown size XXS under $5"` (expect `[]`).

- **`suggest_outfit` (Claude).** Input: the **Tool 2** block + the wardrobe item shape from `data/wardrobe_schema.json` + the `_get_groq_client()` helper signature in `tools.py`. Ask for the two-branch implementation (empty wardrobe → general advice; non-empty → named-piece outfits) wrapped in try/except with a fallback string. **Verify:** check that it branches on `wardrobe["items"]` emptiness and that both branches return non-empty strings; confirm the try/except returns a fallback rather than raising. Test once with `get_example_wardrobe()` (output should name real pieces like "Baggy straight-leg jeans") and once with `get_empty_wardrobe()` (output should be general, no invented pieces).

- **`create_fit_card` (Claude).** Input: the **Tool 3** block (style rules, mention item/price/platform once each, high temperature for variety) + an example `new_item` dict. **Verify:** confirm the empty-`outfit` guard exists, temperature is set high, and item/price/platform each appear once. Test by generating cards for two *different* items and one item *twice* — confirm outputs differ each time and stay 2–4 sentences.

**Milestone 4 — Planning loop and state management:**

- **`run_agent` planning loop (Claude).** Input: the **Planning Loop**, **State Management**, and **Architecture** sections above (especially the diagram, which encodes the conditional branches), plus the `_new_session()` field list and the tool signatures from `tools.py`. Ask Claude to implement the parse step + the conditional pipeline exactly as the diagram shows. **Verify:** trace the generated code against the diagram — confirm the empty-`search_results` branch sets `session["error"]` and returns **before** calling `suggest_outfit`, that `selected_item = search_results[0]`, and that every tool result is written to its named session field. Then run the two `__main__` scenarios in `agent.py` (happy path populates all fields with `error=None`; no-results path sets `error` and leaves outputs `None`).
- **`handle_query` UI wiring (Copilot/Claude).** Input: the `app.py` `handle_query` docstring + the session field names. **Verify:** empty query returns an error in panel 1; a successful run maps `selected_item`→listing panel, `outfit_suggestion`→outfit panel, `fit_card`→fit-card panel; an `error` session shows the message in panel 1 and blanks the other two.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?" (Wardrobe = Example wardrobe.)

**Step 1 — Initialize + parse.**
`run_agent()` builds the session via `_new_session(query, example_wardrobe)`. The parse step extracts: `max_price = 30.0` (from "under $30"), `size = None` (no size given), `description = "vintage graphic tee"` (price/size phrases and filler stripped). These are stored in `session["parsed"]`.

**Step 2 — `search_listings("vintage graphic tee", None, 30.0)`.**
The tool filters by price ≤ $30, scores remaining listings by keyword overlap with "vintage graphic tee", drops zero-score items, and returns ranked dicts. The top hit is `lst_002` *"Y2K Baby Tee — Butterfly Print"* ($18, depop, style_tags include "y2k", "vintage", "graphic tee"). The loop stores the list in `session["search_results"]` and sets `session["selected_item"] = search_results[0]` (the Y2K baby tee). Since results are non-empty, no error branch — proceed.

**Step 3 — `suggest_outfit(selected_item, example_wardrobe)`.**
The wardrobe has 10 items, so the LLM branch runs. It returns something like: *"Tuck the Y2K Baby Tee into your **Baggy straight-leg jeans (dark wash)**, throw on the **Vintage black denim jacket**, and finish with your **Chunky white sneakers** for a true 2000s street look. Add the **Black crossbody bag** to pull it together."* Stored in `session["outfit_suggestion"]`.

**Step 4 — `create_fit_card(outfit_suggestion, selected_item)`.**
At high temperature, the LLM produces a 2–4 sentence caption mentioning the item, its $18 price, and depop once each, e.g. *"Y2K dreams for $18 on depop ✨ butterfly baby tee + baggy jeans + chunky kicks = peak 2000s. Thrifted and proud. #depopfinds #y2kstyle #ootd"* Stored in `session["fit_card"]`. The loop returns the session.

**Final output to user:**
The Gradio UI shows three panels — **🛍️ Top listing found:** the Y2K Baby Tee details (title, $18, condition, depop); **👗 Outfit idea:** the styling text from Step 3; **✨ Your fit card:** the caption from Step 4. `session["error"]` is `None`, so all three panels are populated and the user gets a found item, a wardrobe-specific outfit, and a ready-to-post caption without ever re-entering the item.
