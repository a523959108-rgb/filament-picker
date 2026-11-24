# 离线派生 GLB 和正视

从本机 `originals/{id}.3mf` 解析网格、组件变换和长度单位，写到 `derived/{id}/`。不会改原件，也不会把切片斜视图或俯视图改名为正视。

每张盘上的对象都能在 `Metadata/model_settings.config` 里对上时，另外写出 `front-{盘号}.png`。有构建项对不上盘时，只写整体 `front.png`，索引里的说明是「仅整体正视，没有可靠的盘面定位」。

```sh
FILAMENT_PICKER_MODELS_ROOT=/path/to/models \
  "$VENV/bin/filament-picker" derive-preview --id 9bb0daaf5dc37fed
```

不带 `--id` 时处理 `originals/` 里每一份 `.3mf`。一份失败不会停掉后面的。`--force` 忽略已有的内容哈希，重跑这一份。相同内容哈希且状态是 `ready` 时直接跳过。

登录后的 `POST /api/models/{id}/derive` 走同一条派生。原件如果只在对象存储上，服务端把它流到 `derived/.incoming/` 的临时文件，限制 64MB、剩余磁盘和读取时间，用完就删。浏览器拿不到对象地址或密钥。测试里的对象存储是本地假服务，不表示生产桶已经连通。

派生文件只从 `/api/models/{id}/derived/…` 读取，需要登录，`Cache-Control: no-store`。没有 `model.glb` 时，线框、归位、剖切和正视都保持关闭。

部署前备份正在运行的 wheel、静态文件和 `derived/`。回滚时装回那份备份。不要把旧交接记录里的哈希当成当前生产回滚版本，也不要在生产目录里 checkout 或 reset。
