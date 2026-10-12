# -*- coding: utf-8 -*-
"""
det_center_align_uart.py - 最终版：视觉中心对齐 + 串口控制下位机

这是比赛实际使用的版本。

工作流程
--------
1. 从 /sdcard/mp_deployment_source/deploy_config.json 读部署配置，加载 kmodel
2. Sensor 双通道取流，ai2d 硬件预处理，KPU 推理，aicube 后处理
3. 取置信度最高的目标，算出它相对画面中心的 H/V 像素偏移
4. 偏移超过阈值就通过 UART2 给树莓派发单字节指令，驱动对应轴电机
5. 两轴偏移都进入死区（目标已居中）就退出循环，并发送 0xCC 通知树莓派收工

指令表（与 docs/protocol.md 一致）::

    0x0B  目标偏右（H > +DISTANCE_THRESHOLD）  左右电机反转
    0x0C  目标偏左（H < -DISTANCE_THRESHOLD）  左右电机正转
    0x0D  目标偏下（V > +DISTANCE_THRESHOLD）  上下电机反转
    0x0E  目标偏上（V < -DISTANCE_THRESHOLD）  上下电机正转
    0xCC  目标已居中，收工

接线: UART2 TXD = GPIO11, RXD = GPIO12, 波特率 115200，与树莓派的 USB 转串口交叉连接。

相对原版的改动
--------------
* 补上 `anchors` / `nms_option` 在非 AnchorBaseDet 模型下的处理：
  原代码只在 model_type == "AnchorBaseDet" 时给这两个变量赋值，却无条件
  把它们传给后处理，换成无锚框模型就会 NameError。
* 补上"目标丢失"的退出条件：原代码只在"本帧检测到目标"时判断是否居中退出，
  一旦目标丢失（遮挡、跑出画面）exit_detection 永远不会置位，程序会一直
  空转卡死，只能人工 Ctrl-C。现在连续 MAX_LOST_FRAMES 帧没检测到就退出。
* 删掉未使用的 `import os`。
* 其余识别、控制、限频逻辑保持原样（赛场上验证过，不动）。
"""

import gc
import time
from machine import UART, FPIOA

import aicube
import image
import nncase_runtime as nn
import ujson
import ulab.numpy as np
from libs.PipeLine import ScopedTiming
from libs.Utils import *
from media.display import *
from media.media import *
from media.sensor import *

display_mode = "hdmi"
if display_mode == "lcd":
    DISPLAY_WIDTH = ALIGN_UP(800, 16)
    DISPLAY_HEIGHT = 480
else:
    DISPLAY_WIDTH = ALIGN_UP(1920, 16)
    DISPLAY_HEIGHT = 1080

OUT_RGB888P_WIDTH = ALIGN_UP(640, 16)
OUT_RGB888P_HEIGH = 360

root_path = "/sdcard/mp_deployment_source/"
config_path = root_path + "deploy_config.json"
deploy_conf = {}
debug_mode = 1

# 居中死区（像素）。|H| 和 |V| 都小于它就算"目标已居中"。
# 调大 = 更容易判定到位但精度差；调小 = 精度高但容易在死区边缘来回震荡。
DISTANCE_THRESHOLD = 30

# 串口发送最小间隔（毫秒）。加这个限频是为了避免每帧都发指令、
# 让下位机被指令淹没而来不及走完步数。
SEND_INTERVAL = 200

# 连续多少帧没检测到目标就放弃退出（防止目标丢失时死循环）
MAX_LOST_FRAMES = 100


def two_side_pad_param(input_size, output_size):
    ratio_w = output_size[0] / input_size[0]  # 宽度缩放比例
    ratio_h = output_size[1] / input_size[1]  # 高度缩放比例
    ratio = min(ratio_w, ratio_h)  # 取较小的缩放比例
    new_w = int(ratio * input_size[0])  # 新宽度
    new_h = int(ratio * input_size[1])  # 新高度
    dw = (output_size[0] - new_w) / 2  # 宽度差
    dh = (output_size[1] - new_h) / 2  # 高度差
    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw - 0.1))
    return top, bottom, left, right, ratio


def read_deploy_config(config_path):
    # 打开JSON文件以进行读取deploy_config
    with open(config_path, "r") as json_file:
        try:
            # 从文件中加载JSON数据
            config = ujson.load(json_file)
        except ValueError as e:
            print("JSON 解析错误:", e)
    return config


