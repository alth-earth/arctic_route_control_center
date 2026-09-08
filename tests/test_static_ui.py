from __future__ import annotations

from pathlib import Path

STATIC_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "arctic_route_control_center"
    / "static"
)


def test_help_entry_documents_both_platforms_and_runtime_layout() -> None:
    html = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")

    assert 'id="help-button"' in html
    assert 'id="help-dialog"' in html
    assert 'id="help-close"' in html
    for text in (
        "${XDG_DATA_HOME:-~/.local/share}/arctic-route-control-center",
        "%LOCALAPPDATA%\\ArcticRouteControlCenter\\",
        "artifacts/inbox",
        "artifacts/ready",
        "invalid/",
        "config/",
        "run/",
        "logs/",
        "cache/",
        "ARCTIC_ROUTE_DATA_ROOT",
        "ARCTIC_ROUTE_VIEWER_PACKAGES",
        ".env.copernicus",
        ".cdsapirc",
    ):
        assert text in html


def test_help_entry_is_wired_and_scrollable() -> None:
    javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")
    stylesheet = (STATIC_ROOT / "style.css").read_text(encoding="utf-8")

    assert "function bindHelpDialog()" in javascript
    assert "dialog.showModal()" in javascript
    assert ".help-dialog" in stylesheet
    assert ".help-dialog-body" in stylesheet


def test_artifact_viewer_links_preserve_same_name_source() -> None:
    javascript = (STATIC_ROOT / "app.js").read_text(encoding="utf-8")

    assert "package_location" in javascript
    assert "new URLSearchParams({ package: item.package_dir })" in javascript
