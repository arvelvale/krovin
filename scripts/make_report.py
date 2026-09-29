"""生成项目报告书 PDF（提交用）：docs/report/report.html → web/public/report/（随面板部署，落地页可下载）。

  python scripts/make_report.py

依赖本机 Edge（EDGE_PATH 可改）。产物 gitignore 之外，进 web/public 由 vite 拷进 dist，
静态路由免登录提供下载：/report/KROVIN-项目报告书.pdf
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EDGE = os.environ.get("EDGE_PATH", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
SRC = ROOT / "docs" / "report" / "report.html"
OUT_DIR = ROOT / "web" / "public" / "report"
PDF = OUT_DIR / "KROVIN-项目报告书.pdf"


def main() -> int:
    if not SRC.exists():
        sys.exit(f"找不到报告源文件：{SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_DIR / "report.tmp.pdf"
    tmp.unlink(missing_ok=True)
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
         f"--print-to-pdf={tmp}", SRC.as_uri()],
        check=False, capture_output=True, timeout=180,
    )
    if not tmp.exists() or tmp.stat().st_size < 20_000:
        sys.exit("PDF 没生成成功，检查本机 Edge 路径（EDGE_PATH 环境变量）")
    os.replace(tmp, PDF)
    print(f"报告书：{PDF.relative_to(ROOT)}（{PDF.stat().st_size // 1024} KB）")
    print(f"下载地址（面板部署后）：/report/{PDF.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
