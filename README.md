filament-picker 是一个离线耗材选色工具，提供耗材目录 schema 校验和后续配色规划能力。

公开站与个人打印控制的边界见 [docs/all-in-one-boundary.md](docs/all-in-one-boundary.md)。

选色 worker 的常驻运行手册（只准备，未启动）见 [docs/dingtalk-worker-runbook.md](docs/dingtalk-worker-runbook.md)。

叠色页（`#/stack`）的三栏工作区复用了 Lumina-Layers 2.0 的面板样式和热床绘制，许可证为 AGPL-3.0-only。来源、上游 commit、复用文件和本地修改见 [third_party/lumina-layers/README.md](third_party/lumina-layers/README.md) 与 [NOTICE](NOTICE)。

常用命令：
- `.venv/bin/filament-picker --version`
- `.venv/bin/filament-picker validate request docs/schemas/examples/request.example.json`
- `.venv/bin/pytest -q`
