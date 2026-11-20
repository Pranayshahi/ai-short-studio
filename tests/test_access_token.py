"""Studio access token: every route needs it when set (header, cookie, or ?token= once)."""
from unittest import mock


def test_token_gate():
    from starlette.testclient import TestClient
    from app import web_app as wa
    with mock.patch.object(wa, "STUDIO_API_TOKEN", "s3cret-test-token"):
        c = TestClient(wa.app)
        assert c.get("/api/projects").status_code == 401
        assert c.get("/api/projects", headers={"X-Studio-Token": "wrong"}).status_code == 401
        assert c.get("/api/projects", headers={"X-Studio-Token": "s3cret-test-token"}).status_code == 200
        r = c.get("/?token=s3cret-test-token", follow_redirects=False)
        assert r.status_code == 303 and "studio_token" in r.headers.get("set-cookie", "")
        assert "token=" not in r.headers["location"], "the token is removed from the address bar"
    assert TestClient(wa.app).get("/api/projects").status_code == 200, "no token configured -> open (localhost only)"
