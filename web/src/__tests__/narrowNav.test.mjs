/** @vitest-environment node */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

const stitch = readFileSync(join(process.cwd(), "src/stitch.css"), "utf8");
const preview = readFileSync(join(process.cwd(), "src/components/model-preview.css"), "utf8");
const chrome = ["/usr/bin/google-chrome", "/usr/local/bin/google-chrome"].find((path) => existsSync(path));

describe("narrow navigation and hex contrast", () => {
  let browser = null;
  let ws = null;

  afterAll(() => {
    ws?.close();
    browser?.kill();
  });

  it.skipIf(!chrome)("keeps the 390 header on one line and the hex chip on a dark label", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fp-narrow-"));
    const htmlPath = join(dir, "index.html");
    await writeFile(htmlPath, `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
      ${stitch}
      ${preview}
      body { margin: 0; background: #051424; }
    </style></head><body>
      <header class="site-header">
        <a class="site-brand" href="/"><svg width="18" height="18"></svg><span class="site-brand-home">耗材选色站</span><span class="site-brand-page">耗材选色</span></a>
        <nav class="site-nav"><a class="site-link" href="/">耗材选色</a><a class="site-link" href="/models">模型画廊</a></nav>
        <div class="site-actions"><a class="site-link site-mobile" href="/models">画廊</a><a class="site-link" href="/models/login">登录</a><button type="button" class="site-tools">工具</button></div>
      </header>
      <div class="catalog-page"><span class="swatch" style="position:relative;display:block;width:160px;height:120px;background:#ffffff"><span class="swatch-hex" data-hex="#FFFFFF"></span></span></div>
    </body></html>`);
    const port = 9400 + Math.floor(Math.random() * 400);
    browser = spawn(chrome, ["--headless=new", "--disable-gpu", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${join(dir, "profile")}`, "about:blank"], { stdio: "ignore" });
    const version = await waitForJson(`http://127.0.0.1:${port}/json/version`);
    ws = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", () => resolve());
      ws.addEventListener("error", () => reject(new Error("chrome socket failed")));
    });
    let seq = 0;
    const pending = new Map();
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !pending.has(message.id)) return;
      const waiter = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result);
    });
    const send = (method, params = {}, sessionId = "") => {
      const id = ++seq;
      ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    };
    const created = await send("Target.createTarget", { url: "about:blank" });
    const attached = await send("Target.attachToTarget", { targetId: created.targetId, flatten: true });
    const sessionId = attached.sessionId;
    await send("Page.enable", {}, sessionId);
    await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true }, sessionId);
    await send("Page.navigate", { url: `file://${htmlPath}` }, sessionId);
    const measured = await readLayout(send, sessionId);
    expect(measured.headerHeight).toBeLessThanOrEqual(56);
    expect(Math.abs(measured.loginTop - measured.brandTop)).toBeLessThanOrEqual(4);
    expect(measured.overflow).toBeLessThanOrEqual(1);
    expect(measured.hexBackground).not.toBe("rgba(0, 0, 0, 0)");
    expect(measured.hexBackground).not.toBe("rgb(255, 255, 255)");
    ws.close();
    browser.kill();
    ws = null;
    browser = null;
    await new Promise((resolve) => setTimeout(resolve, 200));
    await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }, 30000);
});

async function waitForJson(url) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch { /* chrome is still starting */ }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${url}`);
}

async function readLayout(send, sessionId) {
  const expression = `(() => {
    const header = document.querySelector('.site-header');
    const brand = document.querySelector('.site-brand');
    const login = [...document.querySelectorAll('.site-actions a')].find((node) => node.textContent === '登录');
    const chip = document.querySelector('.swatch-hex');
    const chipStyle = getComputedStyle(chip, '::after');
    return {
      headerHeight: Math.round(header.getBoundingClientRect().height),
      brandTop: Math.round(brand.getBoundingClientRect().top),
      loginTop: Math.round(login.getBoundingClientRect().top),
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      hexBackground: getComputedStyle(chip).backgroundColor,
    };
  })()`;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const result = await send("Runtime.evaluate", { expression, returnByValue: true }, sessionId);
    if (result.result?.value?.headerHeight) return result.result.value;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("narrow layout did not render");
}
