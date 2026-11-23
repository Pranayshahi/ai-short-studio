"""Web search first: results are sources; a web sentence becomes a fact only when confirmed."""
from unittest import mock

from agents import web_search as ws

R = [{"title": "Northrop", "url": "https://news.northropgrumman.com/b21", "domain": "news.northropgrumman.com", "reliability": "official",
      "content": "## Summary Here are 10 key facts about the B-21. The B-21 Raider first flew in 2023. "
                 "It can go 0 to 100 in 11.95 seconds (claimed). The B-21 has a wingspan of 45 m. Read More about it."},
     {"title": "Air Force", "url": "https://www.af.mil/b21", "domain": "af.mil", "reliability": "official",
      "content": "The B-21 Raider flew for the first time in November 2023 from Palmdale."},
     {"title": "Blog", "url": "https://someblog.com/x", "domain": "someblog.com", "reliability": "web",
      "content": "The B-21 is the most beautiful aircraft ever built by anyone at all."}]


def test_only_confirmed_clean_sentences():
    got = ws.corroborated_sentences(R, reference_text="")
    assert "The B-21 Raider first flew in 2023." in got, got
    assert not any("45 m" in g for g in got), "a number only one site states is not a fact"
    assert not any("claimed" in g or "Here are" in g or "Summary" in g or "Read More" in g for g in got), got
    assert not any("beautiful" in g for g in got), "plain claims only from official / reference sites"


def test_skips_social_and_rates_sources():
    assert ws.SKIP_DOMAINS.search("youtube.com") and ws.SKIP_DOMAINS.search("www.pinterest.com".removeprefix("www."))
    assert ws.reliability("af.mil") == "official" and ws.reliability("en.wikipedia.org") == "reference"
    assert ws.reliability("cardekho.com") == "web"


def test_no_key_means_no_search(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with mock.patch("requests.post", side_effect=AssertionError("must not call Tavily without a key")):
        assert ws.search("B-21") == [] and ws.search_images("B-21") == []


def test_bare_numbers_need_the_same_word():
    rs = [{"title": "a", "url": "https://a.com", "domain": "a.com", "reliability": "official",
           "content": "The Hycross comes in 12 variants across 7- and 8-seat layouts."},
          {"title": "b", "url": "https://b.com", "domain": "b.com", "reliability": "official",
           "content": "It is available in 6 variants and 12 colours with 7 seats."}]
    got = ws.corroborated_sentences(rs)
    assert not any("12 variants" in g for g in got), got
