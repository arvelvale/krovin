"""Bounded development-server/browser checks inside the existing code sandbox."""
import base64
import json
import shlex
import uuid
from pathlib import Path

from .base import Permission, Tool, ToolContext, ToolError, arg, params, safe_path


def browser_check(args: dict, ctx: ToolContext) -> str:
    port = int(arg(args, 'port', 4173))
    if not 1024 <= port <= 65535:
        raise ToolError('port 必须在 1024–65535 之间')
    route = str(arg(args, 'path', '/'))
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
    cfg = {'command': str(args.get('command') or ''), 'port': port, 'path': route, 'actions': actions,
           'width': min(1920, max(320, int(arg(args, 'width', 1280)))),
           'height': min(1440, max(320, int(arg(args, 'height', 900)))),
           'screenshot': f'{folder}/{name}.png', 'report': f'{folder}/{name}.json'}
    runner = base64.b64encode((Path(__file__).parents[1] / 'browser_runner.cjs').read_bytes()).decode()
    payload = base64.b64encode(json.dumps(cfg).encode()).decode()
    script = f'/tmp/krovin-browser-{name}.cjs'
    command = (f'mkdir -p {folder}; printf %s {shlex.quote(runner)} | base64 -d > {script}; '
               f'FONTCONFIG_FILE=/sandbox/browser-tools/fonts/fonts.conf LD_LIBRARY_PATH=/sandbox/browser-tools/lib PLAYWRIGHT_BROWSERS_PATH=/sandbox/browser-tools/browsers node {script} {shlex.quote(payload)}; '
               f'rc=$?; rm -f {script}; exit $rc')
    if ctx.sandbox is None:
        from ..sandbox import get_sandbox
        ctx.sandbox = get_sandbox()
    result = ctx.sandbox.run(command, ctx.workspace, timeout=150, tag=ctx.sandbox_tag)
    screenshot = safe_path(ctx.workspace, cfg['screenshot'])
    if screenshot.is_file() and ctx.image_sink:
        ctx.pending_images.append(ctx.image_sink(screenshot.read_bytes()))
    return f'浏览器检查退出码 {result.exit_code}。开发服务在检查结束后关闭。\n{result.output}'


TOOLS = [Tool('browser_check',
    '在隔离沙箱里启动开发服务并用 Chromium 真浏览器检查页面、点击/输入/按键、读取错误和截图。'
    '截图会自动交给视觉模型查看，同时保存到工作区 .krovin-browser。'
    'command 可填 npm run dev -- --host 127.0.0.1 --port 4173；先用 run_in_sandbox 安装项目依赖。'
    'command 留空则启动静态文件服务。path 是本站路径，port 必须与服务一致。每次检查结束会关闭本次服务。',
    params({'command': {'type':'string'}, 'port': {'type':'integer'}, 'path': {'type':'string'},
            'width': {'type':'integer'}, 'height': {'type':'integer'},
            'actions': {'type':'array', 'items': {'type':'object', 'properties': {
                'type': {'type':'string','enum':['click','fill','press','wait_for','assert_text']},
                'selector': {'type':'string'}, 'value': {'type':'string'}}, 'required':['type']}}}),
    Permission.WRITE_LOCAL, browser_check)]
