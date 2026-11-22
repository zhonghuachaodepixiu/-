# Pwn 进阶笔记：SROP（Sigreturn Oriented Programming）

## 一、 核心思想与背景
- **核心思想**：这是 Pwn 里的**核武器**。正常情况下，我们要传参得一个个去找 `pop rdi`、`pop rsi` 这些 Gadget。但如果遇到极其变态的题（连一个 `pop` 指令都找不到），怎么办？SROP 告诉我们：我们可以利用 Linux 的**信号机制**，伪造一个上下文结构，让操作系统内核帮我们**一次性恢复所有寄存器**。相当于一键修改了 `rdi, rsi, rdx, rsp, rip` 等所有状态，想干嘛干嘛。

## 二、 底层原理：Signal 机制与 sigreturn
要搞懂 SROP，必须先搞懂内核是怎么处理“信号（Signal）”的。
**1. 什么是信号？**
比如你按 `Ctrl+C` 发送 `SIGINT` 信号，或者程序踩到野指针触发 `SIGSEGV`（段错误）信号。

**2. 内核处理信号的标准流程：**
- **保存现场（压栈）**：当一个进程收到信号时，内核会强行中断当前执行流。为了以后还能恢复，内核会把当前进程的**所有寄存器状态（Context）**，硬生生压入该进程的**用户态栈**中，形成一个 `Sigframe`（信号帧）。
- **执行 Handler**：内核让程序跳去执行信号处理函数（Signal Handler）。
- **恢复现场（sigreturn）**：当 Handler 执行完毕后，会触发一个隐藏的系统调用 `rt_sigreturn`（在 64 位下，系统调用号是 **15**）。内核看到 15，就会去栈上读取刚才保存的 `Sigframe`，把寄存器全部恢复，继续执行被打断的地方。

**3. SROP 的致命漏洞：**
内核在恢复现场时，**完全信任用户态的栈**！也就是说，如果我们能骗过程序，让它触发 `sigreturn` 系统调用（`rax = 15`），内核就会傻乎乎地去读我们**提前伪造好放在栈上的 `Sigframe`**。
我们可以把 `Sigframe` 里的 `rdi` 设成 `/bin/sh`，`rax` 设成 59（execve），`rip` 设成 `syscall`。内核一恢复，直接送我们一个 Shell。

## 三、 适用条件（前置条件）
1. 必须是 64 位程序（32 位的 SROP 较少见且难用）。
2. 程序里必须有一个 `syscall` 指令。
3. 有办法把 `rax` 设置为 `15`（`sigreturn` 的系统调用号）。
4. 栈空间足够大，能放下一个完整的 `SigreturnFrame`（通常为 248 字节）。

## 四、 Payload 构造模板（结合 pwntools）
利用 pwntools 的 `SigreturnFrame()` 模块，我们能一键生成 248 字节的上下文结构。

假设我们要执行 `execve("/bin/sh", 0, 0)`：
- `rax = 59`
- `rdi = /bin/sh 的地址`
- `rsi = 0`，`rdx = 0`
- `rip = syscall 指令的地址`
```python
from pwn import *

context(log_level='debug', arch='amd64', os='linux')
elf = ELF('./pwn')
p = process('./pwn')

# 假设已知偏移量、syscall 地址、以及控制 rax 的 gadget
offset = 0x20
syscall_ret = 0x400... # 一个 syscall; ret 的地址
pop_rax_ret = 0x400... # 一个 pop rax; ret 的地址
binsh_addr  = elf.bss() + 0x800 # 需要把 /bin/sh 写到这，或程序里现成的

# 1. 伪造 SigreturnFrame
frame = SigreturnFrame()
frame.rax = 59           # execve 的系统调用号
frame.rdi = binsh_addr   # /bin/sh 的地址
frame.rsi = 0            # argv = 0
frame.rdx = 0            # envp = 0
frame.rip = syscall_ret  # 恢复后直接执行 syscall
frame.rsp = binsh_addr   # 随便填，不为空即可

# 2. 构造 Payload
payload  = b'A' * offset
payload += p64(pop_rax_ret) # 准备设置 rax=15
payload += p64(15)          # rax = 15 (sigreturn)
payload += p64(syscall_ret) # 触发 syscall (此时会陷入内核去读 frame)
payload += bytes(frame)     # 伪造的上下文结构 (248字节)

p.recvuntil(b"Input:")
p.sendline(payload)
p.interactive()
```

## 五、 高级利用技巧（没有 pop rax 怎么办？）
如果题目极其变态，连 `pop rax; ret` 都给你删了，你怎么把 `rax` 变成 15？
- **利用 `read` 函数**：`read` 函数执行完毕后，返回的**实际读取字节数会存放在 `rax` 中**。你可以先调用一次 `read(0, bss, 15)`，然后给它发送 15 个字节。执行完 `read`，`rax` 就稳稳地变成了 15！紧接着接上 `syscall` 即可。
- **利用 `alarm` 或 `syscall` 的返回值**：有时候某些系统调用执行失败或成功后的返回值，恰好是 15。

## 六、 常见踩坑点
1. **栈空间不够**：`SigreturnFrame` 长达 248 字节，如果你的溢出长度连 248 字节都没有，必须配合 **栈迁移（Stack Pivot）** 把栈搬到 `.bss` 段再触发 SROP。
2. **`/bin/sh` 的地址**：通常用 `read` 把 `/bin/sh` 读进 `.bss`，或者直接利用 `libc` 里的 `/bin/sh` 地址（如果你已知 libc 基址）。
3. **`syscall` 之后的 `ret`**：触发 `sigreturn` 的 `syscall` 后面最好跟一个 `ret`，否则内核恢复上下文回来可能会因为栈不对齐崩溃。
4. **32 位的 SROP**：32 位的 `sigreturn` 系统调用号是 `119`，而且它的 `Sigframe` 结构和 64 位不同，pwntools 也支持生成，但题目极度罕见。

## 七、 与其他技术的对比
- **常规 ROP**：一个个用 `pop` 拼凑寄存器，像个苦力。
- **Ret2Csu**：找不到 `pop` 时的“补丁替代”。
- **SROP**：降维打击。不需要找一堆繁琐的 Gadget，只需要一个 `syscall` 和一个能控 `rax` 的漏洞，利用 Linux 处理信号的底层逻辑，直接让操作系统帮你把所有寄存器“一键还原”。