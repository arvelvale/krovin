"""集成设置：用户自己的 Linear、Git 身份与令牌、当前工作区 / 笔记库。

面板是单租户的（一个节点一个实例），这里的设置对所有访问者生效。
存 <data_dir>/integrations.json（600 权限）。Key 和令牌只进不出：接口只回「是否已设置」，永远不回原文。
没有这个文件时一切沿用 config.py 的默认值和环境变量（演示环境）。
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from .config import Config

HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$")


class IntegrationError(Exception):
    """用户输入不合法（给面板直接显示）。"""


def _clean(value, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _host_of(value: str) -> str:
    """接受 'github.com' 或完整 URL，统一成小写主机名。"""
    raw = value.strip().lower()
    host = (urlparse(raw).hostname if "://" in raw else raw.split("/")[0].split(":")[0]) or ""
    if not HOST_RE.match(host):
        raise IntegrationError("主机名不合法，例如 github.com")
    return host


class IntegrationStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass  # Windows 没有 POSIX 权限位
        os.replace(tmp, self.path)

    # ---------------- 读 ----------------
    @property
    def onboarded(self) -> bool:
        return bool(self._data.get("onboarded"))

    def active(self, kind: str) -> str:
        return str(self._data.get(f"active_{kind}") or "demo")

    def git_identity(self) -> tuple[str, str] | None:
        g = self._data.get("git") or {}
        name, email = g.get("user_name", ""), g.get("user_email", "")
        return (name, email) if name and email else None

    def git_token(self, host: str) -> str:
        return str(((self._data.get("git") or {}).get("tokens") or {}).get(host.lower(), ""))

    def public(self, cfg: Config) -> dict:
        lin = self._data.get("linear") or {}
        g = self._data.get("git") or {}
        env_key = bool(os.environ.get("LINEAR_API_KEY"))
        return {
            "onboarded": self.onboarded,
            "linear": {
                "configured": bool(cfg.linear_key),
                "source": "panel" if lin.get("api_key") else ("env" if env_key else None),
                "team_key": cfg.linear_team_key,
                "project_name": cfg.linear_project_name,
                "demo": not lin.get("api_key"),
            },
            "git": {
                "user_name": g.get("user_name", ""),
                "user_email": g.get("user_email", ""),
                "hosts": sorted((g.get("tokens") or {}).keys()),
            },
            "active_workspace": self.active("workspace"),
            "active_vault": self.active("vault"),
        }

    # ---------------- 写 ----------------
    def set_linear(self, data: dict) -> None:
        with self._lock:
            cur = dict(self._data.get("linear") or {})
            key = _clean(data.get("api_key"), 200)
            if key:
                cur["api_key"] = key
            if not cur.get("api_key"):
                raise IntegrationError("还没填 Linear API Key（Linear → Settings → Security & access → Personal API keys）")
            team = _clean(data.get("team_key"), 20).upper()
            if not team:
                raise IntegrationError("请选择团队（Team key，例如 DAY）")
            cur["team_key"] = team
            cur["project_name"] = _clean(data.get("project_name"), 120)  # 空 = 整个团队
            self._data["linear"] = cur
            self._save()

    def clear_linear(self) -> None:
        with self._lock:
            self._data.pop("linear", None)
            self._save()

    def set_git(self, data: dict) -> None:
        with self._lock:
            g = dict(self._data.get("git") or {})
            name, email = _clean(data.get("user_name")), _clean(data.get("user_email"))
            if bool(name) != bool(email):
                raise IntegrationError("姓名和邮箱要一起填（都留空则用默认的 dgx-agent）")
            if email and not re.match(r"^[^@\s]+@[^@\s]+$", email):
                raise IntegrationError("邮箱格式不对")
            g["user_name"], g["user_email"] = name, email
            self._data["git"] = g
            self._save()

    def set_token(self, host: str, token: str) -> None:
        host = _host_of(host)
        token = token.strip()
        if not token or len(token) > 400 or re.search(r"\s", token):
            raise IntegrationError("令牌为空或含空白字符")
        with self._lock:
            g = dict(self._data.get("git") or {})
            g["tokens"] = {**(g.get("tokens") or {}), host: token}
            self._data["git"] = g
            self._save()

    def delete_token(self, host: str) -> None:
        host = _host_of(host)
        with self._lock:
            g = dict(self._data.get("git") or {})
            g["tokens"] = {k: v for k, v in (g.get("tokens") or {}).items() if k != host}
            self._data["git"] = g
            self._save()

    def set_active(self, kind: str, wid: str) -> None:
        with self._lock:
            self._data[f"active_{kind}"] = wid
            self._save()

    def set_onboarded(self, value: bool = True) -> None:
        with self._lock:
            self._data["onboarded"] = value
            self._save()

    # ---------------- 套到运行配置 ----------------
    def apply(self, cfg: Config) -> None:
        lin = self._data.get("linear") or {}
        base = getattr(cfg, "_linear_default", None) or (cfg.linear_team_key, cfg.linear_project_name)
        cfg._linear_default = base  # 记住环境变量给的演示配置，清除面板设置时恢复
        if lin.get("api_key"):
            cfg.linear_key_override = lin["api_key"]
            cfg.linear_team_key = lin.get("team_key") or base[0]
            cfg.linear_project_name = lin.get("project_name", "")
        else:
            cfg.linear_key_override = ""
            cfg.linear_team_key, cfg.linear_project_name = base
        ident = self.git_identity()
        cfg.git_name, cfg.git_email = ident if ident else ("", "")
