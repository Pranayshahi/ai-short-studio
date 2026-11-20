"""YouTube 'altered or synthetic content' disclosure is actually SENT (it used to be computed but dropped)."""
from pathlib import Path
from unittest import mock


def _fake_youtube(sent):
    class Req:
        def __init__(self, body): self.body = body
        def next_chunk(self): return None, {"id": "vid1"}
        def execute(self): return {"id": "vid1"}

    class Videos:
        def insert(self, part, body, media_body=None): sent.append(("insert", body["status"])); return Req(body)
        def update(self, part, body): sent.append(("update", body["status"])); return Req(body)

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


def test_disclosure_is_sent_on_upload_and_approve(tmp_path):
    from app.agents import youtube_publisher as yp
    sent = []
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"0" * 2000)
    tok = tmp_path / "t.json"
    tok.write_text("{}")
    info = lambda channel=None: {"key": "weaponxlabs", "id": "UCx", "handle": "@x", "title": "X", "token_path": tok,
                                 "studio_url": "https://studio.youtube.com/channel/UCx", "upload_url": "u"}
    with mock.patch.object(yp, "HAS_GOOGLE_API", True), \
         mock.patch.object(yp, "MediaFileUpload", lambda *a, **k: None, create=True), \
         mock.patch.object(yp.YouTubePublisher, "channel_info", staticmethod(info)), \
         mock.patch.object(yp.YouTubePublisher, "get_authenticated_service", classmethod(lambda cls, channel=None, interactive=True: _fake_youtube(sent))):
        yp.YouTubePublisher.upload_short(str(vid), "T #Shorts", "D", ["t"], synthetic=False)
        yp.YouTubePublisher.approve_and_go_live({"youtube": {"video_id": "vid1", "filled_fields": {}}, "video_path": str(vid),
                                                 "scenes": [{"clip_path": "c.mp4"}]})
    assert sent[0][0] == "insert" and sent[0][1]["containsSyntheticMedia"] is False
    assert sent[1][0] == "update" and sent[1][1]["containsSyntheticMedia"] is True
    assert all(s[1]["privacyStatus"] == "private" for s in sent)
