// Executed inside OpenShell only. No host credentials or host browser profile.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {chromium} = require('/sandbox/browser-tools/node_modules/playwright');
const cfg = JSON.parse(Buffer.from(process.argv[2], 'base64').toString());
const root = process.cwd();
const origin = `http://127.0.0.1:${cfg.port}`;
let child, server, browser;
const report = {url: origin + cfg.path, actions: [], console_errors: [], page_errors: [], failed_requests: []};
const pause = ms => new Promise(r => setTimeout(r, ms));
const stop = () => { if (child) { try { process.kill(-child.pid, 'SIGKILL'); } catch {} } };
process.on('exit', stop);
process.on('SIGTERM', () => { stop(); process.exit(143); });
async function main() {
  if (cfg.existing) {
    // Reuse managed preview; this check does not own its lifetime.
  } else if (cfg.command) {
    child = spawn('sh', ['-lc', cfg.command], {cwd: root, detached: true, stdio: ['ignore', 'pipe', 'pipe']});
    let log = '';
    for (const stream of [child.stdout, child.stderr]) stream.on('data', b => { log = (log + b).slice(-4000); report.server_log = log; });
  } else {
    const mime = {'.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.png':'image/png', '.svg':'image/svg+xml'};
    server = http.createServer((req, res) => {
      let file;
      try {
        file = fs.realpathSync(path.resolve(root, '.' + decodeURIComponent(new URL(req.url, origin).pathname)));
        if (file !== root && !file.startsWith(root + path.sep)) throw Error('outside root');
        if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
        const body = fs.readFileSync(file);
        res.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); res.end(body);
      } catch { res.statusCode = 404; res.end('Not found'); }
    });
    await new Promise((resolve, reject) => { server.once('error', reject); server.listen(cfg.port, '127.0.0.1', resolve); });
  }
  let ready = false;
  for (let i = 0; i < 80; i++) {
    if (child && child.exitCode !== null) throw Error('开发服务已退出：' + child.exitCode);
    try { const r = await fetch(origin + cfg.path, {signal: AbortSignal.timeout(500)}); if (r.ok) { ready = true; break; } report.http_status = r.status; } catch {}
    await pause(250);
  }
  if (!ready) throw Error('开发服务在 20 秒内没有响应，请检查 command 和 port');
  browser = await chromium.launch({headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage']});
  const context = await browser.newContext({viewport: {width: cfg.width, height: cfg.height}, serviceWorkers: 'block'});
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return url.origin === origin || ['data:', 'blob:'].includes(url.protocol) ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(5000);
  page.on('console', m => { if (m.type() === 'error' && report.console_errors.length < 20) report.console_errors.push(m.text().slice(0,500)); });
  page.on('pageerror', e => { if (report.page_errors.length < 20) report.page_errors.push(e.message.slice(0,500)); });
  page.on('requestfailed', r => { if (report.failed_requests.length < 20) report.failed_requests.push(r.url().slice(0,200)); });
  try {
    const response = await page.goto(report.url, {waitUntil:'domcontentloaded', timeout:20000});
    report.http_status = response?.status();
    await pause(600);
    for (const action of cfg.actions) {
      const locator = action.selector ? page.locator(action.selector).first() : null;
      if (action.type === 'click') await locator.click();
      else if (action.type === 'fill') await locator.fill(action.value || '');
      else if (action.type === 'press') await (locator || page.locator('body')).press(action.value || 'Enter');
      else if (action.type === 'wait_for') await locator.waitFor({state:'visible'});
      else if (action.type === 'assert_text') {
        if (!(await (locator || page.locator('body')).innerText()).includes(action.value || '')) throw Error('页面缺少预期文字：' + action.value);
      } else throw Error('不支持的动作：' + action.type);
      report.actions.push({...action, ok:true});
    }
    await pause(300);
  } catch (error) { report.error = error.message; }
  report.title = await page.title();
  report.text = (await page.locator('body').innerText()).slice(0,4000);
  report.controls = await page.locator('button,a,input,select,textarea').evaluateAll(els => els.slice(0,60).map(e => ({tag:e.tagName, id:e.id, text:(e.innerText || e.getAttribute('aria-label') || '').slice(0,80)})));
  await page.screenshot({path:cfg.screenshot, fullPage:false});
  report.screenshot = cfg.screenshot;
}
main().catch(e => {report.error = e.message;}).finally(async () => {
  if (browser) await browser.close().catch(() => {});
  stop(); if (server) server.close();
  try { fs.writeFileSync(cfg.report, JSON.stringify(report, null, 2)); }
  catch (e) { report.report_error = e.message; }
  console.log(JSON.stringify(report));
  process.exitCode = report.error ? 1 : 0;
});
