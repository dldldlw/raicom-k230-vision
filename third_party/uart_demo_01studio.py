# -*- coding: utf-8 -*-
'''
实验名称：UART（串口通信）
作者：01Studio
实验平台：01Studio CanMV K230
说明：通过编程实现串口通信，跟电脑串口助手实现数据收发。
'''

# ===========================================================================
# ⚠️ 第三方代码，非本项目原创
#
# 本文件为 01Studio CanMV K230 官方 UART 例程，版权归 01Studio 所有，
# 在此仅作参考保留，不在本仓库 LICENSE（MIT）的授权范围内。
# 项目自身的串口实现见 src/det_center_align_uart.py。
#
# 另需注意本例程本身的一个易混淆点：
#   uart.write("0x0B") 发送的是字符串 '0','x','0','B' 四个 ASCII 字节，
#   而不是字节 0x0B。项目代码里用的是 uart.write(b'\x0B')，请勿混用。
# ===========================================================================

#导入串口模块
from machine import UART
from machine import FPIOA
import time

fpioa = FPIOA()

# UART1代码
#fpioa.set_function(3,FPIOA.UART1_TXD)
#fpioa.set_function(4,FPIOA.UART1_RXD)

#uart=UART(UART.UART1,115200) #设置串口号1和波特率


# UART2代码
fpioa.set_function(11,FPIOA.UART2_TXD)
fpioa.set_function(12,FPIOA.UART2_RXD)

uart=UART(UART.UART2,115200) #设置串口号2和波特率


uart.write('Hello 01Studio!')#发送一条数据

while True:

    uart.write("0x0B")#发送一条数据
    text=uart.read(128) #接收128个字符
    if text != None:
        print(text) #通过REPL打印串口3接收的数据

    time.sleep(0.1) #100ms
