# Pwn 知识笔记：Ret2Syscall (返回到系统调用)

## 一、 什么是 Ret2Syscall？
`Ret2Syscall` 是 Pwn 技术中一种绕过常规 C 语言函数（如 `system`），直接通过底层的**系统调用（System Call）**让 CPU 执行命令的利用手法。

**核心思想**：既然程序里没有 `system` 函数，那我就自己拼凑寄存器，直接在底层触发 `execve("/bin/sh", 0, 0)` 来获取 Shell。

## 二、 适用场景与识别特征
在拿到一道题时，如果出现以下情况，大概率需要用到 Ret2Syscall：
1. **程序是静态链接（Static Linked）**：程序把整个 libc 库打包进了自己内部，无法像 Ret2Libc 那样利用动态链接库。
2. **程序里没有现成的 `system` 或后门**。
3. **程序里必然有 `syscall`（64位）或 `int 0x80`（32位）指令**（只要是正常的 Linux 程序，必然包含这些汇编指令）。

## 三、 核心原理：如何执行系统调用
要让系统执行 `execve`，必须按照操作系统的规矩，将对应的参数填入寄存器中。

### 1. 64 位系统 (x86-64)
*   `rax = 59` （系统调用号：execve）
*   `rdi` = 指向 "/bin/sh" 字符串的地址 （第一个参数）
*   `rsi = 0` （第二个参数：argv，设为 0 即可）
*   `rdx = 0` （第三个参数：envp，设为 0 即可）
*   最后执行 **`syscall`** 指令。

### 2. 32 位系统 (x86)
*   `eax = 11` （系统调用号：execve）
*   `ebx` = 指向 "/bin/sh" 字符串的地址
*   `ecx = 0`
*   `edx = 0`
*   最后执行 **`int 0x80`** 指令。

## 四、 Payload 构建模板（ROP 链）

### 🌟 64 位 Payload 结构：
```text
垃圾填充 (覆盖到返回地址)
+ 地址(pop rax; ret)
+ 59                     <-- 弹给 rax
+ 地址(pop rdi; ret)
+ 地址("/bin/sh")        <-- 弹给 rdi
+ 地址(pop rsi; ret)
+ 0                      <-- 弹给 rsi
+ 地址(pop rdx; ret)
+ 0                      <-- 弹给 rdx
+ 地址(syscall; ret)
```

### 🌟 32 位 Payload 结构：
```text
垃圾填充 (覆盖到返回地址)
+ 地址(pop eax; ret)
+ 11
+ 地址(pop ebx; ret)
+ 地址("/bin/sh")
+ 地址(pop ecx; ret)
+ 0
+ 地址(pop edx; ret)
+ 0
+ 地址(int 0x80)
```

## 五、 实战难点：程序里没有 `/bin/sh` 怎么办？
程序里既没有 `system`，也没有 `/bin/sh` 字符串时，可以通过以下方式解决：
1. 寻找一个可写且地址固定的内存区域（如 `.bss` 段）。
2. 利用程序的 `read` 函数，构造 ROP 链执行 `read(0, bss_addr, 8)`。
3. 手动输入 `/bin/sh` 字符串存入该地址。
4. 后续再执行上述的寄存器赋值链，将 `rdi`（或 `ebx`）指向该 `.bss` 地址即可。

## 六、 辅助工具：如何快速寻找 Gadget
遇到此类题目，直接使用 ROPgadget 寻找对应的零件：

```bash
# 寻找 64 位所需零件
ROPgadget --binary ./pwn | grep "pop rax ; ret"
ROPgadget --binary ./pwn | grep "pop rdi ; ret"
ROPgadget --binary ./pwn | grep "pop rsi ; ret"
ROPgadget --binary ./pwn | grep "pop rdx ; ret"
ROPgadget --binary ./pwn | grep "syscall"
```

## 七、 总结对比
*   **Ret2Libc**：依赖动态链接库。需要先泄露真实地址，算偏移，通常需要二次发送 Payload。
*   **Ret2Syscall**：依赖程序内自带的 `syscall` 指令。无需关心库基址，通常一次溢出即可打通（前提是能找齐所需寄存器）。