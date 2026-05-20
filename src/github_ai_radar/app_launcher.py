from __future__ import annotations

import json
import platform
import plistlib
import shlex
import shutil
import subprocess
from pathlib import Path


APP_NAME = "GitHub AI Radar"
APP_VERSION = "0.4.1"


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


def _write_info_plist(contents: Path, name: str, executable_name: str) -> None:
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
    _write_info_plist(contents, name, executable_name)
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
    _write_info_plist(contents, name, executable_name)
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
    _write_info_plist(contents, name, executable_name)
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
