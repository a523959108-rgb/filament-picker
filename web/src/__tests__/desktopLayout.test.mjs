/** @vitest-environment node */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

const css = ["src/styles.css", "src/chroma.css", "src/stitch.css", "src/components/model-preview.css"]
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");
const chrome = ["/usr/bin/google-chrome", "/usr/local/bin/google-chrome"].find((path) => existsSync(path));
const widths = [320, 390, 768, 1366, 1920];

describe("catalog width", () => {
  let browser = null;
  let ws = null;
  let sessionId = "";
  let send = async () => { throw new Error("not ready"); };

  afterAll(async () => {
    ws?.close();
    browser?.kill();
  });

  it.skipIf(!chrome)("fills the desktop picker and keeps every width inside the viewport", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fp-width-"));
    const htmlPath = join(dir, "index.html");
    const chips = Array.from({ length: 16 }, (_, index) => `<button class="spectrum-chip" type="button">色系${index}</button>`).join("");
    const cards = Array.from({ length: 6 }, () => `<article class="swatch-card"><button class="swatch-open" type="button"><span class="swatch"></span></button></article>`).join("");
    await writeFile(htmlPath, `<!doctype html><html><head><meta charset="utf-8"><style>${css} body{margin:0}</style></head><body>
      <main class="page catalog-page">
        <div class="spectrum-row">${chips}</div>
        <div class="catalog-body"><div class="catalog-main"><div class="swatch-grid">${cards}</div></div><aside class="catalog-rail"><h2>色卡</h2><p>点开一张色卡</p></aside></div>
        <aside class="compare-bar compare-tray" id="compare-tray"><h2>对比托盘 <span>1/4</span></h2><ul><li><span>黑色</span><button type="button">移除</button></li></ul><button class="compare-open" type="button">比较</button></aside>
      </main>
      <nav class="fp-tabbar"><a href="#/">色卡</a><button type="button">品牌</button><a href="#compare-tray">对比</a></nav>
    </body></html>`);
    const port = 9600 + Math.floor(Math.random() * 300);
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
    send = (method, params = {}) => {
      const id = ++seq;
      ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    };
    const created = await send("Target.createTarget", { url: `file://${htmlPath}` });
    const windowInfo = await send("Browser.getWindowForTarget", { targetId: created.targetId });
    const windowId = windowInfo.windowId;
    await new Promise((resolve) => setTimeout(resolve, 200));
    const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((item) => item.type === "page");
    const pageWs = new WebSocket(page.webSocketDebuggerUrl);
    await new Promise((resolve) => pageWs.addEventListener("open", () => resolve()));
    let pageSeq = 0;
    const pagePending = new Map();
    pageWs.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id || !pagePending.has(message.id)) return;
      const waiter = pagePending.get(message.id);
      pagePending.delete(message.id);
      if (message.error) waiter.reject(new Error(message.error.message));
      else waiter.resolve(message.result);
    });
    const pageSend = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++pageSeq;
      pagePending.set(id, { resolve, reject });
      pageWs.send(JSON.stringify({ id, method, params }));
    });
    for (const width of widths) {
      await send("Browser.setWindowBounds", { windowId, bounds: { width, height: 900, windowState: "normal" } });
      await new Promise((resolve) => setTimeout(resolve, 150));
      const measured = await readLayout(pageSend);
      expect(measured.clientWidth, `${width} client`).toBe(width);
      expect(measured.overflow, `${width} overflow ${measured.wide}`).toBeLessThanOrEqual(1);
      expect(measured.wide, `${width} wide elements`).toEqual([]);
      if (width >= 1366) {
        expect(measured.bodyWidth).toBeGreaterThan(width * 0.9);
        expect(measured.mainRatio).toBeGreaterThan(0.68);
        expect(measured.mainRatio).toBeLessThan(0.82);
        expect(measured.railRatio).toBeGreaterThan(0.18);
        expect(measured.railRatio).toBeLessThan(0.32);
      }
      if (width === 390) {
        expect(measured.trayBottom).toBeLessThanOrEqual(measured.barTop);
        expect(measured.barHeight).toBeGreaterThanOrEqual(64);
        expect(measured.barHeight).toBeLessThanOrEqual(80);
        expect(measured.labelTops.every((value) => value >= measured.barTop)).toBe(true);
        expect(measured.labelBottoms.every((value) => value <= measured.barBottom)).toBe(true);
        expect(measured.labels).toEqual(["色卡", "品牌", "对比"]);
        expect(measured.trayText).toContain("1/4");
        expect(measured.trayText).toContain("移除");
        expect(measured.trayText).toContain("比较");
      }
    }
    pageWs.close();
    ws.close();
    browser.kill();
    ws = null;
    browser = null;
    await new Promise((resolve) => setTimeout(resolve, 200));
    await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  }, 40000);
});

async function waitForJson(url) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch { /* chrome starting */ }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`timed out waiting for ${url}`);
}

async function readLayout(send) {
  const expression = `(() => {
    const width = document.documentElement.clientWidth;
    const clipped = (el) => {
      let node = el.parentElement;
      while (node) {
        const overflow = getComputedStyle(node).overflowX;
        if (overflow === 'auto' || overflow === 'hidden' || overflow === 'scroll' || overflow === 'clip') return true;
        node = node.parentElement;
      }
      return false;
    };
    const wide = [...document.body.querySelectorAll('*')].filter((el) => {
      const box = el.getBoundingClientRect();
      return box.width > 0 && box.right > width + 1 && !clipped(el);
    }).slice(0, 6).map((el) => String(el.className || el.tagName));
    const body = document.querySelector('.catalog-body');
    const main = document.querySelector('.catalog-main');
    const rail = document.querySelector('.catalog-rail');
    const tray = document.querySelector('#compare-tray');
    const bar = document.querySelector('.fp-tabbar');
    return {
      clientWidth: document.documentElement.clientWidth,
      barHeight: bar ? Math.round(bar.getBoundingClientRect().height) : 0,
      labelTops: bar ? [...bar.querySelectorAll('a,button')].map((el) => Math.round(el.getBoundingClientRect().top)) : [],
      labelBottoms: bar ? [...bar.querySelectorAll('a,button')].map((el) => Math.round(el.getBoundingClientRect().bottom)) : [],
      overflow: document.documentElement.scrollWidth - width,
      wide,
      bodyWidth: body ? Math.round(body.getBoundingClientRect().width) : 0,
      mainRatio: body && main ? main.getBoundingClientRect().width / body.getBoundingClientRect().width : 0,
      railRatio: body && rail ? rail.getBoundingClientRect().width / body.getBoundingClientRect().width : 0,
      trayTop: tray ? Math.round(tray.getBoundingClientRect().top) : -1,
      trayBottom: tray ? Math.round(tray.getBoundingClientRect().bottom) : 9999,
      barTop: bar ? Math.round(bar.getBoundingClientRect().top) : 0,
      barBottom: bar ? Math.round(bar.getBoundingClientRect().bottom) : 9999,
      labels: bar ? [...bar.querySelectorAll('a,button')].map((el) => el.textContent.trim()) : [],
      trayText: tray ? tray.innerText : '',
    };
  })()`;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const result = await send("Runtime.evaluate", { expression, returnByValue: true });
    if (result.result?.value?.labels) return result.result.value;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("layout did not render");
}
