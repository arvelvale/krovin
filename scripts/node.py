"""节点操作：同步代码、带隧道执行命令。凭据只从本地登录表读取，不打印。

  python scripts/node.py sync                 # 把仓库（含未提交改动，不含 var/ 与被忽略文件）同步到节点 ~/dgx-agent
  python scripts/node.py run "python3 -m agent doctor"
  python scripts/node.py run --no-tunnel "nvidia-smi"
  python scripts/node.py serve                # 在节点上起 Web 面板，并把本机 127.0.0.1:9000 转发过去
  python scripts/node.py preflight            # 评审前自检（代理、JEV / Linear、SSH、口令、前端）
  python scripts/node.py serve --public --keep-alive   # 评审期间常驻：断线重连、不让电脑睡眠（或双击 serve-for-judges.bat）

个人使用（不同步代码、不挂公网）：面板常驻在节点的 tmux 里，本机只需要维持一条反向隧道：
  python scripts/node.py daemon start [--sync]   # 在节点 tmux 会话 krovin 里起面板（只听 127.0.0.1，固定走隧道端口 10090）
  python scripts/node.py daemon status|stop|logs
  python scripts/node.py tunnel                  # 本机反向隧道 + 本机 127.0.0.1:9000 转发；断线自动重连（双击 krovin-tunnel.bat）

隧道：节点 127.0.0.1:<随机端口> → SSH → 本机代理（从 HTTPS_PROXY 读，默认 127.0.0.1:10090）。
节点直连不了境外（JEV、Linear），agent 进程靠 https_proxy 走这条隧道；StepFun 与本地模型直连不受影响。
只影响本次执行的命令，不改节点任何系统或网络配置。
"""
from __future__ import annotations

import argparse
import io
import os
import select
import shlex
import socket
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import openpyxl
import paramiko

ROOT = Path(__file__).resolve().parents[1]
REMOTE_DIR = "dgx-agent"


def local_proxy() -> tuple[str, int]:
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:10090"
    u = urlparse(raw)
    return u.hostname or "127.0.0.1", u.port or 10090


def _sheet() -> tuple[str, int, dict]:
    rows = list(openpyxl.load_workbook(ROOT / "登录信息表.xlsx", read_only=True, data_only=True).active.values)
    values = {str(r[0]): r[1] for r in rows if r[0] is not None}
    host, port = rows[3][1].rsplit(":", 1)
    return host, int(port), values


# 组委会的端口映射：节点内端口 → 公网端口前缀，后两位跟 SSH 公网端口一致（本节点 SSH 6006 → 服务 7006/8006/9006）
PUBLIC_PREFIX = {7000: 7000, 8888: 8000, 9000: 9000}


def public_url(node_port: int) -> str | None:
    """节点内端口在公网上的地址；这个端口没做映射就返回 None。"""
    host, ssh_port, _ = _sheet()
    if node_port not in PUBLIC_PREFIX:
        return None
    return f"http://{host}:{PUBLIC_PREFIX[node_port] + ssh_port % 100}"


def connect() -> paramiko.SSHClient:
    host, port, values = _sheet()
    if port != 6006:
        raise RuntimeError("登录表里的端口不是指定的 6006")
    client = paramiko.SSHClient()
    client.load_host_keys(str(ROOT / ".ssh_known_hosts"))  # 首次连接时由 node_admin.py 记录
    client.connect(host, port=6006, username=values["用户名"], password=values["密码"], timeout=20,
                   look_for_keys=False, allow_agent=False)
    client.get_transport().set_keepalive(30)
    return client


def _pipe(chan, target):
    try:
        sock = socket.create_connection(target, timeout=10)
    except OSError:
        chan.close()
        return
    try:
        while True:
            r, _, _ = select.select([sock, chan], [], [], 60)
            if not r:
                continue
            if sock in r:
                data = sock.recv(65536)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(65536)
                if not data:
                    break
                sock.sendall(data)
    finally:
        chan.close()
        sock.close()


