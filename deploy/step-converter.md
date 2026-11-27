# STEP 离线转换

默认 `FILAMENT_PICKER_STEP=0`，并且还要 `FILAMENT_PICKER_SUBMISSIONS=1` 才会接受投稿。开关关闭时接口直接拒绝，不会调用转换器，也不会因为扩展名是 `.step` 就当成已经解析。

## 这台 Ubuntu 24.04 上实际试过的安装

1. `sudo apt-get update` 之后 `sudo apt-get install -s freecad`：
   `Package freecad is not available` / `E: Package 'freecad' has no installation candidate`。
   packages.ubuntu.com 上 `freecad` 在 jammy（0.19.2）和更新的 26.10，不在 noble。
2. `snap`：系统里没有 snap 命令，也没有 systemd，不能装 FreeCAD snap。
3. 同一套 Ubuntu 官方源里有 OpenCASCADE 7.6.3。实测可以安装并转换：

```
sudo apt-get update
sudo apt-get install -y occt-draw libocct-draw-dev
```

`occt-draw` 是命令，`libocct-draw-dev` 提供 `pload` 要打开的不带版本号的 `.so`。不要加第三方源，也不要在请求路径里下载。

有 `freecadcmd` 的机器会优先调用仓库里的 `freecad_step.py`。本环境没有这个包，所以那条脚本没有对着 FreeCAD 跑过。本环境跑通的是：

```
occt-draw -b -c "pload ALL; testreadstep <源> shape; incmesh shape 0.1; writestl shape <目标>"
```

调用在投稿子进程里，默认最多 20 秒，超时后杀掉进程组。CPU 时间和输出文件大小用 `setrlimit` 限制。环境里去掉代理变量。产物 STL 只写在 `accounts/.step-out/`，解析后删除。STEP 原文留在 `accounts/{用户}/originals/`，不进共享 `originals/`。文件里出现 `://` 或 `file:` 就拒绝，不去抓。

`tests/fixtures/synthetic-box.step` 是 occt-draw 写的 10×20×30 mm 合成方块，不是用户模型，也不是 22 盘原件。本机实测读回后是 12 个三角面，投稿人能看到派生预览，另一个账号打开同一 id 是 404。损坏文件、外链、0.01 秒超时和 80 字节输出上限都会记为失败。

## 功能矩阵

- 已实现且在本机实测：`occt-draw` 把合成 STEP 转成私有 STL 网格和预览；开关默认关闭；外链不抓；超时杀进程；输出大小和 CPU 限制；3MF/STL 旧路径仍在。
- 实现但本环境没有实测：`freecadcmd` + `freecad_step.py`。noble 的 apt 没有 `freecad` 包。
- 外部数据或生产未验：22 盘原件、真实 COS、生产机上的转换器、生产 SSH。
