"""Test the macOS build pipeline's signing steps.

No real codesign, notarization, or PyInstaller build is ever invoked; the
`run()` subprocess helper is mocked throughout.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import build_macos


@pytest.fixture(autouse=True)
def _isolated_dist_dir(tmp_path: Path, monkeypatch) -> Path:
    """Point DIST_DIR at a temporary directory so tests never touch the real build output."""
    monkeypatch.setattr(build_macos, "DIST_DIR", tmp_path)
    app = tmp_path / build_macos.APP_NAME
    (app / "Contents" / "MacOS").mkdir(parents=True)
    return app


@pytest.fixture(autouse=True)
def _fake_signing_identity(monkeypatch) -> None:
    """Provide a stand-in signing identity so tests never touch the real keychain."""
    monkeypatch.setattr(
        build_macos, "get_signing_identity", lambda: "Developer ID Application: Test"
    )


def test_require_signing_identity_passes_with_a_real_identity() -> None:
    """Do not raise when a Developer ID identity is available."""
    build_macos.require_signing_identity()


def test_require_signing_identity_raises_without_a_real_identity(monkeypatch) -> None:
    """Raise clearly when no Developer ID identity is available."""
    monkeypatch.setattr(build_macos, "get_signing_identity", lambda: None)

    with pytest.raises(RuntimeError, match="Developer ID"):
        build_macos.require_signing_identity()


def test_verify_application_always_checks_the_signature(tmp_path: Path, monkeypatch) -> None:
    """Verify the signature unconditionally; there is no way to silently skip it."""
    app = tmp_path / build_macos.APP_NAME
    calls: list[list[str]] = []
    monkeypatch.setattr(build_macos, "run", lambda cmd, **_kwargs: calls.append(cmd))

    build_macos.verify_application()

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:2] == ["codesign", "--verify"]
    assert "--deep" in cmd
    assert "--strict" in cmd
    assert str(app) in cmd


def test_verify_application_raises_when_the_app_is_missing(monkeypatch, tmp_path: Path) -> None:
    """Raise clearly when the expected build output does not exist."""
    monkeypatch.setattr(build_macos, "DIST_DIR", tmp_path / "empty")

    with pytest.raises(FileNotFoundError):
        build_macos.verify_application()


def test_pipeline_requires_identity_then_builds_and_verifies_before_packaging(
    monkeypatch,
) -> None:
    """Require a real identity, then build and verify before any DMG step."""
    order: list[str] = []
    monkeypatch.setattr(
        build_macos, "require_signing_identity", lambda: order.append("require_identity")
    )
    monkeypatch.setattr(build_macos, "setup", lambda: order.append("setup"))
    monkeypatch.setattr(build_macos, "run_tests", lambda: order.append("run_tests"))
    monkeypatch.setattr(
        build_macos, "build_application", lambda: order.append("build_application")
    )
    monkeypatch.setattr(build_macos, "verify_application", lambda: order.append("verify"))
    monkeypatch.setattr(build_macos, "package_release", lambda: order.append("package_release"))
    monkeypatch.setattr(build_macos, "verify_package", lambda: order.append("verify_package"))

    build_macos.pipeline(package=True)

    assert order == [
        "require_identity",
        "setup",
        "run_tests",
        "build_application",
        "verify",
        "package_release",
        "verify_package",
    ]


def test_pipeline_fails_fast_without_a_real_identity_before_any_build_work(monkeypatch) -> None:
    """Fail immediately, before any build step runs, when no Developer ID identity is available."""
    monkeypatch.setattr(build_macos, "get_signing_identity", lambda: None)

    def _fail():
        raise AssertionError("must not run build steps before the identity check")

    monkeypatch.setattr(build_macos, "setup", _fail)
    monkeypatch.setattr(build_macos, "run_tests", _fail)
    monkeypatch.setattr(build_macos, "build_application", _fail)
    monkeypatch.setattr(build_macos, "verify_application", _fail)
    monkeypatch.setattr(build_macos, "package_release", _fail)
    monkeypatch.setattr(build_macos, "verify_package", _fail)

    with pytest.raises(RuntimeError, match="Developer ID"):
        build_macos.pipeline(package=True)


def test_pipeline_without_package_never_requires_a_real_identity(monkeypatch) -> None:
    """Allow an ordinary local build to proceed without a Developer ID identity."""
    monkeypatch.setattr(build_macos, "get_signing_identity", lambda: None)
    order: list[str] = []
    monkeypatch.setattr(build_macos, "setup", lambda: order.append("setup"))
    monkeypatch.setattr(build_macos, "run_tests", lambda: order.append("run_tests"))
    monkeypatch.setattr(
        build_macos, "build_application", lambda: order.append("build_application")
    )
    monkeypatch.setattr(build_macos, "verify_application", lambda: order.append("verify"))

    build_macos.pipeline(package=False)

    assert order == ["setup", "run_tests", "build_application", "verify"]


def test_pipeline_skips_packaging_when_not_requested(monkeypatch) -> None:
    """Never run DMG packaging steps unless explicitly requested."""
    monkeypatch.setattr(build_macos, "setup", lambda: None)
    monkeypatch.setattr(build_macos, "run_tests", lambda: None)
    monkeypatch.setattr(build_macos, "build_application", lambda: None)
    monkeypatch.setattr(build_macos, "verify_application", lambda: None)

    def _fail():
        raise AssertionError("must not package unless requested")

    monkeypatch.setattr(build_macos, "package_release", _fail)
    monkeypatch.setattr(build_macos, "verify_package", _fail)

    build_macos.pipeline(package=False)
