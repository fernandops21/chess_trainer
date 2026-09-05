from pathlib import Path

from fastapi.testclient import TestClient

from chess_trainer.api.app import create_app


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_spa_fallback_serves_index_for_unknown_routes(tmp_path):
    client = TestClient(create_app(db_path=":memory:", dist_dir=_dist(tmp_path)))
    assert client.get("/").text.startswith("<!doctype html>")
    assert client.get("/treinar").status_code == 200
    assert "SPA" in client.get("/partidas/abc").text
    assert client.get("/assets/app.js").text == "console.log(1)"


def test_api_404_is_not_masked_by_fallback(tmp_path):
    client = TestClient(create_app(db_path=":memory:", dist_dir=_dist(tmp_path)))
    r = client.get("/api/nao-existe")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_no_dist_means_no_static(tmp_path):
    client = TestClient(create_app(db_path=":memory:", dist_dir=tmp_path / "missing"))
    assert client.get("/treinar").status_code == 404
