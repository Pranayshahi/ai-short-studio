"""YouTube performance loop: reads stats per channel (read-only), keeps a daily history, summarises."""


def _fake_service(stats):
    class Req:
        def __init__(self, ids): self.ids = ids
        def execute(self):
            return {"items": [{"id": i, "statistics": stats[i], "status": {"privacyStatus": "public" if int(stats[i]["viewCount"]) else "private"}}
                              for i in self.ids.split(",") if i in stats]}

    class Videos:
        def list(self, part, id): return Req(id)

    class YT:
        def videos(self): return Videos()
    return lambda ch: YT()


def test_refresh_and_summary(tmp_path):
    from app.automation import analytics
    from app.utils.storage import StorageManager
    base = {"project_dir": str(tmp_path), "status": "approved_private"}
    StorageManager.save_project({**base, "id": "an_car", "topic": "Car", "style": "car_edit", "channel": "autoflashx",
                                 "music_theme": {"theme": "Drift Phonk"}, "youtube": {"video_id": "V1"}})
    StorageManager.save_project({**base, "id": "an_wx", "topic": "Wx", "style": "weaponx", "channel": "weaponxlabs",
                                 "youtube": {"video_id": "V2"}})
    StorageManager.save_project({**base, "id": "an_none", "topic": "Not uploaded", "style": "default"})
    res = analytics.refresh(_fake_service({"V1": {"viewCount": "1200", "likeCount": "80", "commentCount": "5"},
                                           "V2": {"viewCount": "0", "likeCount": "0", "commentCount": "0"}}))
    assert res["updated"] == 2 and not res["errors"], res
    car = StorageManager.get_project_by_id("an_car")["youtube_stats"]
    assert car["views"] == 1200 and car["privacy"] == "public" and car["history"][-1]["views"] == 1200
    s = analytics.summary()
    assert s["totals"]["views"] >= 1200
    style = {r["name"]: r for r in s["by_style"]}
    assert style["car_edit"]["avg_views"] == 1200 and style["weaponx"]["avg_views"] == 0
    assert {r["name"] for r in s["by_music_theme"]} >= {"Drift Phonk"}


def test_unauthorized_channel_is_reported_not_crashing(tmp_path):
    from app.automation import analytics
    from app.utils.storage import StorageManager
    StorageManager.save_project({"id": "an_x", "topic": "X", "project_dir": str(tmp_path), "status": "approved_private",
                                 "channel": "autoflashx", "youtube": {"video_id": "V9"}})

    def boom(ch):
        raise RuntimeError("token expired")
    res = analytics.refresh(boom)
    assert res["updated"] == 0 and any("not authorized" in e for e in res["errors"])
