# Pwn进阶：Ret2libc 攻击原理解析与实战

## 一、什么是 Ret2libc？
* 在开启了 NX（栈不可执行）保护，且程序中没有现成后门（`system("/bin/sh")`）的情况下，利用栈溢出，引导程序去执行 Linux 系统自带的动态链接库（libc.so.6）中的 `system` 函数，从而拿到 Shell。

* 核心思想：既然程序里没有，我就去系统的大仓库（libc）里借。

## 二、核心痛点：system 和 /bin/sh 不在一块怎么打？
* 在内存中，`system` 函数的地址和 `/bin/sh` 字符串的地址通常隔着十万八千里。且由于 ASLR（地址随机化），每次运行地址都在变。

* 解决办法：利用汇编底层逻辑，通过栈（Stack）和 Gadget（如 pop rdi; ret）把这两个不连续的内存地址“强制缝合”成一次函数调用。

## 三、底层执行逻辑还原（CPU视角）
* 假设我们已经拿到了 `system` 地址和 `/bin/sh` 地址，构造了如下 `Payload`：

* `payload = [垃圾数据] + [pop rdi; ret地址] + ["/bin/sh"地址] + [system地址]`

* 当 CPU 触发 `ret` 时，它的大流水线是这样的：

* 1. 执行 `ret`：从栈顶读取 `pop rdi`; `ret` 的地址，跳过去。

* 2. 执行 `pop rdi`：将栈上的下一个值（"`/bin/sh`"的地址）弹出，精准塞进 `RDI` 寄存器里。（完成了参数传递）

* 3. 执行 `Gadget` 里的 `ret`：再次从栈顶读取 `system` 的地址，跳过去。

* 4. 执行 `system`：`system` 函数检查 `RDI` 寄存器，发现有值，顺着地址找到 "`/bin/sh`" 并执行。

* 这就好比用 Gadget 搭建了一座桥，把参数和函数强行接力到了一起。

## 四、Ret2libc 完整利用流程（三步走）

* 前提：题目通常会附带一个 libc.so.6 文件，并存在信息泄露点（如通过 `puts` 或 `write` 打印 GOT 表内容）。

* 第一步：泄露真实地址（Info Leak）

* 构造 Payload 1：`payload1 = [垃圾数据] + puts@plt + main函数地址 + puts@got`

* 作用：让程序执行 `puts` 函数，把 `puts` 函数在内存中的真实地址打印出来。然后返回 `main` 重新开始。

* 第二步：计算基址与目标地址

* `libc_base = 泄露的puts地址 - puts在libc中的偏移`

* `system_addr = libc_base + system在libc中的偏移`

* `bin_sh_addr = libc_base + "/bin/sh"在libc中的偏移`

* 第三步：召唤神龙（Get Shell）

* 构造 Payload 2：`payload = [垃圾数据] + pop rdi; ret 地址 + bin_sh_addr + system_addr`

* 发送后，成功拿下 shell。

## 五、实战防坑指南（极其重要！）

* 1. 64位栈对齐问题：64位系统下，直接跳 system 可能会报 SIGSEGV 崩溃。需要在 pop rdi 之前垫一个单独的 ret 指令地址。

* 2. Libc 版本必须对口：必须用题目附件给的 libc，不能用本机 Kali 的，否则偏移量全错。