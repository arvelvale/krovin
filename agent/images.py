"""Session-scoped image storage; only references enter traces and checkpoints."""
from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

MAX_IMAGE = 8 * 1024 * 1024
MAX_IMAGES_PER_TURN = 6
MAX_SESSION_IMAGES = 64 * 1024 * 1024
IMAGE_ID = re.compile(r"^i-[0-9a-f]{32}$")


class ImageError(ValueError):
    pass


def image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ImageError("只支持 PNG、JPEG、GIF 或 WebP 图片")


def image_path(data_dir: Path, sid: str, image_id: str) -> Path:
    if not IMAGE_ID.fullmatch(image_id):
        raise ImageError("图片编号不合法")
    return data_dir / "runs" / sid / "images" / image_id


def save_image(data_dir: Path, sid: str, data: bytes) -> str:
    if not data or len(data) > MAX_IMAGE:
        raise ImageError("图片不能为空，且每张不能超过 8 MB")
    image_mime(data)
    folder = data_dir / "runs" / sid / "images"
    folder.mkdir(parents=True, exist_ok=True)
    if sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) + len(data) > MAX_SESSION_IMAGES:
        raise ImageError("当前会话图片总量不能超过 64 MB")
    image_id = "i-" + uuid.uuid4().hex
    image_path(data_dir, sid, image_id).write_bytes(data)
    return image_id


def read_image(data_dir: Path, sid: str, image_id: str) -> tuple[bytes, str]:
    path = image_path(data_dir, sid, image_id)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ImageError("图片不存在或已经删除") from exc
    if len(data) > MAX_IMAGE:
        raise ImageError("图片太大")
    return data, image_mime(data)


def validate_images(data_dir: Path, sid: str, image_ids: object) -> list[str]:
    if not isinstance(image_ids, list) or len(image_ids) > MAX_IMAGES_PER_TURN:
        raise ImageError("每轮最多发送 6 张图片")
    if any(not isinstance(x, str) for x in image_ids) or len(image_ids) != len(set(image_ids)):
        raise ImageError("图片编号不合法或重复")
    for image_id in image_ids:
        read_image(data_dir, sid, image_id)
    return image_ids


def model_messages(messages: list[dict], data_dir: Path, sid: str) -> list[dict]:
    """Expand references only for the model call, never in persisted conversation."""
    out = []
    for msg in messages:
        images = msg.get("images") or []
        if not images:
            out.append(msg)
            continue
        content = [{"type": "text", "text": msg.get("content") or "请查看图片"}]
        for image_id in images:
            data, mime = read_image(data_dir, sid, image_id)
            content.append({"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}})
        out.append({"role": msg["role"], "content": content})
    return out
