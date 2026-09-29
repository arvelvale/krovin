// Long-lived preview supervisor, launched inside OpenShell with no host credentials.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {spawn} = require('node:child_process');
const cfg = JSON.parse(Buffer.from(process.argv[2], 'base64').toString());
let child;
const stop = () => { if (child) { try { process.kill(-child.pid, 'SIGKILL'); } catch {} } process.exit(); };
process.on('SIGTERM', stop);
process.on('SIGINT', stop);
setTimeout(stop, cfg.ttl * 1000);
if (cfg.command) {
  child = spawn('sh', ['-lc', cfg.command], {cwd:cfg.root, detached:true, stdio:'inherit'});
  child.on('exit', code => process.exit(code || 0));
} else {
  const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.json':'application/json','.png':'image/png','.jpg':'image/jpeg'};
  const root=fs.realpathSync(cfg.root);
  http.createServer((req,res)=>{
    try {
      const url=new URL(req.url,'http://localhost');
      const rel=decodeURIComponent(url.pathname).replace(cfg.base,'/');
      if (rel.split('/').some(p=>p.startsWith('.'))) throw Error('hidden');
      let file=fs.realpathSync(path.resolve(root,'.'+rel));
      if(fs.statSync(file).isDirectory()) file=fs.realpathSync(path.join(file,'index.html'));
      if(!file.startsWith(root+path.sep)) throw Error('outside root');
      res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
      res.end(fs.readFileSync(file));
    } catch { res.statusCode=404;res.end('Not found'); }
  }).listen(cfg.port,'127.0.0.1');
}
