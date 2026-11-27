/** @vitest-environment node */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

const boot = readFileSync(join(process.cwd(), "index.html"), "utf8");
const css = ["src/styles.css", "src/chroma.css", "src/stitch.css", "src/components/model-preview.css"]
  .map((file) => readFileSync(join(process.cwd(), file), "utf8"))
  .join("\n");
const chrome = ["/usr/bin/google-chrome", "/usr/local/bin/google-chrome"].find((path) => existsSync(path));

const page = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>${css} body{margin:0;background:#051424}</style></head><body>
<header class="site-header">
  <a class="site-brand" href="/"><svg width="18" height="18"></svg><span class="site-brand-home">耗材选色站</span><span class="site-brand-page">耗材选色</span></a>
  <nav class="site-nav" aria-label="全站">
    <a class="site-link is-active" href="/" aria-current="page">耗材选色</a>
    <a class="site-link" href="/models">模型画廊</a>
    <button type="button" class="site-tools-desktop" aria-expanded="false">工具</button>
  </nav>
  <div class="site-actions">
    <a class="site-link site-mobile" href="/models">画廊</a>
    <a class="site-link" href="/models/login">登录</a>
    <button type="button" class="site-tools" aria-expanded="false">工具</button>
  </div>
  <div class="fp-tools">
    <a class="nav-link" href="#/photo">拍照找耗材</a>
    <a class="nav-link" href="#/photo">开始找色</a>
    <a class="nav-link" href="#/plan">图片配色</a>
    <a class="nav-link" href="#/cost">打印成本</a>
    <a class="nav-link" href="#/stack">叠色</a>
    <a class="nav-link" href="#/stack">打开叠色</a>
    <a class="nav-link" href="#/specs">规格索引</a>
  </div>
</header>
<script>
  document.querySelectorAll(".site-tools, .site-tools-desktop").forEach((button) => {
    button.addEventListener("click", () => {
      const open = !document.querySelector(".fp-tools").classList.contains("is-open");
      document.querySelector(".fp-tools").classList.toggle("is-open", open);
      document.querySelectorAll(".site-tools, .site-tools-desktop").forEach((node) => node.setAttribute("aria-expanded", String(open)));
    });
  });
</script>
</body></html>`;

describe("header tools menu", () => {
  let browser = null;
  let ws = null;

  afterAll(() => {
    ws?.close();
    browser?.kill();
  });

  it("keeps the boot script on the same 07:00 and 19:00 bounds", () => {
    expect(boot).toContain("minutes >= 420 && minutes < 1140");
  });

  it.skipIf(!chrome)("opens past the 56px header and keeps the title on the nav baseline", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fp-header-"));
    const htmlPath = join(dir, "index.html");
    await writeFile(htmlPath, page);
    const port = 9700 + Math.floor(Math.random() * 200);
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
    const send = (method, params = {}) => {
      const id = ++seq;
      ws.send(JSON.stringify({ id, method, params }));
      return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    };
    const created = await send("Target.createTarget", { url: `file://${htmlPath}` });
    const windowInfo = await send("Browser.getWindowForTarget", { targetId: created.targetId });
    await new Promise((resolve) => setTimeout(resolve, 200));
    const tab = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((item) => item.type === "page");
    const pageWs = new WebSocket(tab.webSocketDebuggerUrl);
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
    await pageSend("Runtime.enable");
    const evalPage = async (expression) => {
      const result = await pageSend("Runtime.evaluate", { expression, returnByValue: true });
      return result.result?.value;
    };
    for (const width of [1366, 390]) {
      await send("Browser.setWindowBounds", { windowId: windowInfo.windowId, bounds: { width, height: 900, windowState: "normal" } });
      await new Promise((resolve) => setTimeout(resolve, 200));
      const button = width >= 900 ? ".site-tools-desktop" : ".site-tools";
      const closed = await evalPage(`(() => {
        const header = document.querySelector(".site-header");
        const brand = document.querySelector(${width >= 900 ? '".site-brand-home"' : '".site-brand-page"'});
        const tool = document.querySelector(${JSON.stringify(button)});
        const nav = document.querySelector(".site-link.is-active");
        const brandBox = brand.getBoundingClientRect();
        const toolBox = tool.getBoundingClientRect();
        const navBox = nav.getBoundingClientRect();
        return {
          header: Math.round(header.getBoundingClientRect().height),
          brandMid: brandBox.top + brandBox.height / 2,
          toolMid: toolBox.top + toolBox.height / 2,
          navMid: navBox.width > 0 ? navBox.top + navBox.height / 2 : null,
          overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        };
      })()`);
      expect(closed.header, `${width} header`).toBeLessThanOrEqual(56);
      if (closed.navMid != null) {
        expect(Math.abs(closed.brandMid - closed.navMid), `${width} title vs nav`).toBeLessThanOrEqual(1);
      }
      expect(Math.abs(closed.brandMid - closed.toolMid), `${width} title vs tools`).toBeLessThanOrEqual(1);
      expect(closed.overflow, `${width} overflow`).toBeLessThanOrEqual(1);
      await evalPage(`document.querySelector(${JSON.stringify(button)}).click()`);
      const open = await evalPage(`(() => {
        const menu = document.querySelector(".fp-tools");
        const header = document.querySelector(".site-header").getBoundingClientRect();
        const box = menu.getBoundingClientRect();
        const labels = ["拍照找耗材", "图片配色", "打印成本", "叠色", "规格索引"];
        const hits = labels.map((label) => {
          const link = [...menu.querySelectorAll("a")].find((node) => node.textContent === label);
          const rect = link.getBoundingClientRect();
          const target = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
          return target === link || link.contains(target);
        });
        return {
          header: Math.round(header.height),
          top: Math.round(box.top),
          height: Math.round(box.height),
          hits,
        };
      })()`);
      expect(open.header, `${width} header stays`).toBeLessThanOrEqual(56);
      expect(open.top, `${width} menu below header`).toBeGreaterThanOrEqual(56);
      expect(open.height, `${width} menu visible`).toBeGreaterThan(120);
      expect(open.hits, `${width} tools clickable`).toEqual([true, true, true, true, true]);
      await evalPage(`document.querySelector(${JSON.stringify(button)}).click()`);
    }
    pageWs.close();
    ws.close();
    browser.kill();
    ws = null;
    browser = null;
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
