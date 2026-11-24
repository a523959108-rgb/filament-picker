/** @vitest-environment node */
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, describe, expect, it } from "vitest";

const previewCss = readFileSync(join(process.cwd(), "src/components/model-preview.css"), "utf8");
const styles = readFileSync(join(process.cwd(), "src/styles.css"), "utf8");
const FILENAME = "分件版 仙子伊布拉布布labubu （无需AMS）.3mf";
const chrome = ["/usr/bin/google-chrome", "/usr/local/bin/google-chrome"].find((path) => existsSync(path));

describe("enabled download layout", () => {
  let browser = null;
  let ws = null;

  afterAll(() => {
    ws?.close();
    browser?.kill();
  });

  it.skipIf(!chrome)("keeps the long Chinese filename and button inside the card at 1366 and 390", async () => {
    const statusRule = previewCss.match(/\.model-download-status\s*\{[^}]*\}/)?.[0] ?? "";
    expect(statusRule).toContain("overflow-wrap: anywhere");
    expect(statusRule).not.toContain("nowrap");
    expect(previewCss).toContain("overflow-wrap: anywhere");
    expect(previewCss).toContain('grid-template-areas: "title" "meta" "desc" "download"');
    const dir = await mkdtemp(join(tmpdir(), "fp-download-layout-"));
    const htmlPath = join(dir, "index.html");
    await writeFile(htmlPath, `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>${styles}\n${previewCss}</style></head><body>
<main class="page model-preview is-detail">
  <article class="panel model-screen">
    <header class="model-head">
      <h2>仙子伊布拉布布 分件版</h2>
      <p class="model-meta"><span>系列 宝可梦</span><span>作者 labubu</span><span>2 盘</span><span>19.9 MB</span></p>
      <div class="model-download-block">
        <button type="button" class="model-download">下载3MF</button>
        <p class="model-download-status">${FILENAME}</p>
      </div>
      <div class="model-description-block"><p class="model-description is-clamped">${"说明文字。".repeat(40)}</p></div>
    </header>
  </article>
</main></body></html>`);
    const port = 9300 + Math.floor(Math.random() * 500);
    let seq = 0;
    const pending = new Map();
    browser = spawn(chrome, [
      "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
      `--remote-debugging-port=${port}`, `--user-data-dir=${join(dir, "profile")}`,
      "--window-size=1400,900", "about:blank",
    ], { stdio: "ignore" });
    const version = await waitForJson(`http://127.0.0.1:${port}/json/version`);
    ws = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.addEventListener("open", () => resolve());
      ws.addEventListener("error", () => reject(new Error("chrome socket failed")));
    });
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
    await send("Runtime.enable", {}, sessionId);
    for (const width of [1366, 390]) {
      await send("Emulation.setDeviceMetricsOverride", {
        width, height: width === 390 ? 844 : 900, deviceScaleFactor: 1, mobile: width < 500,
      }, sessionId);
      await send("Page.navigate", { url: `file://${htmlPath}` }, sessionId);
      const measured = await readLayout(send, sessionId);
      expect(measured.text).toBe(FILENAME);
      expect(measured.disabled).toBe(false);
      expect(measured.pageScroll).toBeLessThanOrEqual(measured.pageClient + 1);
      expect(measured.button.right).toBeLessThanOrEqual(measured.card.right - 1);
      expect(measured.button.left).toBeGreaterThanOrEqual(measured.card.left);
      expect(measured.status.right).toBeLessThanOrEqual(measured.card.right - 1);
      expect(measured.status.left).toBeGreaterThanOrEqual(measured.card.left);
      expect(measured.status.scrollWidth).toBeLessThanOrEqual(measured.status.clientWidth + 1);
    }
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
    const card = document.querySelector(".model-screen");
    const button = document.querySelector(".model-download");
    const status = document.querySelector(".model-download-status");
    const box = (el) => {
      const rect = el.getBoundingClientRect();
      return { left: rect.left, right: rect.right };
    };
    return {
      text: status.textContent,
      disabled: button.disabled,
      card: box(card),
      button: box(button),
      status: { ...box(status), scrollWidth: status.scrollWidth, clientWidth: status.clientWidth },
      pageScroll: document.documentElement.scrollWidth,
      pageClient: document.documentElement.clientWidth,
    };
  })()`;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const result = await send("Runtime.evaluate", { expression, returnByValue: true }, sessionId);
    if (result.result?.value?.text) return result.result.value;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("layout fixture did not render");
}