def open_tunnel(client: paramiko.SSHClient, port: int = 0) -> int:
    """在节点回环地址上开反向转发，返回端口号。port=0 由节点分配（多个会话并行也不冲突）；
    个人使用的常驻面板要一个固定端口，重连后它的 https_proxy 才不用改。"""
    target = local_proxy()
    return client.get_transport().request_port_forward(
        "127.0.0.1", port,
        lambda ch, origin, dest: threading.Thread(target=_pipe, args=(ch, target), daemon=True).start())


class LocalForward:
    """本机 127.0.0.1:local_port → 节点 127.0.0.1:remote_port（相当于 ssh -L）。
    端口只 bind 一次；SSH 重连后把新连接赋给 .client，转发继续可用。"""

    def __init__(self, client: paramiko.SSHClient, local_port: int, remote_port: int):
        self.client = client
        self.remote_port = remote_port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", local_port))
        self.server.listen(32)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while True:
            try:
                sock, peer = self.server.accept()
            except OSError:
                continue
            try:
                chan = self.client.get_transport().open_channel("direct-tcpip", ("127.0.0.1", self.remote_port), peer)
            except Exception:
                sock.close()  # SSH 正在重连：这次请求失败，浏览器重试即可
                continue
            threading.Thread(target=_bridge, args=(sock, chan), daemon=True).start()


def forward_local(client: paramiko.SSHClient, local_port: int, remote_port: int) -> LocalForward:
    return LocalForward(client, local_port, remote_port)


def _bridge(sock: socket.socket, chan) -> None:
    try:
        while True:
            r, _, _ = select.select([sock, chan], [], [], 60)
            if sock in r:
                data = sock.recv(65536)
                if not data:
                    break
                chan.sendall(data)
            if chan in r:
                data = chan.recv(65536)
                if not data:
                    break
                sock.sendall(data)
    except OSError:
        pass
    finally:
        chan.close()
        sock.close()


def run(cmd: str, tunnel: bool = True, cwd: str = REMOTE_DIR, timeout: int = 3600,
        pty: bool = False, client: paramiko.SSHClient | None = None) -> int:
    client = client or connect()
    try:
        prefix = f"cd ~/{cwd} 2>/dev/null || cd ~; export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8; "
        if tunnel:
            p = f"http://127.0.0.1:{open_tunnel(client)}"
            prefix += f"export https_proxy={p} http_proxy={p} no_proxy=127.0.0.1,localhost; "
        chan = client.get_transport().open_session()
        if pty:  # 有 pty 时 SSH 断开会给远端进程发 SIGHUP，服务跟着退出，不会遗留在节点上
            chan.get_pty()
        chan.set_combine_stderr(True)
        chan.settimeout(timeout)
        chan.exec_command(prefix + cmd)
        out = sys.stdout.buffer
        while True:
            data = chan.recv(4096)
            if not data:
                break
            out.write(data)
            out.flush()
        return chan.recv_exit_status()
    finally:
        client.close()


def sync() -> None:
    files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True,
                           check=True).stdout.decode("utf-8").split("\0")
    dist = ROOT / "web" / "dist"  # 前端构建产物不入库，但节点上要用（节点没有 node）
    if dist.exists():
        files += [p.relative_to(ROOT).as_posix() for p in dist.rglob("*") if p.is_file()]
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel in filter(None, files):
            path = ROOT / rel
            if path.is_file():
                tar.add(path, arcname=rel)
    client = connect()
    try:
        sftp = client.open_sftp()
        client.exec_command(f"mkdir -p ~/{REMOTE_DIR}")[1].channel.recv_exit_status()
        home = sftp.normalize(".")
        remote_tar = f"{home}/{REMOTE_DIR}/.sync.tar.gz"
        buf.seek(0)
        sftp.putfo(buf, remote_tar)
        env_file = ROOT / ".env"
        if env_file.exists():
            with sftp.open(f"{home}/{REMOTE_DIR}/.env", "w") as fh:
                fh.write(env_file.read_bytes())
            sftp.chmod(f"{home}/{REMOTE_DIR}/.env", 0o600)
        # 只覆盖同步的文件，不删节点上的 var/（记忆库、轨迹、工作区）
        _, out, err = client.exec_command(
            f"cd ~/{REMOTE_DIR} && rm -rf web/dist && tar xzf .sync.tar.gz && rm .sync.tar.gz && echo synced $(find . -path ./var -prune -o -type f -print | wc -l) files")
        print(out.read().decode().strip(), err.read().decode().strip())
    finally:
        client.close()


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _via_proxy(url: str, timeout: float = 8.0) -> str | None:
    """经本机代理访问境外服务，能拿到任何 HTTP 响应就算通（返回 None），否则返回原因。"""
    import urllib.error
    import urllib.request
    host, port = local_proxy()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": f"http://{host}:{port}"}))
    why = ""
    for _ in range(2):  # 代理偶尔第一下连接失败，重试一次再判不通，免得评审当天误报
        try:
            opener.open(url, timeout=timeout)
            return None
        except urllib.error.HTTPError:
            return None  # 400 / 401 / 404 也说明网络是通的
        except Exception as exc:  # noqa: BLE001
            why = str(getattr(exc, "reason", exc))[:80]
    return why


