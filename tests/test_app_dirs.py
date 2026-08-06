"""Test application data directory helpers."""

from pathlib import Path
from typing import Any

from tapmap import app_dirs


def test_get_native_app_data_dir_uses_appdata_on_windows(monkeypatch) -> None:
    """Use APPDATA on Windows."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Windows")
    monkeypatch.setenv("APPDATA", str(Path("/tmp/roaming")))

    result = app_dirs.get_native_app_data_dir()

    assert result == Path("/tmp/roaming") / app_dirs.APP_NAME


def test_get_native_app_data_dir_uses_windows_fallback_when_appdata_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Use the Windows fallback path when APPDATA is missing."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Windows")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_native_app_data_dir()

    assert result == tmp_path / "AppData" / "Roaming" / app_dirs.APP_NAME


def test_get_native_app_data_dir_uses_application_support_on_macos(
    monkeypatch, tmp_path: Path
) -> None:
    """Use Application Support on macOS."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_native_app_data_dir()

    assert result == tmp_path / "Library" / "Application Support" / app_dirs.APP_NAME


def test_get_native_app_data_dir_uses_xdg_data_home_on_linux(monkeypatch) -> None:
    """Use XDG_DATA_HOME on Linux."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(Path("/tmp/xdg-data")))

    result = app_dirs.get_native_app_data_dir()

    assert result == Path("/tmp/xdg-data") / app_dirs.APP_NAME


def test_get_native_app_data_dir_uses_linux_default_when_xdg_data_home_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Use the Linux default path when XDG_DATA_HOME is missing."""
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(app_dirs.Path, "home", lambda: tmp_path)

    result = app_dirs.get_native_app_data_dir()

    assert result == tmp_path / ".local" / "share" / app_dirs.APP_NAME


def test_ensure_app_data_dir_creates_directory_and_readme(tmp_path: Path) -> None:
    """Create the directory and README file."""
    app_dir = tmp_path / "TapMap"

    app_dirs.ensure_app_data_dir(app_dir)

    readme_path = app_dir / "README.txt"

    assert app_dir.is_dir()
    assert readme_path.is_file()
    assert readme_path.read_text(encoding="utf-8") == app_dirs.README_TEXT


def test_ensure_app_data_dir_updates_existing_readme(tmp_path: Path) -> None:
    """Update an existing README file with current content."""
    app_dir = tmp_path / "TapMap"
    app_dir.mkdir(parents=True)

    readme_path = app_dir / "README.txt"
    readme_path.write_text("custom content", encoding="utf-8")

    app_dirs.ensure_app_data_dir(app_dir)

    assert readme_path.read_text(encoding="utf-8") == app_dirs.README_TEXT


def test_ensure_native_app_data_dir_creates_directory_and_readme(
    monkeypatch, tmp_path: Path
) -> None:
    """Create and return the application data directory."""
    monkeypatch.setattr(
        app_dirs,
        "get_native_app_data_dir",
        lambda app_name=app_dirs.APP_NAME: tmp_path / app_name,
    )

    result = app_dirs.ensure_native_app_data_dir()

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


def test_reveal_in_file_manager_returns_error_when_file_is_missing(tmp_path: Path) -> None:
    """Return an error when the target file does not exist."""
    missing = tmp_path / "missing.exe"

    ok, message = app_dirs.reveal_in_file_manager(missing)

    assert ok is False
    assert message == f"File not found: {missing}"


def test_reveal_in_file_manager_selects_file_on_windows(monkeypatch, tmp_path: Path) -> None:
    """Reveal with selection via 'explorer /select,' on Windows.

    The command must be a single pre-built string, not an argv list - a list
    would be quoted as one token by subprocess on a path containing spaces,
    which Explorer's /select, parser does not accept.
    """
    target = tmp_path / "app.exe"
    target.write_text("")

    calls: list[Any] = []
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        app_dirs.subprocess, "Popen", lambda args, **kwargs: calls.append(args)
    )

    ok, message = app_dirs.reveal_in_file_manager(target)

    assert ok is True
    assert message == f"Revealed: {target}"
    assert calls == [f'explorer /select,"{target}"']
    assert isinstance(calls[0], str)


def test_reveal_in_file_manager_selects_file_on_macos(monkeypatch, tmp_path: Path) -> None:
    """Reveal with selection via 'open -R' on macOS."""
    target = tmp_path / "app.exe"
    target.write_text("")

    calls: list[list[str]] = []
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        app_dirs.subprocess, "Popen", lambda args, **kwargs: calls.append(args)
    )

    ok, message = app_dirs.reveal_in_file_manager(target)

    assert ok is True
    assert message == f"Revealed: {target}"
    assert calls == [["open", "-R", str(target)]]


def test_reveal_in_file_manager_selects_file_on_linux_via_dbus(
    monkeypatch, tmp_path: Path
) -> None:
    """Reveal with selection via the FileManager1 D-Bus interface on Linux."""

    class CompletedProcess:
        """Provide a minimal subprocess result."""

        returncode = 0
        stdout = ""
        stderr = ""

    target = tmp_path / "app.exe"
    target.write_text("")

    calls: list[list[str]] = []
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: "/usr/bin/dbus-send")

    def fake_run(args: list[str], **kwargs: Any) -> CompletedProcess:
        calls.append(args)
        return CompletedProcess()

    monkeypatch.setattr(app_dirs.subprocess, "run", fake_run)

    ok, message = app_dirs.reveal_in_file_manager(target)

    assert ok is True
    assert message == f"Revealed: {target}"
    assert calls[0][0] == "/usr/bin/dbus-send"
    assert f"array:string:{target.as_uri()}" in calls[0]


def test_reveal_in_file_manager_falls_back_to_open_folder_when_dbus_send_missing(
    monkeypatch, tmp_path: Path
) -> None:
    """Fall back to opening the containing folder when dbus-send is unavailable."""
    target = tmp_path / "app.exe"
    target.write_text("")

    calls: list[Path] = []
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        app_dirs, "open_folder", lambda p: calls.append(p) or (True, f"Opened: {p}")
    )

    ok, message = app_dirs.reveal_in_file_manager(target)

    assert ok is True
    assert message == f"Opened: {tmp_path}"
    assert calls == [tmp_path]


def test_reveal_in_file_manager_falls_back_to_open_folder_when_dbus_send_fails(
    monkeypatch, tmp_path: Path
) -> None:
    """Fall back to opening the containing folder when the D-Bus call fails."""

    class CompletedProcess:
        """Provide a minimal subprocess result."""

        returncode = 1
        stdout = ""
        stderr = "no file manager registered"

    target = tmp_path / "app.exe"
    target.write_text("")

    calls: list[Path] = []
    monkeypatch.setattr(app_dirs.platform, "system", lambda: "Linux")
    monkeypatch.setattr(app_dirs.shutil, "which", lambda name: "/usr/bin/dbus-send")
    monkeypatch.setattr(app_dirs.subprocess, "run", lambda *a, **k: CompletedProcess())
    monkeypatch.setattr(
        app_dirs, "open_folder", lambda p: calls.append(p) or (True, f"Opened: {p}")
    )

    ok, message = app_dirs.reveal_in_file_manager(target)

    assert ok is True
    assert message == f"Opened: {tmp_path}"
    assert calls == [tmp_path]
