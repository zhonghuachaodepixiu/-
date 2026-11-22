# Pwn 进阶笔记：栈迁移（Stack Pivot）

## 一、 核心思想与背景
- **核心思想**：把它想象成**“空间不足时的搬家”**。当程序发生栈溢出时，如果给你的输入空间特别小（连填满缓冲区加一个返回地址都不够），你根本无法在栈上塞下一长串的 ROP 链。这时候，我们就需要利用程序里的 `read` 函数，把长长的 ROP 链写到一块又大又可控的内存（通常是 `.bss` 段），然后用 `leave; ret` 指令，强行把栈指针 `rsp` 搬家到那里，继续执行。

## 二、 适用条件（前置条件）
1. **栈溢出空间极小**：比如只能输入 16 或 32 字节，放不下完整的 ROP 链。
2. **存在可写且已知的地址**：通常是 `.bss` 段（No PIE 下固定），用于存放长的 ROP 链。
3. **有可用的 `read` 或 `gets`**：用来把第二段长链写进 `.bss`。
4. **必须存在 `leave; ret` Gadget**：这是完成“空间折跃”的核心工具。

## 三、 底层原理（核心魔法：两次 `leave; ret`）
`leave` 指令等价于 `mov rsp, rbp; pop rbp`；`ret` 指令等价于 `pop rip`。
整个搬家过程，程序会执行两次 `leave; ret`：

**第一次 `leave; ret`（程序原生的）**：
1. `leave`：`rsp` 被设为当前 `rbp`；然后把栈顶的值（被你覆盖的**假 rbp**）弹给 `rbp`。此时 `rsp` 指向了覆盖的返回地址（你填的 `leave_ret`）。
2. `ret`：弹出 `leave_ret` 的地址，程序跳去执行第二次搬家。

**第二次 `leave; ret`（你填的 Gadget）**：
3. `leave`：此时 `rbp` 是你伪造的地址（比如 `bss_addr`）。`rsp` 被设为你伪造的地址；`pop rbp` 让 `rsp` 挪到 `bss_addr + 8`。
4. `ret`：从 `bss_addr + 8` 弹出下一个地址，程序开始在你布置的 `.bss` 长链上狂欢！

## 四、 Payload 构造模板（两段式）
假设：溢出偏移量是 `offset`；新家地址是 `bss_addr`；有个 `leave_ret` gadget。

### 第一段：造新家（强逼程序去执行 `read` 并触发搬家）
```python
# 第一段是手搓的：垃圾填充 + read_plt + leave_ret + read的三个参数
payload1  = b'A' * offset
payload1 += p64(read_plt)    # 执行 read
payload1 += p64(leave_ret)   # read 执行完后，跳到 leave_ret 触发搬家
payload1 += p64(0)           # read 参数1：fd = 0
payload1 += p64(bss_addr)    # read 参数2：把数据写到 bss 段
payload1 += p64(0x200)       # read 参数3：读 512 字节（足够长了）

p.recvuntil(b"Input:")
p.send(payload1)             # 发完这段，程序开始执行 read 等你的长链
```

### 第二段：造长链（真正的 ROP 链）
因为第一段的 `read` 正在等你输入，你紧接着发过去的数据会被写到 `bss_addr`。
```python
# 第二段可以用 pwntools 自动生成长链
rop = ROP(elf)
# 比如打 ORW 或者 system("/bin/sh")
rop.system(next(elf.search(b'/bin/sh\x00')))
real_rop_chain = rop.chain()

p.send(real_rop_chain)       # 发完这段，read 读完触发第二次 leave_ret，直接起飞
```

## 五、 常见踩坑点
1. **`send` 与 `sendline`**：第一段千万不要用 `sendline`，因为多出来的 `\n` 会留在缓冲区，被接下来的 `read` 当作数据读进去，导致栈错位。
2. **假 `rbp` 的地址**：在 64 位下，通常要把旧 `rbp` 覆盖为 `bss_addr`（或 `bss_addr - 8`）。具体填哪个，取决于第二次 `leave` 时栈顶在哪。如果差 8 个字节，可以在长链里垫几个废数据。
3. **数据包粘连**：如果程序执行太快，第一段的 `read` 可能没来得及准备好，你第二段就发过去了。可以在两次 `send` 之间加个 `sleep(0.1)`。
4. **新家的地址**：尽量选 `.bss` 段靠后的位置（如 `elf.bss() + 0x800`），防止覆盖程序正在使用的全局变量（如 `stdin/stdout`）。

## 六、 与其他技术的对比
- **Ret2Libc / Ret2Syscall**：解决“没后门”和“没地址”的问题。
- **栈迁移（Stack Pivot）**：解决“溢出了，但没地方写 ROP 链”的物理空间问题。常常作为前缀招式，结合 ORW 链或 Ret2Csu 一起使用。