"""Public-page reads must stay read-only and outside the node's private network."""
from pathlib import Path
import subprocess

import pytest

from agent.tools import ToolError, build_registry
from agent.tools.base import Permission
from agent.tools import web


def _dns(address: str):
    return [(None, None, None, None, (address, 443))]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/",
    "https://example.com:9000/", "https://user:pass@example.com/",
])
def test_rejects_nonpublic_or_unsupported_urls(monkeypatch, url):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *_a, **_kw: _dns("127.0.0.1"))
    with pytest.raises(ToolError):
        web._target(url)


def test_public_dns_is_pinned_and_curl_does_not_follow_redirect(monkeypatch):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *_a, **_kw: _dns("93.184.215.14"))
    monkeypatch.setattr(web.shutil, "which", lambda _: "/usr/bin/curl")
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        Path(command[command.index("--dump-header") + 1]).write_bytes(
            b"HTTP/2 302\r\nContent-Type: text/html\r\nLocation: http://127.0.0.1/private\r\n\r\n")
        Path(command[command.index("--output") + 1]).write_text("moved", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(web.subprocess, "run", fake_run)
    tool = build_registry().get("fetch_webpage")
    assert tool.permission == Permission.READ
    result = tool.handler({"url": "https://example.com/docs"}, None)
    assert "HTTP/2 302" in result and "跳转地址：http://127.0.0.1/private" in result
    assert "--location" not in seen["command"]
    assert seen["command"][seen["command"].index("--connect-to") + 1] == \
        ":443:93.184.215.14:443"
    assert seen["command"][-2:] == ["--", "https://example.com/docs"]


def test_public_and_private_dns_only_uses_public_address(monkeypatch):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda *_a, **_kw: _dns("10.0.0.1") + _dns("93.184.215.14"))
    assert web._target("https://example.com/") == ("example.com", 443, "93.184.215.14")
