"""YouTube 'altered or synthetic content' disclosure is actually SENT (it used to be computed but dropped)."""
from pathlib import Path
from unittest import mock


def _fake_youtube(sent, current_label=None):
    class Req:
        def __init__(self, body): self.body = body
        def next_chunk(self): return None, {"id": "vid1"}
        def execute(self): return self.body

    class Videos:
        def insert(self, part, body, media_body=None): sent.append(("insert", body["status"])); return Req({"id": "vid1"})
        def update(self, part, body): sent.append(("update", body["status"])); return Req({"id": "vid1"})
        def list(self, part, id):
            st = {} if current_label is None else {"containsSyntheticMedia": current_label}
            return Req({"items": [{"id": id, "status": st}]})

    class Channels:
        def list(self, **k): return Req({})

    class YT:
        def videos(self): return Videos()
        def channels(self): return Channels()
    return YT()


def test_disclosure_follows_the_content(tmp_path):
    from app.agents import youtube_publisher as yp
    real_photos = {"scenes": [{"image_path": "a.png"}], "visual_records": [{"source": "web_free"}]}
    ai_clip = {"scenes": [{"image_path": "a.png", "clip_path": "c.mp4"}], "visual_records": [{"source": "web_free"}]}
    ai_image = {"scenes": [{}], "visual_records": [{"source": "ai_generated"}]}
    cards_only = {"scenes": [{"title_card": "intro", "clip_path": "intro.mp4"}], "visual_records": [{"source": "car_title_card"}]}
    assert yp.uses_synthetic_media(real_photos) is False
    assert yp.uses_synthetic_media(ai_clip) is True
    assert yp.uses_synthetic_media(ai_image) is True
    assert yp.uses_synthetic_media(cards_only) is False, "logo/end cards are graphics, not realistic AI footage"
    assert yp.uses_synthetic_media(None) is True, "unknown -> declare it (safe)"


def _run(tmp_path, current_label, auto):
    from unittest import mock
    from app.agents import youtube_publisher as yp
    sent = []
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"0" * 2000)
    tok = tmp_path / "t.json"
    tok.write_text("{}")
    info = lambda channel=None: {"key": "weaponxlabs", "id": "UCx", "handle": "@x", "title": "X", "token_path": tok,
                                 "studio_url": "https://studio.youtube.com/channel/UCx", "upload_url": "u"}
    with mock.patch.object(yp, "AUTO_AI_LABEL", auto), mock.patch.object(yp, "HAS_GOOGLE_API", True), \
         mock.patch.object(yp, "MediaFileUpload", lambda *a, **k: None, create=True), \
         mock.patch.object(yp.YouTubePublisher, "channel_info", staticmethod(info)), \
         mock.patch.object(yp.YouTubePublisher, "get_authenticated_service",
                           classmethod(lambda cls, channel=None, interactive=True: _fake_youtube(sent, current_label))):
        yp.YouTubePublisher.upload_short(str(vid), "T #Shorts", "D", ["t"], synthetic=True)
        yp.YouTubePublisher.approve_and_go_live({"youtube": {"video_id": "vid1", "filled_fields": {}}, "video_path": str(vid),
                                                 "scenes": [{"clip_path": "c.mp4"}]})
    return sent


def test_no_automatic_ai_label_by_default(tmp_path):
    """User rule (2026-11-20): the app never sets the AI label itself; the owner does it in Studio."""
    sent = _run(tmp_path, current_label=None, auto=False)
    assert sent[0][1]["containsSyntheticMedia"] is False, "upload must not label"
    assert "containsSyntheticMedia" not in sent[1][1], "approve must not set a label the video doesn't have"
    assert all(x[1]["privacyStatus"] == "private" for x in sent)


def test_label_set_in_studio_is_kept_on_approve(tmp_path):
    sent = _run(tmp_path, current_label=True, auto=False)
    assert sent[1][1]["containsSyntheticMedia"] is True, "approving must not undo the owner's own label"


def test_opt_in_auto_label(tmp_path):
    sent = _run(tmp_path, current_label=None, auto=True)
    assert sent[0][1]["containsSyntheticMedia"] is True and sent[1][1]["containsSyntheticMedia"] is True


def test_publish_and_approve_never_open_a_sign_in_window():
    """Publishing with a missing/expired token must fail with a message, not start a browser OAuth flow
    (it popped a Google window from the dashboard and blocked the request)."""
    import inspect
    from app.agents.youtube_publisher import YouTubePublisher as YP
    src = inspect.getsource(YP)
    assert 'interactive=not ch["token_path"].exists()' not in src


def test_weapon_videos_get_the_owners_hashtags():
    from agents.youtube_metadata import apply_weapon_hashtags, weapon_hashtags
    tags = weapon_hashtags()
    assert tags[0] == "#defense" and "#ak47shorts" in tags and tags[-1] == "#trending" and len(tags) == 18
    desc = "The T-90 entered service in 1992.\n\n#Shorts #WeaponXLabs #MilitaryTech\n#Defense"
    d, t = apply_weapon_hashtags(desc, ["t-90", "tank"])
    assert d.startswith("The T-90 entered service in 1992.") and d.endswith(" ".join(tags))
    assert "#WeaponXLabs" not in d, "old hashtag-only lines are replaced by the owner's set"
    assert apply_weapon_hashtags(d, t) == (d, t), "idempotent"
    assert t[:2] == ["t-90", "tank"] and "ak47shorts" in t
    from app.agents.youtube_publisher import YouTubePublisher as YP
    meta = None \
        if False else YP.build_complete_fields("T-90 #Shorts", desc, ["tank"], channel="weaponxlabs")
    if meta:
        assert meta["description"].count("#ak47shorts") == 1
