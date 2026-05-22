from __future__ import annotations

import json
import platform
import plistlib
import shlex
import shutil
import struct
import subprocess
import zlib
from pathlib import Path


APP_NAME = "GitHub AI Radar"
APP_VERSION = "0.5.0"

PIXEL_CAT = (
    "................",
    "...KK....KK.....",
    "..KGGK..KGGK....",
    "..KGGKKKKGGK....",
    ".KGGGGGGGGGGK...",
    ".KGGWGGGGWGGK...",
    ".KGGGBGGBGGGK...",
    ".KGGGGPPGGGGK...",
    ".KGGGPKKPGGGK...",
    "..KGGGWWGGGK....",
    "...KKGGGGKK.....",
    "....KYYYYK......",
    "...KGGGGGGK.....",
    "...KGG..GGK.....",
    "....KK..KK......",
    "................",
)

PIXEL_COLORS = {
    ".": (0, 0, 0, 0),
    "K": (39, 49, 66, 255),
    "G": (217, 227, 239, 255),
    "W": (255, 247, 220, 255),
    "P": (244, 163, 184, 255),
    "B": (37, 99, 235, 255),
    "Y": (246, 195, 67, 255),
}


def _apps_dir() -> Path:
    path = Path.home() / "Applications"
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_path(name: str = APP_NAME) -> Path:
    return _apps_dir() / f"{name}.app"


def install_macos_app(root: Path, port: int = 8765, name: str = APP_NAME) -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS .app launcher installation is only supported on macOS")
    app = app_path(name)
    if app.exists():
        shutil.rmtree(app)
    swiftc = shutil.which("swiftc")
    if swiftc:
        return _install_webview_bundle(app, root, port, name, swiftc)
    compiler = shutil.which("cc") or shutil.which("clang")
    if compiler:
        return _install_binary_bundle(app, root, port, name, compiler)
    osacompile = shutil.which("osacompile")
    if osacompile:
        return _install_applescript_app(app, root, port, name)
    return _install_script_bundle(app, root, port, name)


def _launcher_script(root: Path, port: int) -> str:
    cli = shutil.which("github-ai-radar") or "github-ai-radar"
    return f"""#!/bin/zsh
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
ROOT={str(root)!r}
PORT={str(port)!r}
CLI={cli!r}
LOG_DIR="$ROOT/reports/github-radar/logs"
mkdir -p "$LOG_DIR"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') launcher invoked on port $PORT" >> "$LOG_DIR/app-launcher.log"
if ! /usr/sbin/lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
  nohup "$CLI" --root "$ROOT" serve --host 127.0.0.1 --port "$PORT" >> "$LOG_DIR/app.log" 2>&1 &
  sleep 1
fi
/usr/bin/open "http://127.0.0.1:$PORT/"
"""


def _server_script(root: Path, port: int) -> str:
    cli = shutil.which("github-ai-radar") or "github-ai-radar"
    return f"""#!/bin/zsh
set -e
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
ROOT={str(root)!r}
PORT={str(port)!r}
CLI={cli!r}
LOG_DIR="$ROOT/reports/github-radar/logs"
mkdir -p "$LOG_DIR"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') native app invoked on port $PORT" >> "$LOG_DIR/app-launcher.log"
if ! /usr/sbin/lsof -iTCP:"$PORT" -sTCP:LISTEN -n -P >/dev/null 2>&1; then
  nohup "$CLI" --root "$ROOT" serve --host 127.0.0.1 --port "$PORT" >> "$LOG_DIR/app.log" 2>&1 &
  sleep 1
fi
"""


def _write_launcher(resources: Path, root: Path, port: int) -> Path:
    resources.mkdir(parents=True, exist_ok=True)
    launcher = resources / "launcher.sh"
    launcher.write_text(_launcher_script(root, port), encoding="utf-8")
    launcher.chmod(0o755)
    return launcher


def _write_server(resources: Path, root: Path, port: int) -> Path:
    resources.mkdir(parents=True, exist_ok=True)
    server = resources / "server.sh"
    server.write_text(_server_script(root, port), encoding="utf-8")
    server.chmod(0o755)
    return server


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(rgba[start : start + stride])
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(data)


def _pixel_cat_rgba(size: int) -> bytes:
    scale = size // 16
    pixels = bytearray()
    for row in PIXEL_CAT:
        expanded_row = bytearray()
        for key in row:
            expanded_row.extend(bytes(PIXEL_COLORS[key]) * scale)
        for _ in range(scale):
            pixels.extend(expanded_row)
    return bytes(pixels)