def preflight() -> bool:
    """评审前自检：本机这一侧的条件都满足，节点上的 agent 才能用上 JEV 和 Linear。"""
    ok = True

    def line(good: bool, what: str, hint: str = "") -> None:
        nonlocal ok
        ok = ok and good
        tail = "" if good or not hint else "\n    → " + hint
        print(("✓ " if good else "✗ ") + what + tail, flush=True)

    line((ROOT / "登录信息表.xlsx").exists(), "登录信息表在仓库根目录", "从组委会材料里放回 登录信息表.xlsx")
    token = ""
    env_file = ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            if raw.startswith("AGENT_WEB_TOKEN="):
                token = raw.split("=", 1)[1].strip()
    line(bool(token), ".env 里固定了面板口令 AGENT_WEB_TOKEN", "不固定的话每次启动随机生成，评委手里的口令会失效")
    line((ROOT / "web" / "dist" / "index.html").exists(), "前端已构建（web/dist）", "cd web && npm install && npm run build")
    host, port = local_proxy()
    has_proxy = _port_open(host, port)
    line(has_proxy, f"本机代理在监听 {host}:{port}", "打开 mihomo / Clash（节点经它访问 JEV 和 Linear）")
    if has_proxy:
        for name, url in (("JEV", "https://api.typesafe.ai/"), ("Linear", "https://api.linear.app/graphql")):
            why = _via_proxy(url)
            line(why is None, f"经代理能连上 {name}", f"代理规则没放行，或网络不通：{why}")
    try:
        connect().close()
        line(True, "SSH 能连上节点（6006）")
    except Exception as exc:  # noqa: BLE001
        line(False, "SSH 能连上节点（6006）", str(exc)[:120])
    return ok


def _keep_awake(on: bool) -> None:
    """Windows：本进程运行期间不让系统睡眠（进程退出即恢复，不改任何系统设置）。合盖是否睡眠仍由电源设置决定。"""
    if sys.platform != "win32":
        return
    import ctypes
    es_continuous, es_system_required = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(es_continuous | (es_system_required if on else 0))


def _watch(url: str | None, stop: threading.Event) -> None:
    """每分钟看一眼：本机代理、公网入口。状态变化才打印，避免刷屏。"""
    import time
    host, port = local_proxy()
    last: dict[str, bool] = {}
    while not stop.wait(60):
        now = {"本机代理": _port_open(host, port)}
        if url:
            u = urlparse(url)
            now["公网入口"] = _port_open(u.hostname or "", u.port or 80, timeout=5)
        for k, v in now.items():
            if last.get(k) != v:
                note = "" if v or k != "本机代理" else "（JEV / Linear 会降级：写操作全改为人工确认）"
                print(f"[{time.strftime('%H:%M')}] {k}：{'正常' if v else '不通'}{note}", flush=True)
        last = now


