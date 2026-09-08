from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_build_accepts_both_viewer_package_paths() -> None:
    script = (ROOT / "packaging/windows/build-windows.ps1").read_text(encoding="utf-8")

    assert '[string]$ViewerRootPackage = ""' in script
    assert "$env:ARCTIC_ROUTE_VIEWER_ROOT" in script
    assert '"--viewer-root", $ViewerRootPackage' in script
    assert '[string]$ReadyPackage = ""' in script
    assert "$env:ARCTIC_ROUTE_READY_PACKAGE" in script
    assert "该制品不随 Git 仓库提供" in script
    # Viewer 数据制品是可选输入：缺省时构建跳过内嵌，而不是失败。
    assert "跳过内嵌根 Viewer 制品" in script
    assert "跳过内嵌 ready Viewer 制品" in script


def test_windows_ai_prompt_requests_missing_artifacts_without_fixed_team_path() -> None:
    prompt = (ROOT / "docs/WINDOWS_AI_PROMPT.zh-CN.md").read_text(encoding="utf-8")

    for text in (
        "远端 `main` 跟踪",
        "v4：`winter-rebuilt-20260215-viewer-package-v4` 不在 Git 远端",
        "缺失制品的完整目录或压缩包",
        "-ViewerRootPackage",
        "-ReadyPackage",
        "不要降级到 v2",
    ):
        assert text in prompt
    assert "/root/" not in prompt
    assert "C:\\Users\\" not in prompt
