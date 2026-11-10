# Lumina-Layers（第三方，AGPL-3.0-only）

叠色工作区复用了 [Lumina-Layers](https://github.com/lumina-layer-studio/Lumina-Layers)（Lumina Studio）的前端代码、样式和热床绘制。

- 来源仓库：https://github.com/lumina-layer-studio/Lumina-Layers
- 上游 commit：`b89af08226a88c9c9b3e2934ea1838c449923858`
- 许可证：GNU Affero General Public License v3.0 **only**。原文见同目录 [`LICENSE`](LICENSE)，未改动。
- 本仓库的对应源码入口在叠色页「源码」链接，构建时可用 `VITE_SOURCE_URL` 覆盖，默认 `https://github.com/a523959108-rgb/filament-picker`。

## 复用了哪些文件

下面的路径是放进本仓库、参与前端构建的副本。除另行说明外，内容与上游该 commit 的对应文件一致。

| 本仓库 | 上游 |
| --- | --- |
| `web/src/vendor/lumina/components/bedPlatformGeometry.ts` | `frontend/src/components/bedPlatformGeometry.ts` |
| `web/src/vendor/lumina/components/bedPlatformTexture.ts` | `frontend/src/components/bedPlatformTexture.ts` |
| `web/src/vendor/lumina/components/themeConfig.ts` | `frontend/src/components/themeConfig.ts` |
| `web/src/vendor/lumina/components/ui/Button.tsx` | `frontend/src/components/ui/Button.tsx` |
| `web/src/vendor/lumina/components/ui/ButtonContent.tsx` | `frontend/src/components/ui/ButtonContent.tsx` |
| `web/src/vendor/lumina/components/ui/DisclosureChevron.tsx` | `frontend/src/components/ui/DisclosureChevron.tsx` |
| `web/src/vendor/lumina/components/ui/panelPrimitives.tsx` | `frontend/src/components/ui/panelPrimitives.tsx` |
| `web/src/vendor/lumina/components/ui/ImageUpload.tsx` | `frontend/src/components/ui/ImageUpload.tsx` |
| `web/src/vendor/lumina/types/workspace.ts` | `frontend/src/types/workspace.ts` |
| `web/src/vendor/lumina/lumina-theme.css` | `frontend/src/index.css`（节选并改过，见下） |
| `third_party/lumina-layers/LICENSE` | `LICENSE` |

未复制字体、`logo.png`、切片软件图标、LUT 预设或 Python 引擎。热床纹理函数仍会在板面写上上游字样 “Lumina”。

## 我们改了什么

- `ImageUpload.tsx`：补了显式的 React 事件类型导入。本仓库的 `react-jsx` 运行时没有全局 `React` 命名空间。交互和文案结构未改；文案来自本仓库的 `web/src/vendor/lumina/i18n/context.tsx`（这是适配层，不是上游文件）。
- `lumina-theme.css`：从 `index.css` 抽出设计令牌、按钮、面板和状态条规则。去掉了 Tailwind 的 `@import` / `@theme`、MiSans `@font-face`、作用在全站的 `body` 规则、全局 `box-shadow` 清除，以及滚动条规则。设计令牌挂在 `.lumina-stack` 上，而不是 `:root`。Tailwind 工具类单独引入，且不带 Preflight，避免改掉选色站其它页面。
- 叠色页自己的三栏壳、槽位排序、预览/3MF 按钮和回传逻辑在 `web/src/components/StackPage.tsx` 与 `StackBed.tsx`，调用上述 Lumina 模块，不是把 Lumina 的转换器 store 整份搬过来。

界面里保留了 Lumina-Layers（Lumina Studio）署名和上游仓库地址，见叠色页「高级」区。
