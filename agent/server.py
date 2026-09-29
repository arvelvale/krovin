"""Web 面板后端：标准库 HTTP + SSE，节点上零安装。

  python -m agent serve                          # 127.0.0.1:9000，经 SSH 隧道访问
  python -m agent serve --host 0.0.0.0           # 公网映射端口，必须带 token（默认就强制）

接口（除登录外都要登录 cookie）：
  POST   /api/login                        {token} → 设置 HttpOnly cookie
  GET    /api/status                       服务状态、技能清单
  GET    /api/sessions                     历史会话（var/runs 下全部，含命令行跑的）
  POST   /api/sessions                     {use_jev, tier, yolo, workspace} 新建在线会话
  GET    /api/sessions/<id>                轨迹 + 对话 + 工作记忆（在线会话还有待确认项）
  PATCH  /api/sessions/<id>                {tier?, yolo?, title?} 改模型档位 / 开关全自动（开启时把已在等的确认一并同意）/ 改会话名
  DELETE /api/sessions/<id>                删除会话（轨迹和对话一并删除；正在进行的会话不能删）
  POST   /api/sessions/<id>/turn           {text, source} 开始一轮（后台执行，进度走 SSE）
  GET    /api/sessions/<id>/stream         SSE：trace / confirm / confirm_resolved / working / turn_done
  POST   /api/sessions/<id>/confirm        {id, approve} 回答写操作确认
POST   /api/sessions/<id>/stop           停止当前轮（步边界收尾；等待中的确认按拒绝）
  GET    /api/memory?status=active|pending
  POST   /api/memory/<id>/approve    DELETE /api/memory/<id>
  POST   /api/asr?format=wav               请求体是音频字节 → {text}
  POST   /api/demo/reset                   重建演示仓库（仅限 var/workspace/ 下的沙盒；有对话进行中时拒绝）
  GET    /api/models                       模型设置（供应商、分工位、预设；不含 Key 原文）
  PUT    /api/models/slots                 {local|backup|cloud: {provider, model}}
  PUT    /api/models/providers/<id>        {name, base_url, api_key?, private, use_proxy, models:[{name, max_tokens}]}
  DELETE /api/models/providers/<id>
  POST   /api/models/providers/<id>/discover   拉取模型列表
  POST   /api/models/providers/<id>/test       {model} 发一句话试连通
  GET    /api/workspaces                   工作区 / 笔记库列表 + 当前选中
  POST   /api/workspaces                   {name, kind, mode: empty|clone, url?, branch?} 新建 / 克隆
  POST   /api/workspaces/upload?name=&kind=   请求体是 zip → 导入本地文件夹
  POST   /api/workspaces/folder?name=&kind=   开始逐文件上传 → {id}；PUT /<id>/file?path= 传文件；POST /<id>/finish 收尾
  POST   /api/workspaces/<id>/activate|pull   设为当前 / 从 git 远端同步；DELETE /<id> 删除
  GET    /api/workspaces/<id>/tree|file|raw|changes|zip   看目录、看文件、原始字节、相对导入快照的改动、打包下载
  POST   /api/workspaces/<id>/preview      {path?} → {url}：给工作区里的网页（html / CDN 版 React、Vue）发一个 2 小时有效的预览地址
  GET    /preview/<token>/<path>           预览静态文件：凭地址里的令牌访问（不带 cookie），响应带 CSP sandbox，页面脚本拿不到面板的任何权限
  GET    /api/integrations                 Linear / Git / 引导状态（不含 Key 与令牌原文）
  PUT    /api/integrations/linear          {api_key?, team_key, project_name}；DELETE 恢复演示配置；POST /discover 拉团队和项目
  PUT    /api/integrations/git             {user_name, user_email}；PUT|DELETE /git/tokens/<host> 私有仓库令牌
  PUT    /api/integrations/onboarded       {done}

SSE 推送的 trace 事件就是决策轨迹原样（docs/接口/03-决策轨迹格式.md），面板和 A/B 读的是同一份数据。
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from .asr import AsrError, transcribe
from .config import ROOT, Config
from .gate import ConfirmRequest
from .integrations import IntegrationError, IntegrationStore
from .images import ImageError, MAX_IMAGE, read_image, save_image, validate_images
from .kernel import Agent
from .llm import LLMClient, LLMError
from .memory import MemoryStore
from .models import ModelConfigError, ModelStore, discover_models
from .router import ModelRouter
from .skills import load_skills
from .tools import build_registry
from .tools.base import ToolError, safe_path
from .tools.linear import LinearClient
from .workspaces import WorkspaceError, WorkspaceStore
from .sandbox import get_sandbox, SandboxError

COOKIE = "dgx_session"
SESSION_ID = re.compile(r"^s-[\w-]{4,64}$")
CONFIRM_TIMEOUT = 600          # 秒；超时按拒绝处理
MAX_JSON = 1 * 1024 * 1024
MAX_AUDIO = 12 * 1024 * 1024
PREVIEW_TTL = 2 * 3600
HOST_OK = re.compile(r"^[A-Za-z0-9.\-\[\]:]{1,100}$")


def preview_csp(host: str) -> str:
    """预览页的 CSP。sandbox 让页面成为不透明源，此时 'self' 不再匹配同站资源，所以要把本机地址明写进去。"""
    me = host if HOST_OK.match(host or "") else "'self'"
    return ("sandbox allow-scripts allow-modals allow-forms allow-pointer-lock; "
            f"default-src {me} https: data: blob:; script-src {me} 'unsafe-inline' 'unsafe-eval' https: blob:; "
            f"style-src {me} 'unsafe-inline' https:; img-src * data: blob:; font-src * data:; "
            f"media-src * data: blob:; connect-src {me} https: wss:")  # 不写 frame-ancestors：沙盒 iframe 里 'self' 会误判成非同源
MAX_ZIP = 200 * 1024 * 1024
MAX_FILE_UPLOAD = 20 * 1024 * 1024
WS_ID = re.compile(r"^[a-z0-9-]{1,40}$")
INTERNAL_PREFIX = "（系统提示）"  # kernel 注入的内部提示，不显示成用户消息
DIST = ROOT / "web" / "dist"


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


class LiveSession:
    """一个在线会话：一个 Agent + SSE 订阅者 + 等待网页回答的写操作确认。"""

    def __init__(self, cfg: Config, use_jev: bool, tier: str | None, factory=Agent, session: str | None = None):
        self.subs: list[queue.Queue] = []
        self.pending: dict[str, dict] = {}
        self.busy = False
        self.use_jev = use_jev
        self._lock = threading.Lock()
        self.agent = factory(cfg, confirm=self._confirm, use_jev=use_jev, force_tier=tier,
                             **({"session": session} if session else {}))
        self.agent.trace.subscribe(self._on_trace)
        self.agent.reasoning_listener = lambda item: self.publish("reasoning", item)

    @property
    def id(self) -> str:
        return self.agent.session

    def publish(self, kind: str, data) -> None:
        for q in list(self.subs):
            try:
                q.put_nowait((kind, data))
            except queue.Full:
                pass

    def _on_trace(self, ev: dict) -> None:
        self.publish("trace", ev)
        if ev["type"] in ("tool.call", "turn.end", "context.compress"):
            self.publish("working", self.agent.working.to_dict())

    def _confirm(self, req: ConfirmRequest) -> bool:
        cid = uuid.uuid4().hex[:10]
        done = threading.Event()
        item = {"id": cid, "turn": self.agent.trace.turn, "tool": req.tool, "permission": req.permission,
                "arguments": req.arguments, "reason": req.reason, "in_scope": req.appropriate,
                "collateral": req.collateral, "summary": req.summary, "verdict": req.verdict, "created": time.time()}
        self.pending[cid] = {"public": item, "done": done, "answer": False}
        self.publish("confirm", item)
        answered = done.wait(CONFIRM_TIMEOUT)
        answer = bool(self.pending.pop(cid, {}).get("answer")) if answered else False
        self.pending.pop(cid, None)
        self.publish("confirm_resolved", {"id": cid, "approve": answer, "timeout": not answered})
        return answer

    def set_bypass(self, on: bool) -> None:
        self.agent.bypass = on
        if on:
            for cid in list(self.pending):
                self.answer(cid, True)

    def set_yolo(self, on: bool) -> None:
        self.agent.yolo = on
        if on:  # 已经弹出来等着的确认卡：开了全自动就等于同意
            for cid in list(self.pending):
                self.answer(cid, True)

    def answer(self, cid: str, approve: bool) -> bool:
        item = self.pending.get(cid)
        if not item:
            return False
        item["answer"] = approve
        item["done"].set()
        return True

    def request_stop(self) -> bool:
        """停止当前轮；返回 False 表示这一轮其实已经结束了。等待中的确认卡按拒绝处理。"""
        with self._lock:
            if not self.busy:
                return False
        self.agent.request_stop()
        for cid in list(self.pending):
            self.answer(cid, False)
        return True

    def start_turn(self, text: str, source: str, images: list[str] | None = None) -> bool:
        with self._lock:
            if self.busy:
                return False
            self.busy = True

        def work():
            try:
                res = self.agent.run_turn(text, source, images=images)
                self.publish("turn_done", {"turn": res.turn, "reply": res.reply, "tier": res.tier, "steps": res.steps,
                                           "stopped": res.stopped, "tokens": res.tokens,
                                           "latency": round(res.latency, 2), "skills": res.skills})
            except Exception as exc:  # 内核异常也要让前端知道这一轮结束了
                self.publish("turn_done", {"turn": self.agent.trace.turn, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                self.busy = False
                self.publish("working", self.agent.working.to_dict())

        threading.Thread(target=work, daemon=True, name=f"turn-{self.id}").start()
        return True


def load_history(data_dir: Path, sid: str) -> dict | None:
    run = data_dir / "runs" / sid
    trace = run / "trace.jsonl"
    if not SESSION_ID.match(sid) or not trace.exists():
        return None
    events = []
    for line in trace.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    messages = []
    reasoning = []
    archive = run / "archive.jsonl"
    if archive.exists():
        for line in archive.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("kind") == "reasoning":
                reasoning.append(rec["payload"])
                continue
            if rec.get("kind") != "msg":
                continue
            msg, turn = rec["payload"]["message"], rec["payload"]["turn"]
            content = msg.get("content") or ""
            if msg["role"] == "user" and not content.startswith(INTERNAL_PREFIX):
                messages.append({"turn": turn, "role": "user", "content": content,
                                 "images": msg.get("images") or []})
            elif msg["role"] == "assistant" and content and not msg.get("tool_calls"):
                messages.append({"turn": turn, "role": "assistant", "content": content})
    return {"id": sid, "events": events, "messages": messages, "reasoning": reasoning}


def _meta_path(data_dir: Path, sid: str) -> Path:
    return data_dir / "runs" / sid / "meta.json"


def read_meta(data_dir: Path, sid: str) -> dict:
    """会话的附加信息（runs/<id>/meta.json）：自定义标题、固定使用的工作区 id。不属于轨迹契约，轨迹文件不动。"""
    try:
        data = json.loads(_meta_path(data_dir, sid).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def update_meta(data_dir: Path, sid: str, **kv) -> dict:
    meta = {**read_meta(data_dir, sid), **kv}
    meta = {k: v for k, v in meta.items() if v not in (None, "")}
    path = _meta_path(data_dir, sid)
    if meta:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)
    return meta


def read_title(data_dir: Path, sid: str) -> str:
    return str(read_meta(data_dir, sid).get("title", ""))


def rename_session(data_dir: Path, sid: str, title: str) -> str:
    """给会话起名（存 runs/<id>/meta.json，不动轨迹文件）。空名字 = 清除，回到用第一句话当标题。"""
    if not SESSION_ID.match(sid):
        raise ValueError("会话编号不合法")
    title = " ".join(title.split())[:60]
    update_meta(data_dir, sid, title=title)
    return title


def list_history(data_dir: Path, live: dict[str, LiveSession], limit: int = 60) -> list[dict]:
    runs = data_dir / "runs"
    out = []
    if runs.exists():
        dirs = sorted((d for d in runs.iterdir() if d.is_dir() and SESSION_ID.match(d.name)),
                      key=lambda d: d.stat().st_mtime, reverse=True)[:limit]
        for d in dirs:
            title, turns = "", 0
            trace = d / "trace.jsonl"
            if trace.exists():
                with trace.open(encoding="utf-8") as fh:
                    for line in fh:
                        if '"turn.start"' not in line:
                            continue
                        turns += 1
                        if not title:
                            try:
                                title = json.loads(line)["data"].get("input", "")
                            except (json.JSONDecodeError, KeyError):
                                pass
            if turns == 0 and d.name not in live:
                continue  # 评估脚本等只建了目录没对话的会话，不列出来
            custom = read_title(data_dir, d.name)
            out.append({"id": d.name, "updated": d.stat().st_mtime, "turns": turns, "custom": bool(custom),
                        "title": custom or _clip(title, 40) or ("新对话" if d.name in live else "（空会话）"),
                        "live": d.name in live})
    for sid, s in live.items():  # 刚建、还没写轨迹的在线会话
        if not any(o["id"] == sid for o in out):
            out.insert(0, {"id": sid, "updated": time.time(), "turns": 0, "title": "新对话", "live": True})
    return out


def _redact(text: str, secret: str) -> str:
    """供应商的报错里偶尔会回显 Key，给前端前抹掉。"""
    return text.replace(secret, "***") if secret and len(secret) >= 6 else text


SESSION_TTL = 7 * 86400


class WebSessions:
    """网页登录态。落盘到 <data_dir>/web_sessions.json（600），面板重启后不用重新登录。

    - 文件里只存 cookie 的 SHA-256 和过期时间，不存 cookie 原文：文件泄露也拿不到可用的登录态
    - 同时记下访问口令的指纹：换了 AGENT_WEB_TOKEN，旧登录全部作废（换口令通常就是为了踢人）
    - 写盘失败只影响"重启后还认不认"，登录本身照常在内存里生效
    """

    def __init__(self, path: Path | None, token: str):
        self.path = path
        self.token_fp = hashlib.sha256(("dgx-web-token:" + token).encode()).hexdigest()[:24]
        self._items: dict[str, float] = {}
        self._lock = threading.Lock()
        self._load()

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return  # 坏文件当作没有，大家重新登录一次而已
        if data.get("token") != self.token_fp:
            return
        now = time.time()
        self._items = {h: float(exp) for h, exp in (data.get("sessions") or {}).items() if float(exp) > now}

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("", encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            tmp.write_text(json.dumps({"token": self.token_fp, "sessions": self._items}), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as exc:
            sys.stderr.write(f"[web] 登录态写盘失败（重启后需要重新登录）：{exc}\n")

    def create(self) -> str:
        value = secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            self._items = {h: e for h, e in self._items.items() if e > now}  # 顺手清掉过期的
            self._items[self._hash(value)] = now + SESSION_TTL
            self._save()
        return value

    def valid(self, value: str) -> bool:
        if not value:
            return False
        h = self._hash(value)
        with self._lock:
            exp = self._items.get(h)
            if exp is None:
                return False
            if exp <= time.time():
                del self._items[h]
                self._save()
                return False
            return True

    def revoke(self, value: str) -> None:
        with self._lock:
            if self._items.pop(self._hash(value), None) is not None:
                self._save()


class App:
    def __init__(self, cfg: Config, token: str, no_auth: bool = False):
        self.cfg = cfg
        self.token = token
        self.no_auth = no_auth  # 仅开发：只允许在回环地址上开启（serve() 里强制检查）
        self.sessions = WebSessions(cfg.data_dir / "web_sessions.json", token)
        self.live: dict[str, LiveSession] = {}
        self.router = ModelRouter(cfg, None)
        self.models = ModelStore(cfg.models_path)
        self.memory = MemoryStore(cfg.data_dir / "memory.sqlite")
        self.integrations = IntegrationStore(cfg.data_dir / "integrations.json")
        self.integrations.apply(cfg)
        self.workspaces = WorkspaceStore(cfg.data_dir, lambda: {"workspace": self.cfg.workspace, "vault": self.cfg.vault_dir},
                                         token_for=self.integrations.git_token)
        self.previews: dict[str, tuple[str, float]] = {}  # 令牌 → (工作区 id, 过期时间)
        self.agent_factory = Agent  # 测试里换成带假模型的工厂
        self._lock = threading.Lock()

    def status(self) -> dict:
        cfg = self.cfg
        reg = build_registry()
        skills, errors = load_skills(cfg.skills_dir, set(reg.names()))
        return {
            "services": {
                **{slot: {"ok": self.router.healthy(ep), "model": ep.model, "private": ep.is_private}
                   for slot, ep in (("local", cfg.local), ("backup", cfg.backup), ("cloud", cfg.cloud))},
                "jev": {"ok": bool(cfg.jev_key), "model": cfg.jev_model},
                "linear": {"ok": bool(cfg.linear_key), "model": cfg.linear_project_name or cfg.linear_team_key},
            },
            "workspace": self.active_name("workspace"),
            "workspace_ready": (self.active_path("workspace") / ".git").exists(),
            "vault": self.active_name("vault"),
            "onboarded": self.integrations.onboarded,
            "workspace_resettable": self.demo_sandbox() is not None,
            "skills": [{"name": s.name, "description": s.description, "model": s.model,
                        "writes": [t for t in s.allowed_tools if reg.get(t).permission.value != "read"]}
                       for s in skills],
            "skill_errors": errors,
        }

    def demo_sandbox(self) -> Path | None:
        """只有演示沙盒（<data_dir>/workspace/ 下）才允许重置；指向真实仓库时返回 None。"""
        ws, box = self.active_path("workspace").resolve(), (self.cfg.data_dir / "workspace").resolve()
        return ws if box in ws.parents else None

    def _active_id(self, kind: str) -> str:
        wid = self.integrations.active(kind)
        try:
            self.workspaces.get(wid, kind)
            return wid
        except WorkspaceError:
            return "demo"  # 选中的那个被删了 / 丢了：回到演示环境

    def active_path(self, kind: str) -> Path:
        return self.workspaces.path(self._active_id(kind), kind)

    def workspace_label(self, path: Path) -> str:
        """一个会话固定用的工作区路径 → 面板里显示的名字（找不到就用目录名）。"""
        try:
            want = path.resolve()
            for item in self.workspaces.list("workspace"):
                if self.workspaces.path(item["id"], "workspace").resolve() == want:
                    return item["name"]
        except (WorkspaceError, OSError):
            pass
        return path.name

    def active_name(self, kind: str) -> str:
        return self.workspaces.get(self._active_id(kind), kind)["name"]

    def session_cfg(self, workspace_id: str | None = None) -> Config:
        """新会话用的配置副本：把当前选中的工作区 / 笔记库固定下来，之后再切换不影响进行中的会话。"""
        ws = self.workspaces.path(workspace_id, "workspace") if workspace_id else self.active_path("workspace")
        return dataclasses.replace(self.cfg, workspace=ws, vault_dir=self.active_path("vault"))

    def mint_preview(self, wid: str) -> str:
        """给工作区发一个预览令牌。预览页面在 sandbox iframe 里是不透明源，带不上 cookie，所以用地址里的令牌授权。"""
        if self.workspaces.get(wid, "workspace")["kind"] != "workspace":
            raise WorkspaceError("只有工作区能预览")
        now = time.time()
        with self._lock:
            self.previews = {t: v for t, v in self.previews.items() if v[1] > now}
            token = secrets.token_urlsafe(18)
            self.previews[token] = (wid, now + PREVIEW_TTL)
        return token

    def preview_file(self, token: str, rel: str) -> tuple[bytes, str] | None:
        entry = self.previews.get(token)
        if not entry or entry[1] < time.time():
            return None
        parts = [p for p in rel.split("/") if p]
        if any(p.startswith(".") for p in parts):  # .git、.env 之类不给看
            return None
        try:
            root = self.workspaces.path(entry[0], "workspace")
            target = safe_path(root, "/".join(parts) or ".")
        except (WorkspaceError, ToolError):
            return None
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file() or target.stat().st_size > 20 * 1024 * 1024:
            return None
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in (".js", ".mjs", ".jsx", ".ts", ".tsx", ".vue"):
            ctype = "text/javascript"
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        return target.read_bytes(), ctype

    def reload_integrations(self) -> None:
        self.integrations.apply(self.cfg)

    def linear_client(self, api_key: str = "", team: str = "", project: str = "") -> LinearClient:
        return LinearClient(api_key or self.cfg.linear_key, team or self.cfg.linear_team_key, project,
                            use_proxy=self.cfg.linear_use_proxy)

    def linear_discover(self, api_key: str) -> dict:
        lc = self.linear_client(api_key)
        d = lc.gql("query{viewer{name email} teams(first:50){nodes{key name}} "
                   "projects(first:100){nodes{name state teams{nodes{key}}}}}")
        return {"user": d["viewer"]["name"], "teams": d["teams"]["nodes"],
                "projects": [{"name": p["name"], "teams": [t["key"] for t in p["teams"]["nodes"]]}
                             for p in d["projects"]["nodes"] if p.get("state") not in ("canceled", "completed")]}

    def reset_demo(self) -> str:
        """重建演示仓库（删掉重来）。评委照着文档修 DAY-298 之前点一下，每个人看到的都是同一个起点。"""
        ws = self.demo_sandbox()
        if ws is None:
            raise RuntimeError("当前工作区不是演示沙盒，不允许重置")
        if any(s.busy for s in self.live.values()):
            raise RuntimeError("还有对话在进行，等它结束再重置")
        proc = subprocess.run([sys.executable, str(ROOT / "demo" / "seed" / "make_workspace.py"), "--force",
                               "--dest", str(ws)], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=90)
        if proc.returncode != 0:
            raise RuntimeError("重置失败：" + (proc.stderr or proc.stdout).strip()[-200:])
        return ws.name

    def reload_models(self) -> None:
        """面板里改了模型设置：重新套到运行配置上。新建的会话生效，进行中的会话继续用原来的模型。"""
        self.models.apply(self.cfg)
        self.router = ModelRouter(self.cfg, None)  # 清掉旧的探活缓存

    def test_model(self, pid: str, model: str) -> dict:
        p = self.models.provider(self.cfg, pid)
        spec = p.model(model)
        if spec is None:
            raise ModelConfigError("没有这个模型")
        ep = p.endpoint("连通测试", spec)
        if not ep.configured:
            return {"ok": False, "error": "还没填 API Key"}
        t0 = time.monotonic()
        try:
            r = LLMClient(ep).chat([{"role": "user", "content": "只回复两个字：在线"}], max_tokens=64, retries=0,
                                   thinking=False)
        except LLMError as exc:
            return {"ok": False, "error": _redact(str(exc), ep.api_key)[:300]}
        return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000), "reply": r.content[:40],
                "model": r.model}

    def session_cleanup(self, sid: str) -> dict:
        if not SESSION_ID.fullmatch(sid):
            raise ValueError("会话编号不合法")
        wid, name = self.session_workspace(sid, self.live.get(sid))
        others = set(self.live) | {p.name for p in (self.cfg.data_dir / "runs").glob("s-*") if p.is_dir()}
        refs = [other for other in others if other != sid and
                self.session_workspace(other, self.live.get(other))[0] == wid] if wid else []
        # 没有 meta 的旧在线会话也可能正在用这个目录。
        if wid and wid != "demo":
            path = self.workspaces.path(wid, "workspace").resolve()
            refs += [other for other, live in self.live.items() if other != sid
                     and live.agent.cfg.workspace.resolve() == path and other not in refs]
        delete_workspace = bool(wid and wid != "demo" and not refs)
        reason = (f"同时删除工作区「{name}」及其中全部文件。" if delete_workspace else
                  f"工作区「{name}」由其它会话共用，予以保留。" if refs else
                  "内置演示工作区保留。" if wid == "demo" else "未找到关联工作区。")
        return {"workspace_id": wid, "delete_workspace": delete_workspace,
                "description": "对话、轨迹及专属沙箱文件会被删除。" + reason + "删除后无法恢复。"}

    def delete_session(self, sid: str, expected_workspace: bool | None = None) -> dict:
        """删除一个会话的全部落盘数据。进行中的会话不让删（删了它还会继续往里写）。"""
        if not SESSION_ID.match(sid):
            raise ValueError("会话编号不合法")
        s = self.live.get(sid)
        if s is not None and s.busy:
            raise RuntimeError("这个会话正在进行中，等它结束再删")
        run = (self.cfg.data_dir / "runs" / sid).resolve()
        if run.parent != (self.cfg.data_dir / "runs").resolve():
            raise ValueError("会话编号不合法")
        with self._lock:
            if s is not None and s.busy:
                raise RuntimeError("这个会话正在进行中，等它结束再删")
            plan = self.session_cleanup(sid)
            if expected_workspace is not None and expected_workspace != plan["delete_workspace"]:
                raise RuntimeError("工作区关联已变化，请重新打开删除确认查看清理范围")
            hist = load_history(self.cfg.data_dir, sid)
            used_sandbox = hist and any(e.get("data", {}).get("tool") == "run_in_sandbox"
                                       for e in hist["events"])
            if used_sandbox:
                tag = sid[-8:].replace("-", "")
                if any(p.name != sid and p.name[-8:].replace("-", "") == tag
                       for p in (self.cfg.data_dir / "runs").glob("s-*")):
                    raise RuntimeError("沙箱目录标识与其它会话重复，已停止删除以保护文件")
                try:
                    get_sandbox().cleanup(tag)
                except SandboxError as exc:
                    raise RuntimeError(f"{exc}；会话尚未删除") from exc
            try:
                if plan["delete_workspace"]:
                    wid = plan["workspace_id"]
                    was_active = self._active_id("workspace") == wid
                    self.workspaces.delete(wid)
                    if was_active:
                        self.integrations.set_active("workspace", "demo")
                    self.previews = {k: v for k, v in self.previews.items() if v[0] != wid}
                if run.exists():
                    shutil.rmtree(run)
            except (OSError, WorkspaceError) as exc:
                raise RuntimeError("文件清理未完成，请重试删除：" + str(exc)) from exc
            self.live.pop(sid, None)
            return plan

    def new_session(self, use_jev: bool, tier: str | None, workspace: str | None = None,
                    yolo: bool = False, bypass: bool = False) -> LiveSession:
        with self._lock:
            s = LiveSession(self.session_cfg(workspace), use_jev, tier if tier in ("local", "cloud") else None,
                            self.agent_factory)
            if bypass:
                s.set_bypass(True)
            if yolo:
                s.set_yolo(True)
            update_meta(self.cfg.data_dir, s.id, workspace_id=workspace or self._active_id("workspace"),
                        use_jev=use_jev, tier=tier or "auto", yolo=yolo, bypass=bypass)
            self.live[s.id] = s
        return s

    def resume_session(self, sid: str) -> LiveSession:
        with self._lock:
            if sid in self.live:
                return self.live[sid]
            if not SESSION_ID.fullmatch(sid) or not load_history(self.cfg.data_dir, sid):
                raise WorkspaceError("没有这个会话")
            meta = read_meta(self.cfg.data_dir, sid)
            wid = meta.get("workspace_id")
            if not wid:
                raise WorkspaceError("旧会话缺少工作区记录，无法安全恢复到原目录")
            cfg = self.session_cfg(wid)
            if not cfg.workspace.is_dir():
                raise WorkspaceError("原工作区已删除，无法接续这个会话")
            tier = meta.get("tier")
            s = LiveSession(cfg, bool(meta.get("use_jev", True)), tier if tier in ("local", "cloud") else None,
                            self.agent_factory, session=sid)
            s.set_yolo(bool(meta.get("yolo", False)))
            s.set_bypass(bool(meta.get("bypass", False)))
            self.live[sid] = s
            return s

    def session_workspace(self, sid: str, live: LiveSession | None) -> tuple[str | None, str | None]:
        """(工作区 id, 名字)：新会话从 meta 读；老会话（没写过 meta）在线时退回按路径找名字。"""
        wid = read_meta(self.cfg.data_dir, sid).get("workspace_id")
        if wid:
            try:
                return wid, self.workspaces.get(wid, "workspace")["name"]
            except WorkspaceError:
                return None, None  # 工作区已被删除
        if live is not None:
            return None, self.workspace_label(live.agent.cfg.workspace)
        return None, None


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "dgx-agent"
        sys_version = ""

        def log_message(self, fmt, *args):  # 只记方法、路径、状态，不记 cookie 和请求体
            sys.stderr.write(f"[web] {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}\n")

        # ---------- 工具方法 ----------
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status: int = 200, extra: dict | None = None) -> None:
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", {"Cache-Control": "no-store", **(extra or {})})

        def _error(self, status: int, message: str) -> None:
            self._json({"error": message}, status)

        def _body(self, limit: int) -> bytes | None:
            length = int(self.headers.get("Content-Length") or 0)
            if length > limit:
                self._error(413, "请求体太大")
                return None
            return self.rfile.read(length) if length else b""

        def _json_body(self) -> dict | None:
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                self._error(415, "需要 application/json")
                return None
            raw = self._body(MAX_JSON)
            if raw is None:
                return None
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._error(400, "请求体不是合法 JSON")
                return None
            if not isinstance(data, dict):
                self._error(400, "请求体必须是对象")
                return None
            return data

        def _authed(self) -> bool:
            if app.no_auth:
                return True
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            value = cookie[COOKIE].value if COOKIE in cookie else ""
            return app.sessions.valid(value)

        def _live(self, sid: str) -> LiveSession | None:
            s = app.live.get(sid)
            if s is None:
                self._error(404, "这个会话不在线（历史会话只能查看）")
            return s

        # ---------- 路由 ----------
        def do_GET(self):
            self._dispatch("GET")

        def do_HEAD(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def _dispatch(self, method: str) -> None:
            url = urlparse(self.path)
            path = url.path
            try:
                if path.startswith("/preview/"):
                    return self._preview(path, method)
                if not path.startswith("/api/"):
                    return self._static(path) if method == "GET" else self._error(405, "不支持")
                if path == "/api/login" and method == "POST":
                    return self._login()
                if not self._authed():
                    return self._error(401, "请先登录")
                parts = path.strip("/").split("/")[1:]  # 去掉 api
                return self._api(method, parts, parse_qs(url.query))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:  # 兜底：不把堆栈给前端
                sys.stderr.write(f"[web] 未处理异常 {type(exc).__name__}: {exc}\n")
                try:
                    self._error(500, "服务器内部错误")
                except OSError:
                    pass

        def _login(self) -> None:
            data = self._json_body()
            if data is None:
                return
            given = str(data.get("token", ""))
            if not hmac.compare_digest(given.encode(), app.token.encode()):
                time.sleep(1.0)  # 拖慢暴力尝试
                return self._error(401, "访问口令不对")
            value = app.sessions.create()
            self._json({"ok": True}, extra={
                "Set-Cookie": f"{COOKIE}={value}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})

        def _api(self, method: str, parts: list[str], query: dict) -> None:
            head = parts[0] if parts else ""
            if head == "status" and method == "GET":
                return self._json(app.status())
            if head == "sessions":
                return self._sessions(method, parts[1:])
            if head == "memory":
                return self._memory(method, parts[1:], query)
            if head == "demo" and parts[1:] == ["reset"] and method == "POST":
                try:
                    return self._json({"ok": True, "workspace": app.reset_demo()})
                except RuntimeError as exc:
                    return self._error(409, str(exc))
            if head == "models":
                return self._models(method, parts[1:])
            if head == "workspaces":
                return self._workspaces(method, parts[1:], query)
            if head == "integrations":
                return self._integrations(method, parts[1:])
            if head == "asr" and method == "POST":
                return self._asr(query)
            if head == "logout" and method == "POST":
                cookie = SimpleCookie(self.headers.get("Cookie") or "")
                if COOKIE in cookie:
                    app.sessions.revoke(cookie[COOKIE].value)
                return self._json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})
            return self._error(404, "没有这个接口")

        def _sessions(self, method: str, rest: list[str]) -> None:
            if not rest:
                if method == "GET":
                    return self._json(list_history(app.cfg.data_dir, app.live))
                if method == "POST":
                    data = self._json_body()
                    if data is None:
                        return
                    wid = data.get("workspace")
                    try:
                        s = app.new_session(bool(data.get("use_jev", True)), data.get("tier"),
                                            wid if isinstance(wid, str) and wid else None,
                                            bool(data.get("yolo", False)), bool(data.get("bypass", False)))
                    except WorkspaceError as exc:
                        return self._error(400, str(exc))
                    return self._json({"id": s.id}, 201)
                return self._error(405, "不支持")
            sid = rest[0]
            if not SESSION_ID.match(sid):
                return self._error(400, "会话编号不合法")
            action = rest[1] if len(rest) > 1 else ""
            if action == "resume" and method == "POST":
                try:
                    s = app.resume_session(sid)
                except WorkspaceError as exc:
                    return self._error(409, str(exc))
                return self._json({"id": s.id})
            if action == "stop" and method == "POST":
                if self._json_body() is None:
                    return
                s = app.live.get(sid)
                if s is None:
                    return self._error(404, "这个会话没有在运行")
                return self._json({"ok": True, "stopped": s.request_stop()})
            if action == "images" and len(rest) == 2 and method == "POST":
                raw = self._body(MAX_IMAGE)
                if raw is None:
                    return
                try:
                    with app._lock:
                        if app.live.get(sid) is None:
                            return self._error(404, "这个会话不在线")
                        image_id = save_image(app.cfg.data_dir, sid, raw)
                    mime = read_image(app.cfg.data_dir, sid, image_id)[1]
                except ImageError as exc:
                    return self._error(400, str(exc))
                return self._json({"id": image_id, "mime": mime}, 201)
            if action == "images" and len(rest) == 3 and method == "GET":
                try:
                    raw, mime = read_image(app.cfg.data_dir, sid, rest[2])
                except ImageError as exc:
                    return self._error(404, str(exc))
                return self._send(200, raw, mime, {"Cache-Control": "private, max-age=3600"})
            if action == "" and method == "GET":
                hist = load_history(app.cfg.data_dir, sid) or {"id": sid, "events": [], "messages": []}
                s = app.live.get(sid)
                if s is None and not hist["events"]:
                    return self._error(404, "没有这个会话")
                hist.update({
                    "live": s is not None,
                    "busy": bool(s and s.busy),
                    "use_jev": s.use_jev if s else None,
                    "tier": (s.agent.force_tier or "auto") if s else None,
                    "yolo": bool(s.agent.yolo) if s else False,
                    "bypass": bool(getattr(s.agent, "bypass", False)) if s else False,
                    "workspace_id": app.session_workspace(sid, s)[0],
                    "workspace": app.session_workspace(sid, s)[1],
                    "working": s.agent.working.to_dict() if s else None,
                    "pending": [p["public"] for p in s.pending.values()] if s else [],
                })
                return self._json(hist)
            if action == "cleanup" and method == "GET":
                return self._json(app.session_cleanup(sid))
            if action == "" and method == "DELETE":
                data = self._json_body() if int(self.headers.get("Content-Length", "0")) else {}
                if data is None:
                    return
                try:
                    expected = data.get("delete_workspace")
                    plan = app.delete_session(sid, expected if isinstance(expected, bool) else None)
                except RuntimeError as exc:
                    return self._error(409, str(exc))
                return self._json({"ok": True, "workspace_deleted": plan["delete_workspace"]})
            patch = None
            if action == "" and method == "PATCH":
                patch = self._json_body()
                if patch is None:
                    return
                if "title" in patch:  # 改名对历史会话也有效
                    title = rename_session(app.cfg.data_dir, sid, str(patch["title"] or ""))
                    if not ({"tier", "yolo", "bypass"} & set(patch)):
                        return self._json({"ok": True, "title": title})
            s = self._live(sid)
            if s is None:
                return
            if patch is not None:
                data = patch
                if "bypass" in data:
                    s.set_bypass(bool(data["bypass"]))
                if "yolo" in data:
                    s.set_yolo(bool(data["yolo"]))
                if "tier" in data:
                    tier = data.get("tier")
                    s.agent.force_tier = tier if tier in ("local", "cloud") else None
                update_meta(app.cfg.data_dir, sid, tier=s.agent.force_tier or "auto", yolo=s.agent.yolo,
                            use_jev=s.use_jev, bypass=getattr(s.agent, "bypass", False))
                return self._json({"tier": s.agent.force_tier or "auto", "yolo": s.agent.yolo, "bypass": getattr(s.agent, "bypass", False)})
            if action == "turn" and method == "POST":
                data = self._json_body()
                if data is None:
                    return
                text = str(data.get("text", "")).strip()
                try:
                    images = validate_images(app.cfg.data_dir, sid, data.get("images", []))
                except ImageError as exc:
                    return self._error(400, str(exc))
                if images and not s.agent.cfg.vision:
                    return self._error(503, "尚未配置图片理解模型")
                if not text and not images:
                    return self._error(400, "说点什么再发送吧")
                if not text:
                    text = "请查看我发送的图片。"
                if len(text) > 8000:
                    return self._error(413, "一次说的内容太长了")
                source = "voice" if data.get("source") == "voice" else "text"
                with app._lock:
                    if app.live.get(sid) is not s:
                        return self._error(409, "会话已删除，请新建对话")
                    if not s.start_turn(text, source, images):
                        return self._error(409, "上一轮还在进行，稍等一下")
                return self._json({"ok": True}, 202)
            if action == "confirm" and method == "POST":
                data = self._json_body()
                if data is None:
                    return
                ok = s.answer(str(data.get("id", "")), bool(data.get("approve")))
                return self._json({"ok": ok}) if ok else self._error(404, "这个确认已经处理过或超时了")
            if action == "stream" and method == "GET":
                return self._stream(s)
            return self._error(404, "没有这个接口")

        def _stream(self, s: LiveSession) -> None:
            q: queue.Queue = queue.Queue(maxsize=2000)
            s.subs.append(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        kind, data = q.get(timeout=15)
                        payload = json.dumps(data, ensure_ascii=False)
                        self.wfile.write(f"event: {kind}\ndata: {payload}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                if q in s.subs:
                    s.subs.remove(q)

        def _memory(self, method: str, rest: list[str], query: dict) -> None:
            if not rest and method == "GET":
                status = (query.get("status") or ["active"])[0]
                if status not in ("active", "pending"):
                    return self._error(400, "status 只能是 active 或 pending")
                items = app.memory.list(status)
                return self._json([{"id": m.id, "layer": m.layer, "kind": m.kind, "content": m.content,
                                    "privacy": m.privacy, "status": m.status, "created": m.created_at,
                                    "used": m.use_count} for m in items])
            if len(rest) == 2 and rest[1] == "approve" and method == "POST":
                return self._json({"ok": app.memory.set_status(rest[0], "active")})
            if len(rest) == 1 and method == "DELETE":
                return self._json({"ok": app.memory.delete(rest[0])})
            return self._error(404, "没有这个接口")

        def _models(self, method: str, rest: list[str]) -> None:
            cfg = app.cfg
            try:
                if not rest and method == "GET":
                    return self._json(app.models.public(cfg))
                if rest == ["slots"] and method == "PUT":
                    data = self._json_body()
                    if data is None:
                        return
                    app.models.set_slots(cfg, data)
                elif len(rest) == 2 and rest[0] == "providers" and method in ("PUT", "DELETE"):
                    if method == "PUT":
                        data = self._json_body()
                        if data is None:
                            return
                        app.models.upsert_provider(cfg, rest[1], data)
                    else:
                        app.models.delete_provider(cfg, rest[1])
                elif len(rest) == 3 and rest[0] == "providers" and rest[2] == "discover" and method == "POST":
                    return self._json({"models": discover_models(app.models.provider(cfg, rest[1]))})
                elif len(rest) == 3 and rest[0] == "providers" and rest[2] == "test" and method == "POST":
                    data = self._json_body()
                    if data is None:
                        return
                    return self._json(app.test_model(rest[1], str(data.get("model", ""))))
                else:
                    return self._error(404, "没有这个接口")
            except ModelConfigError as exc:
                return self._error(400, str(exc))
            app.reload_models()
            return self._json(app.models.public(cfg))

        def _preview(self, path: str, method: str) -> None:
            if method not in ("GET", "HEAD"):
                return self._error(405, "不支持")
            _, _, token, *rest = path.split("/")
            got = app.preview_file(unquote(token), unquote("/".join(rest)))
            if got is None:
                return self._send(404, "预览已过期或文件不存在".encode("utf-8"), "text/plain; charset=utf-8",
                                  {"Cache-Control": "no-store"})
            body, ctype = got
            self._send(200, body, ctype, {"Cache-Control": "no-store", "Content-Security-Policy": preview_csp(self.headers.get("Host") or ""),
                                          "Access-Control-Allow-Origin": "*"})

        def _ws_listing(self) -> dict:
            return {"workspaces": app.workspaces.list("workspace"), "vaults": app.workspaces.list("vault"),
                    "active_workspace": app._active_id("workspace"), "active_vault": app._active_id("vault")}

        def _workspaces(self, method: str, rest: list[str], query: dict) -> None:
            ws = app.workspaces
            q = lambda k, d="": (query.get(k) or [d])[0]  # noqa: E731
            try:
                if not rest:
                    if method == "GET":
                        return self._json(self._ws_listing())
                    if method == "POST":
                        data = self._json_body()
                        if data is None:
                            return
                        kind, name = str(data.get("kind", "workspace")), str(data.get("name", ""))
                        if data.get("mode") == "clone":
                            view = ws.clone(name, str(data.get("url", "")), kind, str(data.get("branch", "")))
                        else:
                            view = ws.create_empty(name, kind)
                        return self._json({"created": view, **self._ws_listing()}, 201)
                    return self._error(405, "不支持")
                if rest == ["upload"] and method == "POST":
                    raw = self._body(MAX_ZIP)
                    if raw is None:
                        return
                    view = ws.import_zip(q("name"), raw, q("kind", "workspace"))
                    return self._json({"created": view, **self._ws_listing()}, 201)
                if rest == ["folder"] and method == "POST":
                    return self._json(ws.begin_upload(q("name"), q("kind", "workspace")), 201)
                wid = rest[0]
                if not WS_ID.match(wid):
                    return self._error(400, "工作区编号不合法")
                action = rest[1] if len(rest) > 1 else ""
                if action == "" and method == "DELETE":
                    kind = ws.get(wid)["kind"]
                    if wid == app._active_id(kind):
                        app.integrations.set_active(kind, "demo")
                    ws.delete(wid)
                    return self._json(self._ws_listing())
                if action == "file" and method == "PUT":
                    raw = self._body(MAX_FILE_UPLOAD)
                    if raw is None:
                        return
                    ws.put_file(wid, q("path"), raw)
                    return self._json({"ok": True})
                if action == "finish" and method == "POST":
                    return self._json({"created": ws.finish_upload(wid), **self._ws_listing()}, 201)
                if action == "activate" and method == "POST":
                    e = ws.get(wid)
                    app.integrations.set_active(e["kind"], wid)
                    return self._json(self._ws_listing())
                if action == "preview" and method == "POST":
                    if ws.get(wid)["kind"] != "workspace":
                        return self._error(400, "只有工作区能预览")
                    token = app.mint_preview(wid)
                    return self._json({"url": f"/preview/{token}/", "expires_in": PREVIEW_TTL})
                if action == "pull" and method == "POST":
                    ws.pull(wid)
                    return self._json(self._ws_listing())
                if method == "GET" and action == "tree":
                    return self._json({"entries": ws.tree(wid, q("path"))})
                if method == "GET" and action == "file":
                    return self._json(ws.read(wid, q("path")))
                if method == "GET" and action == "raw":
                    name = Path(q("path")).name or "file"
                    return self._send(200, ws.raw(wid, q("path")), "application/octet-stream",
                                      {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
                if method == "GET" and action == "changes":
                    return self._json(ws.changes(wid))
                if method == "GET" and action == "zip":
                    name = quote(ws.get(wid)["name"] + ".zip")
                    return self._send(200, ws.zip_bytes(wid), "application/zip",
                                      {"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})
            except WorkspaceError as exc:
                return self._error(400, str(exc))
            return self._error(404, "没有这个接口")

        def _integrations(self, method: str, rest: list[str]) -> None:
            store = app.integrations
            try:
                if not rest and method == "GET":
                    return self._json(store.public(app.cfg))
                if rest == ["linear"] and method == "PUT":
                    data = self._json_body()
                    if data is None:
                        return
                    key = str(data.get("api_key") or "").strip() or (store._data.get("linear") or {}).get("api_key", "")
                    team = str(data.get("team_key", "")).strip().upper()
                    project = str(data.get("project_name", "")).strip()
                    if key and team:  # 先真连一次：Key、团队、项目任何一个不对都不保存
                        try:
                            app.linear_client(key, team, project)._resolve()
                        except ToolError as exc:
                            return self._error(400, str(exc))
                    store.set_linear(data)
                elif rest == ["linear"] and method == "DELETE":
                    store.clear_linear()
                elif rest == ["linear", "discover"] and method == "POST":
                    data = self._json_body()
                    if data is None:
                        return
                    key = str(data.get("api_key") or "").strip() or (store._data.get("linear") or {}).get("api_key", "")
                    if not key:  # 不拿演示环境的 Key 替用户查：必须是用户自己填的
                        return self._error(400, "先填你自己的 Linear API Key")
                    try:
                        return self._json(app.linear_discover(key))
                    except ToolError as exc:
                        return self._error(400, str(exc))
                elif rest == ["git"] and method == "PUT":
                    data = self._json_body()
                    if data is None:
                        return
                    store.set_git(data)
                elif len(rest) == 3 and rest[:2] == ["git", "tokens"] and method in ("PUT", "DELETE"):
                    if method == "PUT":
                        data = self._json_body()
                        if data is None:
                            return
                        store.set_token(rest[2], str(data.get("token", "")))
                    else:
                        store.delete_token(rest[2])
                elif rest == ["onboarded"] and method == "PUT":
                    data = self._json_body()
                    if data is None:
                        return
                    store.set_onboarded(bool(data.get("done", True)))
                else:
                    return self._error(404, "没有这个接口")
            except IntegrationError as exc:
                return self._error(400, str(exc))
            app.reload_integrations()
            return self._json(store.public(app.cfg))

        def _asr(self, query: dict) -> None:
            fmt = (query.get("format") or ["wav"])[0]
            audio = self._body(MAX_AUDIO)
            if audio is None:
                return
            try:
                result = transcribe(app.cfg, audio, fmt)
            except AsrError as exc:
                return self._error(502, str(exc))
            return self._json(result)

        def _static(self, path: str) -> None:
            if not DIST.exists():
                return self._send(503, "面板还没构建：在 web/ 目录运行 npm run build".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            rel = path.lstrip("/") or "index.html"
            target = (DIST / rel).resolve()
            if DIST.resolve() not in target.parents or not target.is_file():
                target = DIST / "index.html"  # 单页应用回退
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            cache = "no-cache" if target.name == "index.html" else "public, max-age=31536000, immutable"
            extra = {"Cache-Control": cache}
            if target.name == "index.html":
                extra["Content-Security-Policy"] = (
                    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                    "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            self._send(200, target.read_bytes(), ctype, extra)

    return Handler


def startup_lines(host: str, port: int, token: str, no_auth: bool, public_url: str | None = None) -> list[str]:
    """启动提示。公网地址是组委会的端口映射决定的，进程自己不知道，由调用方（scripts/node.py）从登录表算好传进来。"""
    public = host not in ("127.0.0.1", "localhost", "::1")
    if public and public_url:
        lines = [f"面板已启动：{public_url}（节点内监听 {host}:{port}）"]
    elif public:
        lines = [f"面板已启动：节点内监听 {host}:{port}（公网地址见登录表的端口映射，可用 --public-url 指定）"]
    else:
        lines = [f"面板已启动：http://{host}:{port}"]
    lines.append("开发模式：免登录（只听回环地址，经 SSH 隧道访问）" if no_auth else f"访问口令：{token}")
    if public:
        lines.append("注意：监听在非回环地址，任何知道地址的人都能打开登录页；口令不要外传，用完及时关闭。")
    return lines


def serve(cfg: Config, host: str, port: int, token: str | None = None, no_auth: bool = False,
          public_url: str | None = None) -> None:
    if no_auth and host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("--dev-no-auth 只能配合回环地址使用；监听公网地址必须登录")
    token = token or os.environ.get("AGENT_WEB_TOKEN") or secrets.token_urlsafe(18)
    app = App(cfg, token, no_auth)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    for line in startup_lines(host, port, token, no_auth, public_url):
        print(line, flush=True)
    if not DIST.exists():
        print("提醒：web/dist 不存在，先在 web/ 目录 npm run build。", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