def _write_app_icon(resources: Path) -> str | None:
    iconutil = shutil.which("iconutil")
    if not iconutil:
        return None
    iconset = resources / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }
    for filename, size in sizes.items():
        _write_png(iconset / filename, size, size, _pixel_cat_rgba(size))
    output = resources / "AppIcon.icns"
    try:
        subprocess.run([iconutil, "-c", "icns", str(iconset), "-o", str(output)], check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return "AppIcon"


def _write_info_plist(contents: Path, name: str, executable_name: str, icon_file: str | None = None) -> None:
    plist = {
        "CFBundleName": name,
        "CFBundleDisplayName": name,
        "CFBundleIdentifier": "com.genbenbuxing.githubairadar",
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleVersion": APP_VERSION,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": executable_name,
        "LSMinimumSystemVersion": "10.15",
        "NSHighResolutionCapable": True,
    }
    if icon_file:
        plist["CFBundleIconFile"] = icon_file
    with (contents / "Info.plist").open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)


def _install_binary_bundle(app: Path, root: Path, port: int, name: str, compiler: str) -> Path:
    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    launcher = _write_launcher(resources, root, port)
    executable_name = "github-ai-radar-launcher"
    executable = macos / executable_name
    command = f"/bin/zsh {shlex.quote(str(launcher))} >/dev/null 2>&1 &"
    source = resources / "launcher.c"
    source.write_text(
        "#include <stdlib.h>\n"
        "int main(void) {\n"
        f"  int rc = system({json.dumps(command)});\n"
        "  return rc == -1 ? 1 : 0;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run([compiler, str(source), "-o", str(executable)], check=True)
    icon_file = _write_app_icon(resources)
    _write_info_plist(contents, name, executable_name, icon_file)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    return app


def _install_webview_bundle(app: Path, root: Path, port: int, name: str, swiftc: str) -> Path:
    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    _write_server(resources, root, port)
    executable_name = "GitHubAIRadar"
    executable = macos / executable_name
    source = resources / "GitHubAIRadar.swift"
    source.write_text(
        f"""
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate {{
    var window: NSWindow?

    func applicationDidFinishLaunching(_ notification: Notification) {{
        startServer()
        let webView = WKWebView(frame: .zero)
        let frame = NSRect(x: 0, y: 0, width: 1220, height: 820)
        let window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = {json.dumps(name)}
        window.center()
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        self.window = window
        webView.load(URLRequest(url: URL(string: "http://127.0.0.1:{port}/")!))
    }}

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {{
        return true
    }}

    private func startServer() {{
        guard let resourcePath = Bundle.main.resourcePath else {{ return }}
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/zsh")
        task.arguments = [resourcePath + "/server.sh"]
        try? task.run()
        task.waitUntilExit()
    }}
}}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
""".lstrip(),
        encoding="utf-8",
    )
    subprocess.run([swiftc, str(source), "-o", str(executable), "-framework", "Cocoa", "-framework", "WebKit"], check=True)
    icon_file = _write_app_icon(resources)
    _write_info_plist(contents, name, executable_name, icon_file)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")
    return app


def _install_applescript_app(app: Path, root: Path, port: int, name: str) -> Path:
    script = """
set launcherPath to quoted form of POSIX path of (path to resource "launcher.sh")
do shell script launcherPath
"""
    subprocess.run(["osacompile", "-o", str(app), "-e", script], check=True)
    _write_launcher(app / "Contents" / "Resources", root, port)
    info_path = app / "Contents" / "Info.plist"
    with info_path.open("rb") as handle:
        plist = plistlib.load(handle)
    plist["CFBundleName"] = name
    plist["CFBundleDisplayName"] = name
    plist["CFBundleIdentifier"] = "com.genbenbuxing.githubairadar"
    plist["CFBundleShortVersionString"] = APP_VERSION
    plist["CFBundleVersion"] = APP_VERSION
    icon_file = _write_app_icon(app / "Contents" / "Resources")
    if icon_file:
        plist["CFBundleIconFile"] = icon_file
    with info_path.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)
    return app


def _install_script_bundle(app: Path, root: Path, port: int, name: str) -> Path:
    contents = app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    executable_name = "launcher"
    executable = macos / executable_name
    executable.write_text(_launcher_script(root, port), encoding="utf-8")
    executable.chmod(0o755)
    icon_file = _write_app_icon(resources)
    _write_info_plist(contents, name, executable_name, icon_file)
    return app


def uninstall_macos_app(name: str = APP_NAME) -> Path:
    app = app_path(name)
    if app.exists():
        shutil.rmtree(app)
    return app


def macos_app_status(name: str = APP_NAME) -> dict[str, object]:
    app = app_path(name)
    return {
        "name": name,
        "path": str(app),
        "exists": app.exists(),
    }
