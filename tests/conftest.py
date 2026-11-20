"""
Test isolation: every test run uses a brand-new temporary output / audio / credentials folder, set
BEFORE the app is imported. Tests can never read or change real projects, the music library, the
pre-made music pool, the job queue or YouTube tokens.

Only the channel registry (channels.json - channel ids and handles, no tokens) is copied in, because
several modules need to know which channels exist.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="ai_shorts_tests_"))
os.environ["AI_SHORTS_OUTPUT_DIR"] = str(_TMP / "output")
os.environ["AI_SHORTS_AUDIO_DIR"] = str(_TMP / "audio")
os.environ["AI_SHORTS_CREDENTIALS_DIR"] = str(_TMP / "credentials")
os.environ.setdefault("SCRIPT_WRITER", "template")   # never call the local LLM from tests
os.environ.setdefault("THEME_MUSIC", "on")
for sub in ("output", "audio", "credentials"):
    (_TMP / sub).mkdir(parents=True, exist_ok=True)
reg = ROOT / "credentials" / "channels.json"
if reg.exists():
    shutil.copyfile(reg, _TMP / "credentials" / "channels.json")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


def pytest_configure(config):
    import config as app_config  # noqa: F401  (imported after the env is set)
    real = ROOT / "output"
    assert Path(app_config.OUTPUT_DIR).resolve() != real.resolve(), "tests must never use the real output folder"
