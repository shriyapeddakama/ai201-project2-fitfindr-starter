"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # Step 1: fresh session — the single source of truth for this interaction.
    session = _new_session(query, wardrobe)

    # Step 2: parse the raw query into description / size / max_price (regex).
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # Step 3: search. This is the conditional branch point of the loop.
    session["search_results"] = search_listings(description, size, max_price)

    if not session["search_results"]:
        # ERROR BRANCH — no item to style, so terminate early. We do NOT call
        # suggest_outfit or create_fit_card. fit_card / outfit_suggestion stay None.
        filters = []
        if size is not None:
            filters.append(f"size {size}")
        if max_price is not None:
            filters.append(f"under ${max_price:.0f}")
        filter_str = (" in " + ", ".join(filters)) if filters else ""
        session["error"] = (
            f"No listings matched '{description}'{filter_str}. "
            "Try removing the size filter, raising your budget, or using broader "
            "keywords (e.g. 'graphic tee' instead of a specific print)."
        )
        return session

    # Step 4: select the top-ranked match and store it in the session.
    session["selected_item"] = session["search_results"][0]

    # Step 5: style the selected item against the wardrobe. suggest_outfit handles
    # the empty-wardrobe case internally and always returns a non-empty string.
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: turn the outfit + item into a shareable caption.
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: done — error is None, all output fields populated.
    return session


# ── query parsing ─────────────────────────────────────────────────────────────

# Standalone clothing-size tokens we recognize in free text. Restricted to the
# unambiguous multi-letter sizes: bare single letters (s/m/l) match too eagerly
# in natural prose (e.g. the "s" in "What's") and cause false size filters, so a
# single-letter size must be given explicitly as "size S".
_SIZE_TOKENS = ["xxs", "xs", "xxl", "xl"]


def _parse_query(query: str) -> dict:
    """
    Extract a search description, an optional size, and an optional max_price
    from a free-text query using regex. Returns a dict with keys
    'description', 'size', 'max_price' — matching the Planning Loop spec.
    """
    text = query or ""
    size = None
    max_price = None
    # Spans of the original text we consume for size/price, removed from the
    # leftover description so they don't pollute keyword search.
    consumed_spans = []

    # max_price: a dollar amount after under / below / less than / <= / <  or  $.
    price_pat = re.compile(
        r"(?:under|below|less than|<=|<|max(?:imum)?|up to)\s*\$?\s*(\d+(?:\.\d+)?)"
        r"|\$\s*(\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    m = price_pat.search(text)
    if m:
        max_price = float(m.group(1) or m.group(2))
        consumed_spans.append(m.span())

    # size: explicit "size <token>" (token may be a letter size or a number).
    size_phrase = re.search(
        r"\bsize\s+([a-zA-Z0-9.\-/]+)", text, re.IGNORECASE
    )
    if size_phrase:
        size = size_phrase.group(1).upper()
        consumed_spans.append(size_phrase.span())
    else:
        # standalone letter-size token as its own word, e.g. "... tee M"
        for tok in _SIZE_TOKENS:
            tm = re.search(rf"\b({tok})\b", text, re.IGNORECASE)
            if tm:
                size = tm.group(1).upper()
                consumed_spans.append(tm.span())
                break

    # description: original text minus the consumed size/price spans, tidied up.
    description = text
    for start, end in sorted(consumed_spans, key=lambda s: s[0], reverse=True):
        description = description[:start] + " " + description[end:]
    # collapse whitespace and strip trailing filler punctuation.
    description = re.sub(r"\s+", " ", description).strip(" ,.-")

    # If stripping left nothing usable, fall back to the full original query.
    if not description:
        description = text.strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
