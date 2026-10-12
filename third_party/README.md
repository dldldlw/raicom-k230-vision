# third_party —— 第三方代码说明

本目录下的文件**不是本项目的原创代码**，版权归原作者所有，
不在本仓库根目录 `LICENSE`（MIT）的授权范围内。放在这里仅作参考对照。

## uart_demo_01studio.py

* **来源**：01Studio 官方 CanMV K230 UART 例程
  （文件头原始标注：`作者：01Studio`、`实验平台：01Studio CanMV K230`）
* **内容**：演示 UART2 的引脚配置与收发，未做任何修改
* **为什么保留**：本项目的串口部分是在这个例程的基础上写起来的，
  留着便于对照引脚配置方式（`FPIOA.set_function`）
* **本项目自己的实现**：`src/det_center_align_uart.py`

### ⚠️ 使用该例程时容易踩的坑

例程里这行：

```python
uart.write("0x0B")   # 发送的是字符串 '0','x','0','B' 四个 ASCII 字节
```

发送的是**字符串**而不是字节。四个 ASCII 字符 `0x30 0x78 0x30 0x42` 会被下位机
当成四条互不相干的指令。项目代码里正确写法是：

```python
uart.write(b'\x0B')  # 发送单个字节 0x0B
```

## 补充说明

同目录外的 `src/det_video_baseline.py` 是由 CanMV / 01Studio 官方的
`det_video.py` 部署例程改造而来。改造后已包含本项目自己的中心对齐逻辑，
因此留在 `src/` 下并纳入 MIT 许可；如果原作者有异议，请联系我删除或调整归属声明。