def serve_forever(port: int, local_port: int, public: bool, extra: str) -> int:
    """评审期间用：SSH 断了自动重连，面板随之重启；登录态已落盘，评委不用重新登录。Ctrl+C 结束。"""
    import time
    host = "0.0.0.0" if public else "127.0.0.1"
    url = public_url(port) if public else None
    if url:
        extra += f" --public-url {shlex.quote(url)}"
    _keep_awake(True)
    stop = threading.Event()
    threading.Thread(target=_watch, args=(url, stop), daemon=True).start()
    fwd: LocalForward | None = None
    delay = 5
    try:
        while True:
            try:
                client = connect()
            except Exception as exc:  # noqa: BLE001
                print(f"[{time.strftime('%H:%M:%S')}] 连不上节点：{str(exc)[:100]}，{delay} 秒后重试", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            delay = 5
            if fwd is None:
                fwd = forward_local(client, local_port, port)
                print(f"本机访问：http://127.0.0.1:{local_port}" + (f"　公网访问：{url}" if url else ""), flush=True)
            else:
                fwd.client = client
            print(f"[{time.strftime('%H:%M:%S')}] 已连上节点，启动面板（这个窗口不要关）", flush=True)
            started = time.monotonic()
            try:
                run(f"python3 -m agent serve --host {host} --port {port}{extra}", tunnel=True, pty=True, client=client)
            except Exception as exc:  # noqa: BLE001  网络断开时 recv 可能直接抛异常
                print(f"[{time.strftime('%H:%M:%S')}] 连接异常：{str(exc)[:100]}", flush=True)
            lived = time.monotonic() - started
            wait = 5 if lived > 30 else 20  # 刚起就挂说明有别的问题，放慢一点
            print(f"[{time.strftime('%H:%M:%S')}] 连接断开（运行了 {lived / 60:.0f} 分钟），{wait} 秒后自动重连", flush=True)
            time.sleep(wait)
    except KeyboardInterrupt:
        print("已停止。节点上的面板随 SSH 断开一起退出。", flush=True)
        return 0
    finally:
        stop.set()
        _keep_awake(False)


# ---------------- 个人使用：面板常驻节点 + 本机只维持反向隧道 ----------------
DAEMON_SESSION = "krovin"
TUNNEL_PORT = 10090  # 节点上的固定隧道端口；常驻面板的 https_proxy 指向它


def _ssh(client: paramiko.SSHClient, cmd: str, timeout: int = 60) -> tuple[int, str]:
    _, out, err = client.exec_command(cmd, timeout=timeout)
    text = out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")
    return out.channel.recv_exit_status(), text.strip()


def _token_configured() -> bool:
    env_file = ROOT / ".env"
    return env_file.exists() and any(line.startswith("AGENT_WEB_TOKEN=") and line.split("=", 1)[1].strip()
                                     for line in env_file.read_text(encoding="utf-8").splitlines())


def daemon(action: str, port: int, remote_port: int, do_sync: bool) -> int:
    """节点上的常驻面板（tmux 会话 krovin）。它不依赖本机的 SSH 连接；JEV / Linear 走固定端口的反向隧道，
    隧道断了这两项暂时不可用（写操作全改人工确认），恢复后自动可用，不用重启面板。"""
    sess = DAEMON_SESSION
    if action == "start" and do_sync:
        sync()
    client = connect()
    try:
        if action == "status":
            rc, _ = _ssh(client, f"tmux has-session -t {sess}")
            _, code = _ssh(client, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/api/status")
            _, tun = _ssh(client, f"ss -ltn | grep -c '127.0.0.1:{remote_port} '")
            print(f"面板进程（tmux {sess}）：{'在运行' if rc == 0 else '没有运行'}")
            print(f"面板 http://127.0.0.1:{port}（节点上）：{'可访问' if code in ('200', '401') else '不通'}")
            print(f"反向隧道 {remote_port}：{'已连上（JEV / Linear 可用）' if tun.strip() not in ('', '0') else '没连（先运行 krovin-tunnel.bat，JEV / Linear 暂不可用）'}")
            return 0 if rc == 0 else 1
        if action == "logs":
            _, text = _ssh(client, f"tmux capture-pane -p -t {sess} -S -60")
            print(text)
            return 0
        if action == "stop":
            rc, _ = _ssh(client, f"tmux kill-session -t {sess}")
            print("已停止" if rc == 0 else "本来就没在运行")
            return 0
        if action == "start":
            if not _token_configured():
                print("先在 .env 里设 AGENT_WEB_TOKEN（常驻面板要一个固定口令，不然每次重启都变）")
                return 1
            rc, _ = _ssh(client, f"tmux has-session -t {sess}")
            if rc == 0:
                print(f"已经在运行了（tmux {sess}）。要重启请先 daemon stop，或用 daemon start --sync 更新代码后重启")
                return 0
            _, busy = _ssh(client, f"ss -ltn | grep -c ':{port} '")
            if busy.strip() not in ("", "0"):
                print(f"节点上的 {port} 端口已经有别的进程在监听（可能是评审服务 serve-for-judges 正在跑）。先停掉它，或者换 --port")
                return 1
            proxy = f"http://127.0.0.1:{remote_port}"
            inner = (f"cd ~/{REMOTE_DIR} && export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 https_proxy={proxy} http_proxy={proxy} "
                     f"no_proxy=127.0.0.1,localhost && exec python3 -m agent serve --host 127.0.0.1 --port {port}")
            rc, text = _ssh(client, f"tmux new-session -d -s {sess} {shlex.quote(inner)}")
            if rc != 0:
                print("启动失败：" + text)
                return 1
            import time
            time.sleep(4)
            rc, _ = _ssh(client, f"tmux has-session -t {sess}")
            if rc != 0:
                print("面板启动后马上退出了，看不到日志；用 node.py run 手动运行 python3 -m agent serve 看报错")
                return 1
            print(f"面板已在节点常驻（tmux {sess}，只听 127.0.0.1:{port}）。接下来运行 krovin-tunnel.bat，浏览器打开 http://127.0.0.1:9000")
            return 0
    finally:
        client.close()
    return 2


def tunnel_forever(remote_port: int, local_port: int, remote_panel_port: int, forward: bool) -> int:
    """个人使用：只维持两样东西——节点到本机代理的反向隧道（JEV / Linear 靠它）、本机到节点面板的转发（可选）。
    不同步代码，也不启动面板。断线自动重连；运行期间电脑不睡眠。Ctrl+C 结束。"""
    import time
    _keep_awake(True)
    stop = threading.Event()
    threading.Thread(target=_watch, args=(None, stop), daemon=True).start()
    fwd: LocalForward | None = None
    delay = 5
    try:
        while True:
            try:
                client = connect()
            except Exception as exc:  # noqa: BLE001
                print(f"[{time.strftime('%H:%M:%S')}] 连不上节点：{str(exc)[:100]}，{delay} 秒后重试", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            delay = 5
            ok = False
            for attempt in range(12):  # 上一条连接刚断时，节点上的旧转发要几十秒才释放
                try:
                    open_tunnel(client, remote_port)
                    ok = True
                    break
                except Exception:  # noqa: BLE001
                    if attempt == 0:
                        print(f"[{time.strftime('%H:%M:%S')}] 节点上的端口 {remote_port} 还被旧连接占着，等它释放…", flush=True)
                    time.sleep(5)
            if not ok:
                print(f"隧道端口 {remote_port} 一直被占用：节点上是不是有别的程序在用？可以用 --remote-port 换一个（同时要改 daemon 的 --remote-port）", flush=True)
                client.close()
                time.sleep(15)
                continue
            if forward:
                if fwd is None:
                    fwd = forward_local(client, local_port, remote_panel_port)
                else:
                    fwd.client = client
            host, port = local_proxy()
            print(f"[{time.strftime('%H:%M:%S')}] 隧道已连上：节点 127.0.0.1:{remote_port} → 本机代理 {host}:{port}（JEV / Linear 走这里）", flush=True)
            if forward:
                print(f"    面板：浏览器打开 http://127.0.0.1:{local_port}", flush=True)
            rc, _ = _ssh(client, f"tmux has-session -t {DAEMON_SESSION}")
            if rc != 0:
                print("    提示：节点上的面板还没有启动，先运行 krovin-panel.bat（只需要做一次）", flush=True)
            print("    这个窗口保持打开；关掉后 JEV / Linear 暂时不可用（聊天和改代码照常）。Ctrl+C 结束。", flush=True)
            started = time.monotonic()
            while client.get_transport() and client.get_transport().is_active():
                time.sleep(3)
            print(f"[{time.strftime('%H:%M:%S')}] 连接断开（保持了 {(time.monotonic() - started) / 60:.0f} 分钟），自动重连…", flush=True)
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(5)
    except KeyboardInterrupt:
        print("已停止。", flush=True)
        return 0
    finally:
        stop.set()
        _keep_awake(False)


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync")
    r = sub.add_parser("run")
    r.add_argument("--no-tunnel", action="store_true")
    r.add_argument("command")
    sv = sub.add_parser("serve")
    sv.add_argument("--port", type=int, default=9000, help="节点上的端口")
    sv.add_argument("--local-port", type=int, default=9000, help="本机转发端口")
    sv.add_argument("--public", action="store_true", help="监听 0.0.0.0（公网映射端口，必须有口令）")
    sv.add_argument("--dev-no-auth", action="store_true", help="开发用免登录（不能和 --public 一起用）")
    sv.add_argument("--keep-alive", action="store_true", help="评审用：断线自动重连、运行期间不让电脑睡眠")
    sub.add_parser("preflight", help="评审前自检：代理、JEV / Linear 连通、SSH、口令、前端构建")
    tn = sub.add_parser("tunnel", help="个人使用：只维持反向隧道（JEV / Linear）和本机到面板的转发，断线自动重连")
    tn.add_argument("--remote-port", type=int, default=TUNNEL_PORT, help="节点上的隧道端口（常驻面板的 https_proxy 指向它）")
    tn.add_argument("--local-port", type=int, default=9000, help="本机转发端口")
    tn.add_argument("--panel-port", type=int, default=9000, help="节点上面板的端口")
    tn.add_argument("--no-forward", action="store_true", help="不转发面板（面板已经通过别的方式能访问）")
    dm = sub.add_parser("daemon", help="个人使用：面板常驻节点 tmux 会话 krovin")
    dm.add_argument("action", choices=["start", "stop", "status", "logs"])
    dm.add_argument("--port", type=int, default=9000, help="节点上面板的端口")
    dm.add_argument("--remote-port", type=int, default=TUNNEL_PORT)
    dm.add_argument("--sync", action="store_true", help="start 之前先同步代码")
    args = p.parse_args()
    if args.cmd == "tunnel":
        return tunnel_forever(args.remote_port, args.local_port, args.panel_port, not args.no_forward)
    if args.cmd == "daemon":
        return daemon(args.action, args.port, args.remote_port, args.sync)
    if args.cmd == "preflight":
        return 0 if preflight() else 1
    if args.cmd == "sync":
        sync()
        return 0
    if args.cmd == "serve" and args.keep_alive:
        return serve_forever(args.port, args.local_port, args.public, " --dev-no-auth" if args.dev_no_auth else "")
    if args.cmd == "serve":
        client = connect()
        forward_local(client, args.local_port, args.port)
        host = "0.0.0.0" if args.public else "127.0.0.1"
        print(f"本机访问：http://127.0.0.1:{args.local_port}（Ctrl+C 结束，节点上的服务随之退出）", flush=True)
        extra = " --dev-no-auth" if args.dev_no_auth else ""
        if args.public:
            url = public_url(args.port)
            if url:
                print(f"公网访问：{url}", flush=True)
                extra += f" --public-url {shlex.quote(url)}"
            else:
                print(f"提醒：节点端口 {args.port} 没有公网映射（只有 7000 / 8888 / 9000 有），外网打不开", flush=True)
        return run(f"python3 -m agent serve --host {host} --port {args.port}{extra}", tunnel=True, pty=True,
                   client=client)
    return run(args.command, tunnel=not args.no_tunnel)


if __name__ == "__main__":
    sys.exit(main())
