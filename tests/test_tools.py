"""
tests/test_tools.py

Tests for the three FitFindr tools. At least one test per failure mode:
  - search_listings: returns results / empty result (no exception) / price filter
  - suggest_outfit: empty wardrobe is handled gracefully (no crash)
  - create_fit_card: empty outfit returns a message string (no crash)

The LLM-backed tools (suggest_outfit, create_fit_card) are tested for their
contract — non-empty string output and graceful handling of bad input — without
asserting on exact wording, since the model output varies.

Run from the project root with:  pytest tests/
"""

import os
import sys

# Make the project root importable when pytest is run from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import (
    get_example_wardrobe,
    get_empty_wardrobe,
    load_listings,
)


# ── search_listings ─────────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # Each result is a full listing dict with the documented fields.
    first = results[0]
    for field in ("id", "title", "price", "category", "style_tags", "platform"):
        assert field in first


def test_search_empty_results():
    # No listing matches this query — must return [] (empty list), not raise.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    # The price ceiling is inclusive and must be respected for every result.
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match sizes like "M", "S/M", "M/L" case-insensitively.
    results = search_listings("top", size="m", max_price=None)
    assert all("m" in item["size"].lower() for item in results)


def test_search_ranks_by_relevance():
    # A specific query should surface a strongly matching item at the top.
    results = search_listings("graphic tee", size=None, max_price=None)
    assert len(results) > 0
    top = results[0]
    haystack = (top["title"] + " " + " ".join(top["style_tags"])).lower()
    assert "graphic" in haystack or "tee" in haystack


# ── suggest_outfit ──────────────────────────────────────────────────────────────

def _sample_item() -> dict:
    return load_listings()[1]  # lst_002 Y2K Baby Tee


def test_suggest_outfit_empty_wardrobe_does_not_crash():
    # Empty wardrobe must be handled gracefully and still return a non-empty
    # styling string (general advice), never raise or return "".
    result = suggest_outfit(_sample_item(), get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_with_wardrobe_returns_string():
    result = suggest_outfit(_sample_item(), get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


# ── create_fit_card ─────────────────────────────────────────────────────────────

def test_fit_card_empty_outfit_returns_message():
    # An empty outfit string must return a descriptive message, not crash.
    result = create_fit_card("", _sample_item())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_fit_card_whitespace_outfit_returns_message():
    result = create_fit_card("   ", _sample_item())
    assert isinstance(result, str)
    assert result.strip() != ""


def test_fit_card_returns_string_for_valid_input():
    outfit = "Pair the baby tee with baggy jeans and chunky white sneakers."
    result = create_fit_card(outfit, _sample_item())
    assert isinstance(result, str)
    assert result.strip() != ""
