"""Read a public webpage with curl, without exposing the node's internal network."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urlsplit

from .base import Permission, Tool, ToolError, arg, params, subprocess_env

MAX_BYTES = 256 * 1024
MAX_CHARS = 16000


def _target(url: str) -> tuple[str, int, str]:
    if len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise ToolError("网址太长或包含控制字符")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise ToolError(f"网址格式无效：{exc}") from exc
    if parsed.scheme not in ("http", "https") or not host or parsed.username or parsed.password:
        raise ToolError("只支持无需登录的公开 HTTP(S) 网页")
    port = port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        raise ToolError("网页只允许使用 80 或 443 端口")
    try:
        host.encode("ascii")
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (UnicodeError, OSError) as exc:
        raise ToolError(f"无法解析公开网页域名：{exc}") from exc
    public = sorted({ipaddress.ip_address(item[4][0]) for item in addresses if ipaddress.ip_address(item[4][0]).is_global},
                    key=lambda ip: (ip.version != 4, str(ip)))
    if not public:
        raise ToolError("已拒绝访问内网、回环或非公开地址")
    ip = str(public[0])
    return host, port, f"[{ip}]" if public[0].version == 6 else ip


def _loopback_proxy() -> str | None:
    value = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1") \
                and parsed.port and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def fetch_webpage(args: dict, _ctx) -> str:
    url = str(arg(args, "url", required=True)).strip()
    host, port, ip = _target(url)
    curl = shutil.which("curl")
    if not curl:
        raise ToolError("节点没有 curl 命令")
    with tempfile.TemporaryDirectory(prefix="krovin-web-") as tmp:
        headers = Path(tmp) / "headers"
        body = Path(tmp) / "body"
        command = [curl, "--disable", "--silent", "--show-error", "--request", "GET",
                   "--proto", "=http,https", "--connect-timeout", "8", "--max-time", "25",
                   "--max-filesize", str(MAX_BYTES), "--connect-to", f":{port}:{ip}:{port}",
                   "--dump-header", str(headers), "--output", str(body)]
        proxy = _loopback_proxy()
        if proxy:
            command += ["--proxy", proxy]
        command += ["--", url]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    env=subprocess_env(), timeout=30)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("读取网页超时（30 秒）") from exc
        if result.returncode:
            raise ToolError(f"curl 失败（退出码 {result.returncode}）：{result.stderr.strip()[-300:]}")
        blocks = [b for b in headers.read_text(encoding="iso-8859-1").replace("\r\n", "\n").split("\n\n") if b.strip()]
        header = blocks[-1] if blocks else ""
        lines = header.splitlines()
        status = lines[0] if lines else "HTTP 状态未知"
        fields = {k.lower(): v.strip() for line in lines[1:] if ":" in line for k, v in [line.split(":", 1)]}
        content_type = fields.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type and not (content_type.startswith("text/") or content_type in
                                 {"application/json", "application/xml", "application/xhtml+xml", "application/javascript"}):
            return f"{status}\n内容类型：{content_type}（非文本内容，未读取正文）"
        data = body.read_bytes()
        if b"\x00" in data:
            raise ToolError("网页正文不是可读文本")
        content = data.decode("utf-8", errors="replace")
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS] + "\n…（正文已截断）"
        location = fields.get("location")
        return f"{status}\n网址：{url}" + (f"\n跳转地址：{location}（请单独读取，工具不会自动跟随跳转）" if location else "") \
            + f"\n\n{content or '（无正文）'}"


TOOLS = [Tool("fetch_webpage",
              "使用 curl 只读公开 HTTP(S) 网页。仅允许 80/443 端口，拒绝内网地址；不带登录凭据、不自动跟随跳转。"
              "适合查网页资料或读取公开文档；返回状态和最多 16000 字正文。",
              params({"url": {"type": "string", "description": "公开网页的完整 http:// 或 https:// 地址"}}, ["url"]),
              Permission.READ, fetch_webpage)]
