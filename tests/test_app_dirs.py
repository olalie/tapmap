"""Test application data directory helpers."""

from pathlib import Path

import app_dirs


def test_get_app_data_dir_uses_appdata_on_windows(monkeypatch) -> None:
    """Use APPDATA on Windows."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(Path("/tmp/roaming")))

    result = app_dirs.get_app_data_dir()

    assert result == Path("/tmp/roaming") / app_dirs.APP_NAME


def test_get_app_data_dir_uses_windows_fallback_when_appdata_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Use the Windows fallback path when APPDATA is missing."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Windows")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_app_data_dir()

    assert result == tmp_path / "AppData" / "Roaming" / app_dirs.APP_NAME


def test_get_app_data_dir_uses_application_support_on_macos(
    monkeypatch, tmp_path: Path
) -> None:
    """Use Application Support on macOS."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_app_data_dir()

    assert result == tmp_path / "Library" / "Application Support" / app_dirs.APP_NAME


def test_get_app_data_dir_uses_xdg_data_home_on_linux(monkeypatch) -> None:
    """Use XDG_DATA_HOME on Linux."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(Path("/tmp/xdg-data")))

    result = app_dirs.get_app_data_dir()

    assert result == Path("/tmp/xdg-data") / app_dirs.APP_NAME


def test_get_app_data_dir_uses_linux_default_when_xdg_data_home_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Use the Linux default path when XDG_DATA_HOME is missing."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_app_data_dir()

    assert result == tmp_path / ".local" / "share" / app_dirs.APP_NAME


def test_ensure_app_data_dir_creates_directory_and_readme(tmp_path: Path) -> None:
    """Create the directory and README file."""
    app_dir = tmp_path / "TapMap"

    app_dirs.ensure_app_data_dir(app_dir)

    readme_path = app_dir / "README.txt"

    assert app_dir.is_dir()
    assert readme_path.is_file()
    assert readme_path.read_text(encoding="utf-8") == app_dirs.README_TEXT


def test_ensure_app_data_dir_does_not_overwrite_existing_readme(tmp_path: Path) -> None:
    """Preserve an existing README file."""
    app_dir = tmp_path / "TapMap"
    app_dir.mkdir(parents=True)
    readme_path = app_dir / "README.txt"
    readme_path.write_text("custom content", encoding="utf-8")

    app_dirs.ensure_app_data_dir(app_dir)

    assert readme_path.read_text(encoding="utf-8") == "custom content"


def test_get_or_create_app_data_dir_creates_directory_and_readme(
    monkeypatch, tmp_path: Path
) -> None:
    """Create and return the application data directory."""
    monkeypatch.setattr(
        app_dirs,
        "get_app_data_dir",
        lambda app_name=app_dirs.APP_NAME: tmp_path / app_name,
    )

    result = app_dirs.get_or_create_app_data_dir()

    assert result == tmp_path / app_dirs.APP_NAME
    assert result.is_dir()
    assert (result / "README.txt").read_text(encoding="utf-8") == app_dirs.README_TEXT


def test_open_folder_returns_error_when_xdg_open_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Return an error when xdg-open is unavailable."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: None)

    ok, message = app_dirs.open_folder(tmp_path)

    assert ok is False
    assert message == "xdg-open is not available on this system."


def test_open_folder_returns_success_when_xdg_open_succeeds(
    monkeypatch, tmp_path: Path
) -> None:
    """Return success when xdg-open succeeds."""

    class CompletedProcess:
        """Provide a minimal subprocess result."""

        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: "/usr/bin/xdg-open")
    monkeypatch.setattr(
        app_dirs.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(),
    )

    ok, message = app_dirs.open_folder(tmp_path)

    assert ok is True
    assert message == f"Opened: {tmp_path}"


def test_open_folder_returns_failure_message_when_xdg_open_fails(
    monkeypatch, tmp_path: Path
) -> None:
    """Return the xdg-open error details on failure."""

    class CompletedProcess:
        """Provide a minimal subprocess result."""

        returncode = 1
        stdout = ""
        stderr = "permission denied"

    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: "/usr/bin/xdg-open")
    monkeypatch.setattr(
        app_dirs.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(),
    )

    ok, message = app_dirs.open_folder(tmp_path)

    assert ok is False
    assert message == "xdg-open failed. permission denied"
