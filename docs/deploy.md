# 部署说明

本仓库**不包含模型文件**。要跑起来必须自己准备 `kmodel` 和 `deploy_config.json`，
并放到 K230 的 SD 卡上。下面是完整流程。

## 1. 硬件与固件

| 项目 | 要求 |
|---|---|
| 开发板 | 01Studio CanMV K230（嘉楠 K230 芯片） |
| 固件 | 01Studio 官方 CanMV 固件（自带 `nncase_runtime`、`aicube`、`libs`、`media` 模块） |
| 显示 | HDMI（LT9611，默认 1920×1080）或 LCD（ST7701，800×480） |
| 摄像头 | 板载/配套 CSI 摄像头 |
| SD 卡 | 需可读写，模型放 `/sdcard/` |

代码里用到的模块（`aicube`、`image`、`nncase_runtime`、`ujson`、`ulab.numpy`、
`libs.*`、`media.*`、`machine`）**全部是 CanMV 固件内置的，不需要 pip 安装**，
所以本仓库没有 `requirements.txt`。

切到 LCD 屏幕：把源文件顶部的 `display_mode = "hdmi"` 改成 `"lcd"`。

## 2. 准备模型

1. 在 PC 上用 YOLO 系列（本项目用的是带锚框的 AnchorBaseDet 结构）训练检测模型。
2. 用嘉楠的 **nncase** 工具链把模型转成 `.kmodel`。
3. 建议输入尺寸 320×320（代码里 `img_size` 从 config 读，可改）。

> 本项目对应的模型权重没有随仓库提供（kmodel 属大文件，且是训练产出）。
> 请按上述流程自行训练/转换，或使用你自己的等结构模型。

## 3. 放置文件

把文件按下面的路径放进 SD 卡：

```
/sdcard/mp_deployment_source/
├── your_model.kmodel          <- 你的模型
└── deploy_config.json         <- 部署配置
```

`deploy_config.json` 可以拿 `configs/deploy_config.example.json` 做模板，
**必须把 `kmodel_path` 改成本次实际使用的文件名**。

各字段含义：

| 字段 | 类型 | 说明 |
|---|---|---|
| `kmodel_path` | string | 相对 `root_path` 的模型文件名 |
| `model_type` | string | `"AnchorBaseDet"`（带锚框检测）。填别的值时 `anchors` 会被置空并打印警告 |
| `img_size` | `[w, h]` | kmodel 的输入尺寸，注意是 **宽在前** |
| `num_classes` | int | 类别数，需与 `categories` 长度一致 |
| `categories` | string[] | 类别名，用于 OSD 显示 |
| `confidence_threshold` | float | 置信度阈值 |
| `nms_threshold` | float | NMS 的 IoU 阈值 |
| `nms_option` | bool | 传给 `aicube.anchorbasedet_post_process` 的 NMS 模式开关 |
| `anchors` | float[3][6] | 三个尺度各 6 个锚框值（YOLO 的 w/h 成对） |

## 4. 运行

方式一：用 CanMV IDE 打开 `src/det_center_align.py`，点运行（调试用，只显示不控制）。

方式二：把 `src/det_center_align_uart.py` 拷到 SD 卡，通过 IDE 或自启动脚本运行
（正式联调用，带串口控制）。

## 5. 调参

都在源文件顶部：

| 常量 | 默认 | 作用 |
|---|---|---|
| `DISTANCE_THRESHOLD` | 30 | 居中死区（像素）。调大 = 容易判定到位但精度差；调小 = 精度高但容易在边缘震荡 |
| `SEND_INTERVAL` | 200 | 串口发送最小间隔（ms）。调小 = 响应快但下位机可能来不及走完步数 |
| `MAX_LOST_FRAMES` | 100 | 连续多少帧没检测到目标就放弃退出 |
| `display_mode` | `"hdmi"` | 改成 `"lcd"` 切到 800×480 屏 |
| `debug_mode` | 1 | `ScopedTiming` 打印各阶段耗时的开关 |

## 6. 常见问题

**`JSON 解析错误` / 文件打不开** — `deploy_config.json` 没放到
`/sdcard/mp_deployment_source/` 下，或路径拼写不对。

**`NameError: name 'time' is not defined`** — 旧版源文件（原始工程里的
`det_video_1_2_2.py` 和 `untitled_2.py`）用了 `time.sleep(1)` 却没导入
`time`。本仓库的三个源文件都已补上 `import time`。

**运行后立刻报 `anchors` 相关错误** — 说明 `model_type` 不是
`"AnchorBaseDet"`。带锚框模型必须提供 `anchors` 字段；无锚框模型需要改用
anchor-free 的后处理接口。

**画面是黑的 / 显示不出来** — `display_mode` 与实际屏幕不匹配
（HDMI 对应 LT9611，LCD 对应 ST7701）。

**`nn.shrink_memory_pool()` 报错** — 那是退出路径上的内存回收，正常运行时
用不到；如果固件版本较老不支持，删掉那一行即可。
