"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    listings = load_listings()

    # 1. Filter by optional price ceiling and optional size first.
    candidates = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.strip():
            # Case-insensitive substring match: "M" matches "S/M",
            # "8" matches "US 8" and "US 8.5".
            if size.strip().lower() not in item["size"].lower():
                continue
        candidates.append(item)

    # 2. Tokenize the description into meaningful keywords.
    keywords = _keywords(description)
    if not keywords:
        # No usable keywords — fall back to returning everything that passed
        # the size/price filters, cheapest first, rather than nothing.
        return sorted(candidates, key=lambda it: it["price"])

    # 3. Score each candidate by keyword overlap and drop zero-relevance items.
    scored = []
    for item in candidates:
        score = _score_listing(item, keywords)
        if score > 0:
            scored.append((score, item))

    # 4. Sort by score (highest first), tie-break on price (cheapest first).
    scored.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [item for _score, item in scored]


# ── search helpers ─────────────────────────────────────────────────────────────

# Common words that carry no search signal — stripped before keyword matching.
_STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "in", "on", "of", "to", "or",
    "i", "im", "me", "my", "looking", "want", "need", "find", "some", "any",
    "that", "this", "under", "below", "over", "size", "sized", "price",
    "cheap", "around", "about", "is", "are", "it", "would", "like",
}


def _keywords(description: str) -> list[str]:
    """Lowercase the description and split it into significant search tokens."""
    if not description:
        return []
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in description)
    return [
        tok for tok in cleaned.split()
        if len(tok) > 1 and tok not in _STOPWORDS
    ]


def _score_listing(item: dict, keywords: list[str]) -> int:
    """
    Count how strongly a listing matches the keywords.

    Title and style_tags hits are weighted more heavily than body/colors/category
    matches, since they are the strongest signals of relevance.
    """
    title = item.get("title", "").lower()
    body = item.get("description", "").lower()
    category = item.get("category", "").lower()
    tags = " ".join(item.get("style_tags", [])).lower()
    colors = " ".join(item.get("colors", [])).lower()

    score = 0
    for kw in keywords:
        if kw in title:
            score += 3
        if kw in tags:
            score += 3
        if kw in category:
            score += 2
        if kw in colors:
            score += 2
        if kw in body:
            score += 1
    return score


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    item_desc = _format_item(new_item)
    items = (wardrobe or {}).get("items", [])

    if not items:
        # Empty/minimal wardrobe — general styling advice, not an error.
        prompt = (
            f"A shopper is considering buying this secondhand item:\n{item_desc}\n\n"
            "They haven't added any pieces from their own closet yet. "
            "Suggest how to style this item on its own: what kinds of pieces "
            "(by category and color) pair well with it, and what overall vibe "
            "it suits. Keep it to 2-3 short, friendly sentences. Do NOT invent "
            "specific pieces as if they already own them."
        )
    else:
        wardrobe_text = "\n".join(f"- {_format_wardrobe_item(w)}" for w in items)
        prompt = (
            f"A shopper is considering buying this secondhand item:\n{item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1-2 complete head-to-toe outfits built around the new item, "
            "naming specific pieces from their wardrobe by name. Mention shoes and "
            "an accessory or layer where it makes sense. Keep each outfit to 1-2 "
            "sentences and sound like an enthusiastic friend giving styling advice."
        )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are FitFindr, a warm, knowledgeable secondhand-fashion "
                        "stylist. Give concrete, wearable outfit ideas."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        # Empty completion — fall through to the deterministic fallback.
    except Exception:
        pass

    # Graceful fallback if the LLM is unreachable / errors / returns nothing.
    return _outfit_fallback(new_item)


def _outfit_fallback(new_item: dict) -> str:
    """Deterministic styling string built from the item's own attributes."""
    title = new_item.get("title", "this piece")
    category = new_item.get("category", "item")
    tags = ", ".join(new_item.get("style_tags", [])) or "versatile"
    colors = ", ".join(new_item.get("colors", [])) or "neutral"
    return (
        f"I couldn't reach the styling model right now, but the {title} is a "
        f"{tags} {category} in {colors}. It would pair well with simple neutral "
        "basics, a structured layer, and your go-to shoes for an easy everyday look."
    )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    # 1. Guard against an empty / whitespace-only outfit — return a message,
    #    never raise.
    if not outfit or not outfit.strip():
        return (
            "I need an outfit suggestion before I can write a fit card. "
            "Try searching again so I can style a specific piece."
        )

    title = new_item.get("title", "this thrifted find")
    price = new_item.get("price")
    price_str = f"${price:.0f}" if isinstance(price, (int, float)) else "a steal"
    platform = new_item.get("platform", "secondhand")

    prompt = (
        f"Write a short, shareable social-media caption (2-4 sentences) for an "
        f"outfit-of-the-day post about a thrifted find.\n\n"
        f"Item: {title}\n"
        f"Price: {price_str}\n"
        f"Platform: {platform}\n"
        f"The outfit it's styled in:\n{outfit}\n\n"
        "Make it casual and authentic, like a real OOTD post (not a product "
        f"description). Mention the item name, the price ({price_str}), and the "
        f"platform ({platform}) naturally — once each. Capture the outfit vibe in "
        "specific terms and end with 2-3 relevant hashtags. A tasteful emoji or "
        "two is fine."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a trend-savvy thrift influencer writing punchy, "
                        "original OOTD captions. Never repeat yourself."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.1,  # high temperature → captions vary across runs
            max_tokens=200,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
    except Exception:
        pass

    # Deterministic fallback caption if the LLM is unreachable / returns nothing.
    return (
        f"Just thrifted the {title} for {price_str} on {platform} ✨ styling it "
        "up next — stay tuned. #thriftfinds #ootd #secondhandstyle"
    )


# ── formatting helpers (shared by the LLM tools) ────────────────────────────────

def _format_item(item: dict) -> str:
    """Render a listing dict as a compact prompt-friendly description."""
    title = item.get("title", "Untitled item")
    category = item.get("category", "item")
    tags = ", ".join(item.get("style_tags", [])) or "n/a"
    colors = ", ".join(item.get("colors", [])) or "n/a"
    desc = item.get("description", "")
    return (
        f"{title} (category: {category}; colors: {colors}; "
        f"style: {tags}). {desc}"
    )


def _format_wardrobe_item(w: dict) -> str:
    """Render a wardrobe item dict as a single readable line for a prompt."""
    name = w.get("name", "unnamed piece")
    category = w.get("category", "")
    colors = ", ".join(w.get("colors", []))
    notes = w.get("notes")
    line = f"{name} ({category}"
    if colors:
        line += f", {colors}"
    line += ")"
    if notes:
        line += f" — {notes}"
    return line
