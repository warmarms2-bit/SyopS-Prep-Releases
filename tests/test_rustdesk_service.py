"""Tests del servicio RustDesk sin Qt, red ni instaladores reales."""

import plistlib
import subprocess


def test_config_for_platform():
    from services.rustdesk_service import config_for_platform

    mac = config_for_platform("darwin")
    win = config_for_platform("win32")
    assert mac.filename == "rustdesk.dmg"
    assert mac.url.endswith("aarch64.dmg")
    assert win.filename == "rustdesk.msi"
    assert win.url.endswith(".msi")


def test_install_macos_copia_y_desmonta(monkeypatch, tmp_path):
    from services import rustdesk_service as service

    mount = tmp_path / "RustDesk Volume"
    app = mount / "RustDesk.app"
    app.mkdir(parents=True)
    (app / "Contents.txt").write_text("ok", encoding="utf-8")
    destination = tmp_path / "Applications" / "RustDesk.app"
    plist = plistlib.dumps({"system-entities": [{"mount-point": str(mount)}]})
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == "hdiutil" and "attach" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=plist, stderr=b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(service.subprocess, "run", fake_run)
    assert service.install_macos(tmp_path / "rustdesk.dmg", destination) is True
    assert (destination / "Contents.txt").read_text(encoding="utf-8") == "ok"
    assert any(cmd[0] == "hdiutil" and "detach" in cmd for cmd in calls)


def test_install_windows_exit_code(monkeypatch, tmp_path):
    from services import rustdesk_service as service

    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0),
    )
    assert service.install_windows(tmp_path / "rustdesk.msi") is True


def test_install_windows_fallo(monkeypatch, tmp_path):
    from services import rustdesk_service as service

    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1603),
    )
    assert service.install_windows(tmp_path / "rustdesk.msi") is False
