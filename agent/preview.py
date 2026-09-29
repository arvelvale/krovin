"""Managed sandbox preview services. Only loopback forwards; browser access uses scoped URL tokens."""
from __future__ import annotations
import atexit
import base64
import hashlib
import http.client
import json
import secrets
import shlex
import socket
import subprocess
import threading
import time
from pathlib import Path
from .sandbox import get_sandbox
from .tools.base import ToolError, safe_path, subprocess_env

TTL = 7200
MAX_PREVIEWS = 4

class PreviewManager:
    def __init__(self):
        self.entries = {}
        self.lock = threading.RLock()
        atexit.register(self.close)

    def close(self):
        for token in list(self.entries):
            self.stop(token)

    def stop_workspace(self, workspace):
        for token, entry in list(self.entries.items()):
            if entry['workspace'] == str(Path(workspace).resolve()):
                self.stop(token)

    def stop(self, token):
        with self.lock:
            entry = self.entries.pop(token, None)
        if not entry: return
        entry['timer'].cancel()
        entry['forward'].terminate()
        sb = get_sandbox()
        # PID belongs to the dedicated supervisor, which terminates its child process group.
        try:
            sb._cli('sandbox','exec','-n',sb.name,'--timeout','10','--','sh','-c',
                    f"test ! -f {entry['pid']} || kill $(cat {entry['pid']})", timeout=15)
            sb.cleanup(entry['tag'])
        except ToolError:
            pass  # TTL supervisor remains the upper bound if gateway is unavailable.

    def start(self, workspace: Path, route='/'):
        workspace=workspace.resolve()
        with self.lock:
            for token, e in list(self.entries.items()):
                if e['workspace']==str(workspace): self.stop(token)
            if len(self.entries)>=MAX_PREVIEWS:
                raise ToolError('已有 4 个在线预览，请先关闭不用的预览')
            token=secrets.token_urlsafe(24)
            base=f'/live-preview/{token}/'
            tag='preview-'+hashlib.sha256(str(workspace).encode()).hexdigest()[:16]
            remote=f'/sandbox/work/{tag}/w'
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
            package=workspace/'package.json'
            command=''
            setup=''
            if package.is_file():
                try: data=json.loads(package.read_text(encoding='utf-8-sig'))
                except ValueError: raise ToolError('package.json 不是有效 JSON')
                deps={**data.get('dependencies',{}),**data.get('devDependencies',{})}
                scripts=data.get('scripts',{})
                if 'vite' in deps or any('vite' in str(v) for v in scripts.values()):
                    build_code = "import {build} from './node_modules/vite/dist/node/index.js'; await build({build:{write:false}});"
                    setup='npm install --no-audit --no-fund && node --input-type=module -e '+shlex.quote(build_code)+' && '
                    code = "import {createServer} from './node_modules/vite/dist/node/index.js'; const s=await createServer("+json.dumps({'base':base,'server':{'host':'127.0.0.1','port':port,'strictPort':True,'hmr':False}})+"); await s.listen();"
                    command='node --input-type=module -e '+shlex.quote(code)
                elif not (workspace/'index.html').is_file():
                    raise ToolError('暂未识别开发服务：当前支持 Vite/React 和静态 HTML；请提供 Vite 项目或构建后的 HTML 目录')
            route='/' if route in ('','.', 'index.html','/index.html','package.json') else '/'+route.lstrip('/')
            if '..' in route.split('/') or '\\' in route or '?' in route or '#' in route:
                raise ToolError('预览路径不合法')
            if not command:
                target=safe_path(workspace,route.lstrip('/') or 'index.html')
                if not target.is_file(): raise ToolError('找不到预览入口：'+route)
            sb=get_sandbox()
            cfg={'root':remote,'port':port,'base':base,'command':command,'ttl':TTL}
            payload=base64.b64encode(json.dumps(cfg).encode()).decode()
            runner=base64.b64encode(Path(__file__).with_name('preview_runner.cjs').read_bytes()).decode()
            script=f'/tmp/krovin-preview-{token}.cjs'; pid=f'/tmp/krovin-preview-{token}.pid'; log=f'/tmp/krovin-preview-{token}.log'
            # Launch only after dependencies finish, otherwise readiness might race an npm install.
            prepare=sb.run(f'set -o pipefail; {setup}printf %s {shlex.quote(runner)} | base64 -d > {script}',workspace,timeout=240,tag=tag)
            if prepare.exit_code: raise ToolError('预览准备失败（依赖安装或项目构建）：'+prepare.output[-2500:])
            started=sb._cli('sandbox','exec','-n',sb.name,'--timeout','10','--','sh','-c',
                            f'nohup node {script} {payload} >{log} 2>&1 </dev/null & echo $! > {pid}',timeout=20)
            if started.returncode: raise ToolError('启动预览失败：'+started.stderr[-1000:])
            forward=subprocess.Popen(['timeout','--kill-after=5',str(TTL),sb.cli,'forward','start',f'127.0.0.1:{port}',sb.name],
                                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,stdin=subprocess.DEVNULL,
                                     env=subprocess_env(**sb._env()))
            timer=threading.Timer(TTL,lambda:self.stop(token));timer.daemon=True
            entry={'workspace':str(workspace),'port':port,'base':base,'tag':tag,'pid':pid,'log':log,
                   'forward':forward,'timer':timer,'expires':time.time()+TTL,'url':base+route.lstrip('/')}
            self.entries[token]=entry
            try:
                for _ in range(100):
                    if forward.poll() is not None: raise ToolError('预览端口转发启动失败')
                    try:
                        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=1)
                        conn.request('GET',entry['url']);r=conn.getresponse();r.read();conn.close()
                        if r.status<400: break
                    except OSError: pass
                    time.sleep(.2)
                else:
                    log_result=sb._cli('sandbox','exec','-n',sb.name,'--timeout','10','--','tail','-c','2400',log)
                    raise ToolError('预览服务未就绪：'+log_result.stdout)
            except Exception:
                self.stop(token);raise
            timer.start()
            return {'url':entry['url'],'expires_in':TTL,'kind':'vite' if command else 'static','path':route,
                    'note':'在线预览已启动，2 小时后自动关闭；修改代码后重新启动预览以同步最新文件。'}

    def resolve(self, token):
        entry=self.entries.get(token)
        if not entry or entry['expires']<time.time(): return None
        return entry

_manager=None
def get_previews():
    global _manager
    if _manager is None: _manager=PreviewManager()
    return _manager