def detection():
    print("det_infer start")

    # 初始化串口（UART2）
    fpioa = FPIOA()
    fpioa.set_function(11, FPIOA.UART2_TXD)  # UART2 TXD 引脚
    fpioa.set_function(12, FPIOA.UART2_RXD)  # UART2 RXD 引脚
    uart = UART(UART.UART2, 115200)  # 波特率 115200

    # 记录上一次发送时间，用于限频
    last_send_time = time.ticks_ms()

    deploy_conf = read_deploy_config(config_path)
    kmodel_name = deploy_conf["kmodel_path"]
    labels = deploy_conf["categories"]
    confidence_threshold = deploy_conf["confidence_threshold"]
    nms_threshold = deploy_conf["nms_threshold"]
    img_size = deploy_conf["img_size"]
    num_classes = deploy_conf["num_classes"]
    color_four = get_colors(num_classes)
    nms_option = deploy_conf.get("nms_option", False)
    model_type = deploy_conf.get("model_type", "AnchorBaseDet")

    if model_type == "AnchorBaseDet":
        anchors = deploy_conf["anchors"][0] + deploy_conf["anchors"][1] + deploy_conf["anchors"][2]
    else:
        # 原代码没有这个分支：anchors 未定义却仍被传给后处理，会 NameError。
        # 这里显式置空并给出提示，需要跑无锚框模型时请改用对应的后处理接口。
        anchors = []
        print(f"[警告] model_type='{model_type}' 不是 AnchorBaseDet，anchors 置空。"
              f"若后处理报错，需改用 anchor-free 的后处理接口。")

    kmodel_frame_size = img_size
    frame_size = [OUT_RGB888P_WIDTH, OUT_RGB888P_HEIGH]
    strides = [8, 16, 32]

    # 计算padding值
    top, bottom, left, right, ratio = two_side_pad_param(frame_size, kmodel_frame_size)

    # 计算图像中心点（虚拟目标点）
    center_x = DISPLAY_WIDTH // 2
    center_y = DISPLAY_HEIGHT // 2

    # 初始化kpu
    kpu = nn.kpu()
    kpu.load_kmodel(root_path + kmodel_name)
    # 初始化ai2d
    ai2d = nn.ai2d()
    ai2d.set_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)
    ai2d.set_pad_param(True, [0, 0, 0, 0, top, bottom, left, right], 0, [114, 114, 114])
    ai2d.set_resize_param(True, nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
    ai2d_builder = ai2d.build(
        [1, 3, OUT_RGB888P_HEIGH, OUT_RGB888P_WIDTH], [1, 3, kmodel_frame_size[1], kmodel_frame_size[0]]
    )

    # 初始化并配置sensor
    sensor = Sensor()
    sensor.reset()
    # 设置镜像
    sensor.set_hmirror(False)
    # 设置翻转
    sensor.set_vflip(False)
    # 通道0直接给到显示VO，格式为YUV420
    sensor.set_framesize(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT)
    sensor.set_pixformat(PIXEL_FORMAT_YUV_SEMIPLANAR_420)
    # 通道2给到AI做算法处理，格式为RGB888
    sensor.set_framesize(width=OUT_RGB888P_WIDTH, height=OUT_RGB888P_HEIGH, chn=CAM_CHN_ID_2)
    sensor.set_pixformat(PIXEL_FORMAT_RGB_888_PLANAR, chn=CAM_CHN_ID_2)

    # 绑定通道0的输出到vo
    sensor_bind_info = sensor.bind_info(x=0, y=0, chn=CAM_CHN_ID_0)
    Display.bind_layer(**sensor_bind_info, layer=Display.LAYER_VIDEO1)
    if display_mode == "lcd":
        # 设置为ST7701显示，默认800x480
        Display.init(Display.ST7701, to_ide=True)
    else:
        # 设置为LT9611显示，默认1920x1080
        Display.init(Display.LT9611, to_ide=True)

    # 创建OSD图像
    osd_img = image.Image(DISPLAY_WIDTH, DISPLAY_HEIGHT, image.ARGB8888)
    # media初始化
    MediaManager.init()
    # 启动sensor
    sensor.run()
    rgb888p_img = None
    ai2d_input_tensor = None
    data = np.ones((1, 3, kmodel_frame_size[1], kmodel_frame_size[0]), dtype=np.uint8)
    ai2d_output_tensor = nn.from_numpy(data)

    # 退出标志 / 连续未检测到目标的帧数
    exit_detection = False
    lost_frames = 0

    while not exit_detection:
        with ScopedTiming("total", debug_mode > 0):
            rgb888p_img = sensor.snapshot(chn=CAM_CHN_ID_2)
            if rgb888p_img.format() == image.RGBP888:
                ai2d_input = rgb888p_img.to_numpy_ref()
                ai2d_input_tensor = nn.from_numpy(ai2d_input)
                # 使用ai2d进行预处理
                ai2d_builder.run(ai2d_input_tensor, ai2d_output_tensor)
                # 设置模型输入
                kpu.set_input_tensor(0, ai2d_output_tensor)
                # 模型推理
                kpu.run()

                # 获取模型输出
                results = []
                for i in range(kpu.outputs_size()):
                    out_data = kpu.get_output_tensor(i)
                    result = out_data.to_numpy()
                    result = result.reshape((result.shape[0] * result.shape[1] * result.shape[2] * result.shape[3]))
                    del out_data
                    results.append(result)

                # 使用aicube模块封装的接口进行后处理
                det_boxes = aicube.anchorbasedet_post_process(
                    results[0],
                    results[1],
                    results[2],
                    kmodel_frame_size,
                    frame_size,
                    strides,
                    num_classes,
                    confidence_threshold,
                    nms_threshold,
                    anchors,
                    nms_option,
                )

                # 绘制结果
                osd_img.clear()

                # 绘制中心十字（红色）
                osd_img.draw_line(center_x - 10, center_y, center_x + 10, center_y, color=(255, 0, 0), thickness=2)
                osd_img.draw_line(center_x, center_y - 10, center_x, center_y + 10, color=(255, 0, 0), thickness=2)

                if det_boxes:
                    lost_frames = 0

                    # 只处理第一个检测到的目标（后处理结果已按置信度排序）
                    det_boxe = det_boxes[0]
                    # 原始目标坐标（相对于 OUT_RGB888P 尺寸）
                    x1, y1, x2, y2 = det_boxe[2], det_boxe[3], det_boxe[4], det_boxe[5]

                    # 转换到显示尺寸
                    x = int(x1 * DISPLAY_WIDTH // OUT_RGB888P_WIDTH)
                    y = int(y1 * DISPLAY_HEIGHT // OUT_RGB888P_HEIGH)
                    w = int((x2 - x1) * DISPLAY_WIDTH // OUT_RGB888P_WIDTH)
                    h = int((y2 - y1) * DISPLAY_HEIGHT // OUT_RGB888P_HEIGH)

                    # 计算目标中心点
                    box_center_x = x + w // 2
                    box_center_y = y + h // 2

                    # 计算与虚拟中心的水平和垂直距离
                    horizontal_distance = box_center_x - center_x
                    vertical_distance = box_center_y - center_y

                    # 绘制目标信息
                    osd_img.draw_rectangle(x, y, w, h, color=color_four[det_boxe[0]][1:])
                    text = labels[det_boxe[0]] + " " + str(round(det_boxe[1], 2))
                    osd_img.draw_string_advanced(x, y - 40, 32, text, color=color_four[det_boxe[0]][1:])
                    osd_img.draw_circle(box_center_x, box_center_y, 5, color=(0, 255, 0))
                    osd_img.draw_line(center_x, center_y, box_center_x, box_center_y,
                                      color=(0, 255, 255), thickness=10)
                    distance_text = f"H:{horizontal_distance} V:{vertical_distance}"
                    osd_img.draw_string_advanced(
                        box_center_x + 10,
                        box_center_y,
                        32,
                        distance_text,
                        color=(255, 255, 0),  # 黄色文字
                    )

                    # 检查发送间隔（限频）
                    current_time = time.ticks_ms()
                    time_diff = time.ticks_diff(current_time, last_send_time)
                    should_send = time_diff >= SEND_INTERVAL

                    # 根据距离差发送串口指令
                    if should_send:
                        if horizontal_distance > DISTANCE_THRESHOLD:
                            uart.write(b'\x0B')  # 目标偏右
                        elif horizontal_distance < -DISTANCE_THRESHOLD:
                            uart.write(b'\x0C')  # 目标偏左

                        if vertical_distance > DISTANCE_THRESHOLD:
                            uart.write(b'\x0D')  # 目标偏下
                        elif vertical_distance < -DISTANCE_THRESHOLD:
                            uart.write(b'\x0E')  # 目标偏上

                        # 更新最后发送时间
                        last_send_time = current_time

                    # 检查退出条件：两轴都进死区 = 目标已居中
                    if (abs(horizontal_distance) < DISTANCE_THRESHOLD and
                            abs(vertical_distance) < DISTANCE_THRESHOLD):
                        exit_detection = True
                        print("退出检测：目标已居中")

                else:
                    # 原代码没有这个分支，目标丢失时会永远卡在循环里。
                    lost_frames += 1
                    if lost_frames >= MAX_LOST_FRAMES:
                        exit_detection = True
                        print(f"连续 {lost_frames} 帧未检测到目标，退出检测")

                Display.show_image(osd_img, 0, 0, Display.LAYER_OSD3)
                gc.collect()
            rgb888p_img = None

    # 退出时发送 0xCC，通知树莓派收工
    uart.write(b'\xCC')
    print("已发送退出信号: 0xCC")

    # 清理资源
    del ai2d_input_tensor
    del ai2d_output_tensor
    # 停止摄像头输出
    sensor.stop()
    # 去初始化显示设备
    Display.deinit()
    # 释放媒体缓冲区
    MediaManager.deinit()
    gc.collect()
    time.sleep(1)
    nn.shrink_memory_pool()
    print("det_infer end")
    return 0


if __name__ == "__main__":
    detection()
