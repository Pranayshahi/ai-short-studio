"""Photo credits: every CC photo is credited (no 12-line cap) and credits follow image replacements."""


def _rec(i):
    return {"source": "web_free", "author": f"Photographer {i}", "license": "CC BY 2.0",
            "page_url": f"https://www.flickr.com/photos/someone/{1000 + i}"}


def test_every_photo_is_credited():
    from app.agents.pipeline import attach_visual_metadata
    sd = {"description": "A car edit.\n\n#Shorts", "scenes": []}
    attach_visual_metadata(sd, [_rec(i) for i in range(20)])
    assert all(f"Photographer {i}" in sd["description"] for i in range(20)), "credits were cut off"
    assert len(sd["description"]) <= 5000


def test_long_descriptions_shorten_lines_not_drop_credits():
    from app.agents.pipeline import _with_credits_block
    out = _with_credits_block("x" * 4000, [f"• Person {i} · CC BY 2.0 · https://www.flickr.com/photos/p/{i}" for i in range(30)])
    assert len(out) <= 5000 and all(f"Person {i}" in out for i in range(30))


def test_credits_follow_replaced_images():
    from app.agents.pipeline import refresh_photo_credits
    proj = {"description": "Desc\n\nPhoto credits:\n• Old Person · CC BY 2.0 · https://x/1",
            "visual_records": [_rec(7)]}
    refresh_photo_credits(proj)
    assert "Old Person" not in proj["description"] and "Photographer 7" in proj["description"]
    assert proj["description"].startswith("Desc")
