# RAICOM 睿抗机器人开发者大赛 · K230 视觉端

2025 年睿抗机器人开发者大赛（RAICOM）国赛参赛作品 —— **视觉识别与决策端**。

在 01Studio CanMV K230 上跑 YOLO 目标检测，计算目标相对画面中心的像素偏移，
通过串口指挥树莓派三轴机械结构把目标"搬到"画面中心。

> 作者：**[dldldlw_逐风](https://github.com/dldldlw)**
>
> 配套的下位机控制代码见另一个仓库 **raicom-pi-controller**。

> ### ⚠️ 关于本仓库代码的来源
> 比赛期间上位机代码是在 K230 的 CanMV IDE 里迭代出来的，本仓库整理自赛后留存的
> 副本。另外树莓派侧的代码是**直接在树莓派上编辑**的，与 PC 副本可能不完全一致。
> 因此这里的代码**以留存的副本为准**，可能与比赛现场实际运行版本存在差异；
> 如有出入，以现场版本为准。

---

## 获奖

**2025 年睿抗机器人开发者大赛（RAICOM）全国总决赛 ·「慧眼识果」竞赛项目 · 一等奖**

[![获奖证书](docs/awards/2025-raicom-national-final-first-prize.png)](docs/awards/2025-raicom-national-final-first-prize.png)

> 本仓库的视觉部分就是"**识果**"这一环：YOLO 检测 + 中心对齐。
> 证书中的**参赛院校、参赛学生与指导老师姓名、证书编号**，以及左下角一个
> **内含验真链接的二维码**，都已用深灰实色条打码；赛事名称、赛项、奖项等级与
> 发证单位保持可见。二维码那处尤其容易漏（**OCR 读不出二维码**），
> 排查与核对方式见 [docs/awards/README.md](docs/awards/README.md)。

---

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    K230 (CanMV / MicroPython)             │
│                                                          │
│   Sensor ──┬── CHN0  1920x1080 YUV420 ──► Display LAYER_VIDEO1 (零拷贝)
│            │                                 ▲
│            └── CHN2   640x360 RGB888P        │ OSD 叠加
│                   │                          │
│              ai2d 硬件预处理                   │
│              (等比例缩放 + 双边 padding)        │
│                   │                          │
│              KPU 推理 (kmodel)                │
│                   │                          │
│        aicube.anchorbasedet_post_process     │
│                   │                          │
│        取置信度最高的框 → 算 H / V 偏移 ──► OSD 绘制
│                   │
│              UART2 115200
└───────────────────┼──────────────────────────────────────┘
                    │  0x0B/0x0C/0x0D/0x0E  (方向)
                    │  0xCC                 (居中收工)
                    ▼
              树莓派下位机 ──► 三轴步进电机 + 舵机夹爪
```

**控制闭环**：检测到目标 → 算出相对画面中心的偏移 → 发方向字节 → 树莓派走
50 步 → 重新检测 → 直到 `|H|` 和 `|V|` 都小于 30 px 死区 → 发 `0xCC`。

---

## 硬件与固件

| 项目 | 要求 |
|---|---|
| 开发板 | 01Studio CanMV K230 |
| 固件 | 01Studio 官方 CanMV 固件（自带 `nncase_runtime` / `aicube` / `libs` / `media`） |
| 显示 | HDMI（LT9611，1920×1080）或 LCD（ST7701，800×480） |
| 通信 | UART2：TXD = GPIO11，RXD = GPIO12，115200 8N1 |

**没有 `requirements.txt`** —— 代码用到的所有模块都是 CanMV 固件内置的，
不需要 pip 安装。

---

## ⚠️ 先读这个：模型文件不在仓库里

本仓库**只包含源码**。要跑起来需要自己准备：

1. 训练好的 YOLO 检测模型 → 用 nncase 转成 `.kmodel`
2. `deploy_config.json` 部署配置（可从 [`configs/deploy_config.example.json`](configs/deploy_config.example.json) 改）

然后把它们放到 K230 的：

```
/sdcard/mp_deployment_source/
├── your_model.kmodel
└── deploy_config.json
```

完整流程见 **[docs/deploy.md](docs/deploy.md)**。

---

## 目录结构

```
raicom-k230-vision/
├── src/
│   ├── det_video_baseline.py       # 最早的基线：只做检测 + 画框
│   ├── det_center_align.py         # 加中心对齐 OSD（纯视觉调试，不发串口）
│   └── det_center_align_uart.py    # ★ 最终版：中心对齐 + 串口控制下位机
├── configs/
│   └── deploy_config.example.json  # 部署配置模板
├── docs/
│   ├── deploy.md                   # 模型转换与部署完整流程
│   ├── protocol.md                 # 串口协议（K230 视角）
│   └── awards/                     # 获奖证书（已打码）与打码说明
├── third_party/
│   ├── README.md                   # 第三方代码归属说明
│   └── uart_demo_01studio.py       # 01Studio 官方 UART 例程（非本项目原创）
├── LICENSE
└── .gitignore
```

---

## 版本演进

这三个源文件是同一份代码的三代快照，保留下来是为了记录调试过程。
**实际使用请直接看 `det_center_align_uart.py`。**

| 版本 | 文件 | 行数 | 新增能力 |
|---|---|---|---|
| v1 | `det_video_baseline.py` | 188 | YOLO 检测 + 画框（由 CanMV 官方 `det_video.py` 例程改造） |
| v2 | `det_center_align.py` | 232 | 画面中心十字 + 目标中心点 + 中心连线 + H/V 偏移量 OSD 显示 |
| v3 | `det_center_align_uart.py` | 239 | UART2 通信 + 阈值判据 + 居中退出 + 200 ms 发送限频 |

> 原工程里还有一个 `untitled_2.py`，它和 v2 只差两处（缺 `import time`、
> 用不受支持的 `draw_cross`），已被 v2 完全取代，属于死代码，本仓库不再收录。

### 调试过程中踩的两个坑（保留记录）

```python
# 坑 1: 忘了 import time
#   det_video_baseline.py / untitled_2.py 末尾用了 time.sleep(1) 却没导入 time
#   -> 一旦走到退出分支就 NameError
import time          # ☑ 本仓库三个源文件都已补上

# 坑 2: draw_cross 接口不存在
#   原代码: osd_img.draw_cross(center_x, center_y, 20, color=(255,0,0,255))
#   实际固件不支持，改用两条 draw_line 画十字（本仓库采用的写法）
osd_img.draw_line(center_x - 10, center_y, center_x + 10, center_y, color=(255, 0, 0), thickness=2)
osd_img.draw_line(center_x, center_y - 10, center_x, center_y + 10, color=(255, 0, 0), thickness=2)
```

---

## 关键实现说明

### 双通道取流 + 零拷贝显示

```python
sensor.set_framesize(width=1920, height=1080)                      # CHN0: 给人看
sensor.set_pixformat(PIXEL_FORMAT_YUV_SEMIPLANAR_420)
sensor.set_framesize(width=640, height=360, chn=CAM_CHN_ID_2)      # CHN2: 给 AI
sensor.set_pixformat(PIXEL_FORMAT_RGB_888_PLANAR, chn=CAM_CHN_ID_2)

sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
Display.bind_layer(**sensor_bind_info, layer=Display.LAYER_VIDEO1)  # 硬件直通，不过 CPU
```

CHN0 直接绑定到显示层，视频流不经过 CPU 拷贝；CHN2 才送给算法。
OSD 单独画在 `Display.LAYER_OSD3` 上叠加。

### 用 ai2d 做硬件预处理

推理前的缩放和 padding 全部交给 ai2d 硬件单元，CPU 不参与：

```python
ai2d.set_pad_param(True, [0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
ai2d.set_resize_param(True, nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
ai2d_builder = ai2d.build(
    [1, 3, OUT_RGB888P_HEIGH, OUT_RGB888P_WIDTH],
    [1, 3, kmodel_frame_size[1], kmodel_frame_size[0]],
)
```

padding 值由 `two_side_pad_param()` 按等比例缩放算出，保证宽高比不失真
（对检测精度影响很大）。

### 显示坐标换算

检测在 640×360 的通道上做，但 OSD 画在 1920×1080 上，所有框坐标都要换算：

```python
x = int(x1 * DISPLAY_WIDTH  // OUT_RGB888P_WIDTH)
y = int(y1 * DISPLAY_HEIGHT // OUT_RGB888P_HEIGH)
```

### 内存管理

嵌入式上内存很紧张，代码里做了这些：

```python
gc.collect()                 # 每帧结束后回收
del out_data                 # 及时释放推理输出张量
del ai2d_input_tensor        # 退出时释放
del ai2d_output_tensor
nn.shrink_memory_pool()      # 把内存池还给系统
```

---

## 调参速查

| 常量 | 默认 | 作用 |
|---|---|---|
| `DISTANCE_THRESHOLD` | 30 | 居中死区（像素）。调大 = 容易判定到位但精度差；调小 = 精度高但容易在边缘来回震荡 |
| `SEND_INTERVAL` | 200 | 串口发送最小间隔（ms）。调小 = 响应快但下位机可能来不及走完步数 |
| `MAX_LOST_FRAMES` | 100 | 连续多少帧没检测到目标就放弃退出 |
| `display_mode` | `"hdmi"` | 改成 `"lcd"` 切到 800×480 屏 |
| `debug_mode` | 1 | 打印各阶段耗时（`ScopedTiming`） |

---

## 串口指令速查

| 字节 | 方向 | 含义 |
|---|---|---|
| `0xAA` | 树莓派 → K230 | 就绪握手 |
| `0x0B` / `0x0C` | K230 → 树莓派 | 目标偏右 / 偏左 |
| `0x0D` / `0x0E` | K230 → 树莓派 | 目标偏下 / 偏上 |
| `0xCC` | K230 → 树莓派 | 目标已居中，收工 |

完整说明见 **[docs/protocol.md](docs/protocol.md)**。

---

## 已知问题

| 严重度 | 问题 | 位置 | 说明 |
|---|---|---|---|
| 中 | 只处理 `det_boxes[0]` | `det_center_align_uart.py` | 完全依赖后处理返回顺序（按置信度排序）。场上出现多个目标时可能锁错对象，导致三轴来回摆 |
| 中 | 纯 bang-bang 控制 | 同上 | 固定 50 步/指令，不按偏移量比例调速；30 px 死区 + 200 ms 限频，容易过冲震荡 |
| 中 | `0xAA` 握手没有真正生效 | 同上 | 本仓库**从不调用 `uart.read()`**，树莓派发来的 `0xAA` 一直留在接收缓冲里。要修就在进主循环前加一段等 `0xAA` 的读取逻辑 |
| — | `0xFF`（启动红外夹取）**不归本仓库管** | — | 红外夹取是树莓派侧的独立本地链路，当年在树莓派上直接调函数触发，不经过串口。这里没有发送方是**设计如此**，不是遗漏 |
| 低 | 中心连线 `thickness=10` 过粗 | `det_center_align.py` / `_uart.py` | 遮挡画面，观感问题 |
| 低 | 颜色元组写法不统一 | 多个文件 | v2 用 RGBA 四元组 `(255,0,0,255)`，v3 用三元组 `(255,0,0)`，同一仓库内不一致 |
| 低 | 配置项硬编码 | 所有文件 | `display_mode`、UART 引脚、`root_path`、阈值都写在文件顶部，未抽成配置模块 |

**本次相对原始版本已修复的：**

- ✅ 补上 `import time`（`det_video_baseline.py` 原本用了 `time.sleep(1)` 却没有导入）
- ✅ 补上 `anchors` / `nms_option` 在非 `AnchorBaseDet` 模型下的处理分支
      （原代码只在 `model_type == "AnchorBaseDet"` 时给这两个变量赋值，
      却无条件传给后处理，换成无锚框模型就 `NameError`）
- ✅ 补上"目标丢失"的退出条件（原代码只在**本帧检测到目标**时才判断是否居中退出，
      目标一旦被遮挡或跑出画面就永远卡在循环里，只能人工 `Ctrl-C`）
- ✅ 删掉死代码 `untitled_2.py`，把 `untitled_2/3/4.py` 改成有意义的文件名
- ✅ 补上 `try` 外的 `deploy_conf.get()` 默认值，避免配置文件缺字段直接崩

---

## 第三方代码

`third_party/uart_demo_01studio.py` 是 **01Studio 官方 CanMV K230 UART 例程**，
版权归 01Studio 所有，**不在本仓库 MIT 许可范围内**，详见
[third_party/README.md](third_party/README.md)。

`src/det_video_baseline.py` 由 CanMV / 01Studio 官方的 `det_video.py` 部署例程
改造而来，改造后已包含本项目自己的逻辑。

---

## 许可

本项目代码采用 [MIT License](LICENSE)（第三方代码除外，见上）。

---

## 相关仓库

| 仓库 | 说明 |
|---|---|
| **raicom-k230-vision** | 本仓库 —— K230 视觉识别与中心对齐 |
| **raicom-pi-controller** | 树莓派执行机构控制 |
