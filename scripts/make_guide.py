"""生成评委使用指南：把 docs/guide/guide.html 里的占位符换成真实地址和访问口令，导出 PDF。

  python scripts/make_guide.py
  GUIDE_CONTACT="晨熠 · 微信 xxx" python scripts/make_guide.py     # 封面联系人

输出到 deliverables/（已 gitignore）：评委使用指南.html + 评委使用指南.pdf + img/。
口令来自 .env 的 AGENT_WEB_TOKEN，地址按登录表推算（同 scripts/node.py）。脚本不在终端打印口令。
仓库里的模板保留占位符，不含真实地址和口令。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from agent.config import load_dotenv  # noqa: E402

EDGE = os.environ.get("EDGE_PATH", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
OUT = ROOT / "deliverables"


def main() -> int:
    load_dotenv()
    token = os.environ.get("AGENT_WEB_TOKEN", "").strip()
    if not token:
        sys.exit("没有找到 .env 里的 AGENT_WEB_TOKEN：面板每次启动会随机生成口令，评委拿到的会对不上。先在 .env 里固定一个。")
    import node  # 登录表 → 公网地址（与面板启动提示同一套推算）
    url = node.public_url(9000)
    if not url:
        sys.exit("推算不出公网地址")
    contact = os.environ.get("GUIDE_CONTACT", "晨熠（队长）")
    availability = os.environ.get("GUIDE_AVAILABILITY", "评审期间服务保持在线；如果打不开，请联系封面上的联系人。")

    html = (ROOT / "docs" / "guide" / "guide.html").read_text(encoding="utf-8")
    for k, v in {"{{URL}}": url, "{{TOKEN}}": token, "{{CONTACT}}": contact, "{{AVAILABILITY}}": availability}.items():
        if k not in html:
            sys.exit(f"模板里缺少占位符 {k}")
        html = html.replace(k, v)
    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "docs" / "guide" / "img", OUT / "img", dirs_exist_ok=True)
    page = OUT / "评委使用指南.html"
    page.write_text(html, encoding="utf-8")
    pdf = OUT / "评委使用指南.pdf"
    if pdf.exists():
        pdf.unlink()
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                    f"--print-to-pdf={pdf}", page.as_uri()], check=False, capture_output=True, timeout=120)
    if not pdf.exists() or pdf.stat().st_size < 50_000:
        sys.exit("PDF 没有生成成功（检查 Edge 路径：EDGE_PATH）")
    print(f"地址：{url}")
    print(f"口令：已填入（来自 .env，长度 {len(token)}）")
    print(f"联系人：{contact}")
    print(f"已生成：{page.relative_to(ROOT)}")
    print(f"已生成：{pdf.relative_to(ROOT)}（{pdf.stat().st_size // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
