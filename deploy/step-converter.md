# STEP 离线转换

缺 `freecadcmd` 时拒绝上传，只说明依赖没装。这不是 STEP 支持。

要让接口真正调用转换器，需要同时满足：

1. 发行版离线安装提供 `freecadcmd` 的 FreeCAD 包（Debian/Ubuntu 包名 `freecad`）。不要在请求路径里 `pip install` 或访问网络。
2. `FILAMENT_PICKER_STEP=1`。默认是 `0`，即使机器上有 `freecadcmd` 也不会调用。
3. `FILAMENT_PICKER_SUBMISSIONS=1`。投稿总开关仍然默认关闭。

调用方式：投稿进程在账号目录里执行 `freecadcmd <源.step> <账号临时目录>/<模型 id>.stl`，最多 20 秒。产物只留在该账号的临时目录，再按 STL 规则做网格。失败、超时或没有产出 STL，投稿记为失败，不写入共享 `originals/`。

本仓库的测试只用 PATH 上的假脚本证明开关和调用边界。没有在这台机器上用真实 FreeCAD 转过 STEP，所以发布清单里 STEP 仍是未完成。
