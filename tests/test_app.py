"""
The app's offline test suite (pytest). Each check group from agents/qa_tester_agent.py that needs no
real data runs here in an isolated temp folder (see conftest.py); each individual check is reported.

Groups that inspect real projects (API smoke over existing videos, storage index, produced media,
verify-video on a real project, music catalog) are integration checks and stay in the dashboard's
"QA Sanity" button.
"""
import pytest

UNIT_GROUPS = [
    "python_syntax",
    "dom_contract",
    "frontend_js_contract",
    "image_studio_engine",
    "shape_resize_compositing",
    "fonts_availability",
    "weapon_visual_accuracy_contract",
    "phase1_image_generation_engine",
    "phase2_automation_contracts",
    "layer_studio_and_rerender_contracts",
    "subject_accuracy_regressions",
    "topic_agent_contract",
    "content_analyser_contract",
    "music_agent",
    "hindi_voice_agent",
    "youtube_metadata_guard",
    "scene_effects",
    "video_quality_regressions",
]

_cache = {}


def _results(group):
    if group not in _cache:
        from agents.qa_tester_agent import QATesterAgent
        _cache[group] = getattr(QATesterAgent(), f"_check_{group}")()
    return _cache[group]


@pytest.mark.parametrize("group", UNIT_GROUPS)
def test_group(group):
    results = _results(group)
    assert results, f"{group}: no checks ran"
    failed = [r for r in results if r.get("status") != "PASSED"]
    assert not failed, "\n".join(f"{r['name']}: {r.get('details')}" for r in failed)


def test_never_uses_real_data():
    import config
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for d in (config.OUTPUT_DIR, config.AUDIO_ASSETS_DIR, config.CREDENTIALS_DIR):
        assert root not in Path(d).resolve().parents, f"{d} is inside the real project"


def test_no_undefined_names():
    """Static check: a name used but never defined/imported (e.g. a helper deleted by an edit) fails here
    instead of crashing a video at runtime."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    out = subprocess.run([sys.executable, "-m", "pyflakes", "agents", "app", "scheduler.py", "config.py", "main.py"],
                         cwd=root, capture_output=True, text=True).stdout
    bad = [ln for ln in out.splitlines() if "undefined name" in ln or "referenced before assignment" in ln]
    assert not bad, "\n".join(bad)
