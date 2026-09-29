"""Bounded development-server/browser checks inside the existing code sandbox."""
import base64
import json
import shlex
import uuid
from pathlib import Path

from .base import Permission, Tool, ToolContext, ToolError, arg, params, safe_path


def browser_check(args: dict, ctx: ToolContext) -> str:
    existing = None
    if args.get('preview_url'):
        from ..preview import get_previews
        parts = str(args['preview_url']).split('/')
        existing = get_previews().resolve(parts[2] if len(parts) > 2 and parts[1] == 'live-preview' else '')
        if not existing or existing['workspace'] != str(ctx.workspace.resolve()):
            raise ToolError('预览已过期或不属于当前工作区，请先调用 start_preview')
    port = existing['port'] if existing else int(arg(args, 'port', 4173))
    if not 1024 <= port <= 65535:
        raise ToolError('port 必须在 1024–65535 之间')
    route = existing['url'] if existing else str(arg(args, 'path', '/') or '/')
    if route == '.':
        route = '/'
    if not route.startswith('/') or route.startswith('//'):
        raise ToolError('path 必须是本站路径，例如 / 或 /dist/')
    actions = args.get('actions') or []
    if not isinstance(actions, list) or len(actions) > 12:
        raise ToolError('每次最多 12 个页面操作')
    for a in actions:
        if not isinstance(a, dict) or a.get('type') not in {'click','fill','press','wait_for','assert_text'}:
            raise ToolError('无效的浏览器操作')
        if a['type'] in {'click','fill','wait_for'} and not a.get('selector'):
            raise ToolError('这个操作需要 CSS selector')
    name = uuid.uuid4().hex
    folder = '.krovin-browser'
    folder_path = ctx.workspace / folder
    if folder_path.exists() and not folder_path.is_dir():
        folder = f'.krovin-browser-{name}'
    cfg = {'existing': bool(existing), 'command': str(args.get('command') or ''), 'port': port, 'path': route, 'actions': actions,
           'width': min(1920, max(320, int(arg(args, 'width', 1280)))),
           'height': min(1440, max(320, int(arg(args, 'height', 900)))),
           'screenshot': f'{folder}/{name}.png', 'report': f'{folder}/{name}.json'}
    runner = base64.b64encode((Path(__file__).parents[1] / 'browser_runner.cjs').read_bytes()).decode()
    payload = base64.b64encode(json.dumps(cfg).encode()).decode()
    script = f'/tmp/krovin-browser-{name}.cjs'
    command = (f'set -o pipefail; mkdir -p {folder} && printf %s {shlex.quote(runner)} | base64 -d > {script}; '
               f'FONTCONFIG_FILE=/sandbox/browser-tools/fonts/fonts.conf LD_LIBRARY_PATH=/sandbox/browser-tools/lib PLAYWRIGHT_BROWSERS_PATH=/sandbox/browser-tools/browsers node {script} {shlex.quote(payload)}; '
               f'rc=$?; rm -f {script}; exit $rc')
    if ctx.sandbox is None:
        from ..sandbox import get_sandbox
        ctx.sandbox = get_sandbox()
    result = ctx.sandbox.run(command, ctx.workspace, timeout=150, tag=ctx.sandbox_tag)
    screenshot = safe_path(ctx.workspace, cfg['screenshot'])
    if screenshot.is_file() and ctx.image_sink:
        ctx.pending_images.append(ctx.image_sink(screenshot.read_bytes()))
    if result.exit_code != 0:
        raise ToolError(f'浏览器检查失败（退出码 {result.exit_code}）：\n{result.output}')
    return f'浏览器检查退出码 {result.exit_code}。{"在线预览保持运行。" if existing else "本次临时开发服务已关闭。"}\n{result.output}'


TOOLS = [Tool('browser_check',
    '在隔离沙箱里启动开发服务并用 Chromium 真浏览器检查页面、点击/输入/按键、读取错误和截图。'
    '截图会自动交给视觉模型查看，同时保存到工作区 .krovin-browser。'
    'command 可填 npm run dev -- --host 127.0.0.1 --port 4173；先用 run_in_sandbox 安装项目依赖。'
    'command 留空则启动静态文件服务。path 是本站路径，port 必须与服务一致。只关闭本工具启动的临时服务；传 preview_url 时保持在线预览运行。',
    params({'preview_url': {'type':'string','description':'start_preview 返回的地址；检查同一个在线预览，结束后保持运行'}, 'command': {'type':'string'}, 'port': {'type':'integer'}, 'path': {'type':'string'},
            'width': {'type':'integer'}, 'height': {'type':'integer'},
            'actions': {'type':'array', 'items': {'type':'object', 'properties': {
                'type': {'type':'string','enum':['click','fill','press','wait_for','assert_text']},
                'selector': {'type':'string'}, 'value': {'type':'string'}}, 'required':['type']}}}),
    Permission.WRITE_LOCAL, browser_check)]


def start_preview(args: dict, ctx: ToolContext) -> str:
    from ..preview import get_previews
    result = get_previews().start(ctx.workspace, str(args.get('path') or '/'))
    return json.dumps(result, ensure_ascii=False)

TOOLS.append(Tool('start_preview',
    '启动用户可直接打开的在线预览，返回 /live-preview/ 地址。自动识别 Vite/React，安装依赖并持续运行 2 小时；静态 HTML 也支持。'
    '交付网页前调用本工具，不要把沙箱路径或 127.0.0.1 地址当成用户可访问链接。代码修改后再次调用刷新工作区副本。',
    params({'path': {'type':'string','description':'网页路径，Vite 默认 /，静态文件例如 /public/demo.html'}}),
    Permission.WRITE_LOCAL, start_preview))
