from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_exposes_explicit_viewer_package_inputs() -> None:
    script = (ROOT / "packaging/windows/build-windows.ps1").read_text(encoding="utf-8")

    assert '[string[]]$ViewerPackage = @()' in script
    assert '[string]$ViewerManifest = ""' in script
    assert '"--viewer-package", $package' in script
    assert '"--viewer-manifest", $ViewerManifest' in script
    # No package name, no fixed artifact slot, no appdata default and no legacy
    # environment variables are allowed to leak back into the build script.
    assert "winter-rebuilt-20260215-viewer-package-v4" not in script
    assert "$EmbeddedReadyPackageName" not in script
    assert "ARCTIC_ROUTE_VIEWER_ROOT" not in script
    assert "ARCTIC_ROUTE_READY_PACKAGE" not in script


def test_windows_ai_prompt_documents_explicit_viewer_inputs() -> None:
    prompt = (ROOT / "docs/WINDOWS_AI_PROMPT.zh-CN.md").read_text(encoding="utf-8")

    for text in (
        "-ViewerPackage",
        "-ViewerManifest",
        "ARCTIC_ROUTE_VIEWER_PACKAGES",
        "内嵌 Viewer 数据制品",
    ):
        assert text in prompt
    # The prompt must not reintroduce a specific package name or legacy flags.
    assert "winter-rebuilt-20260215-viewer-package-v4" not in prompt
    assert "-ViewerRootPackage" not in prompt
    assert "-ReadyPackage" not in prompt
    assert "/root/" not in prompt
    assert "C:\\Users\\" not in prompt
