from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest

from locus.app.server import build_server


@pytest.fixture()
def running_server(tmp_path: Path):
    (tmp_path / "dashboard.html").write_text(
        "<!doctype html><title>Locus</title>", encoding="utf-8"
    )
    (tmp_path / "summary.json").write_text(
        json.dumps({"city_name": "Казань", "cells": 1}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "location_index.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    server = build_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_root_serves_dashboard(running_server: str) -> None:
    status, body = _get(running_server + "/")
    assert status == 200
    assert "Locus" in body


def test_health_endpoint(running_server: str) -> None:
    status, body = _get(running_server + "/api/health")
    assert status == 200
    assert json.loads(body) == {"status": "ok"}


def test_summary_endpoint(running_server: str) -> None:
    status, body = _get(running_server + "/api/summary")
    assert status == 200
    assert json.loads(body)["city_name"] == "Казань"
