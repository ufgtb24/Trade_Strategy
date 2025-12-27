# Ubuntu uv Tkinter 字体显示修复指南

## 问题描述

Ubuntu 系统中，uv 环境的 Tkinter 应用可能出现字体显示问题：
- 文字边缘锯齿明显
- 字体模糊、不清晰
- 字体渲染质量差

**原因**：uv 打包的 Tk/Tcl 库与系统字体渲染不兼容

## 解决方案

将 uv Python 的 Tk/Tcl 库替换为系统库的符号链接，利用系统的字体配置和反锯齿支持。

---

## 版本兼容性

**关键**：系统 Tcl/Tk 版本必须与 uv Python 所需版本匹配。

| Ubuntu 版本 | 系统 Tcl/Tk | 兼容的 Python 版本 |
|-------------|-------------|-------------------|
| 22.04 LTS   | 8.6.12      | Python 3.12.x     |
| 24.04 LTS   | 8.6.14      | Python 3.13.x     |

检查系统版本：
```bash
dpkg -l | grep libtcl8
```

检查 uv Python 所需版本：
```bash
head -20 ~/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib/tcl8.6/init.tcl | grep "package require"
```

---

## 配置步骤

### 1. 确认系统库存在

```bash
ls /usr/lib/x86_64-linux-gnu/libtk8.6.so
ls /usr/lib/x86_64-linux-gnu/libtcl8.6.so
```

如果不存在，需要先安装：
```bash
sudo apt update
sudo apt install tk-dev tcl-dev python3-tk
```

### 2. 定位 uv Python 库路径

```bash
ls ~/.local/share/uv/python/
```

选择与系统 Tcl/Tk 版本兼容的 Python 版本，例如 Ubuntu 22.04 选择 `cpython-3.12.12-linux-x86_64-gnu`

设置变量：
```bash
UV_LIB=~/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib
```

### 3. 备份原始文件

```bash
mv ${UV_LIB}/libtk8.6.so ${UV_LIB}/libtk8.6.so.bak
mv ${UV_LIB}/libtcl8.6.so ${UV_LIB}/libtcl8.6.so.bak
```

### 4. 创建符号链接

```bash
ln -s /usr/lib/x86_64-linux-gnu/libtk8.6.so ${UV_LIB}/libtk8.6.so
ln -s /usr/lib/x86_64-linux-gnu/libtcl8.6.so ${UV_LIB}/libtcl8.6.so
```

### 5. 验证配置

```bash
ls -la ${UV_LIB}/libtk8.6.so ${UV_LIB}/libtcl8.6.so
```

应该看到：
```
lrwxrwxrwx ... libtk8.6.so -> /usr/lib/x86_64-linux-gnu/libtk8.6.so
lrwxrwxrwx ... libtcl8.6.so -> /usr/lib/x86_64-linux-gnu/libtcl8.6.so
```

### 6. 重建项目虚拟环境

```bash
cd /your/project
rm -rf .venv
uv venv --python 3.12.12
uv sync
```

### 7. 测试

```bash
.venv/bin/python -c "import tkinter; root = tkinter.Tk(); root.destroy(); print('OK')"
```

---

## 恢复原始配置

```bash
UV_LIB=~/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu/lib

rm ${UV_LIB}/libtk8.6.so ${UV_LIB}/libtcl8.6.so
mv ${UV_LIB}/libtk8.6.so.bak ${UV_LIB}/libtk8.6.so
mv ${UV_LIB}/libtcl8.6.so.bak ${UV_LIB}/libtcl8.6.so
```

---

## 常见错误

### version conflict for package "Tcl"

```
version conflict for package "Tcl": have 8.6.12, need exactly 8.6.14
```

**原因**：Python 版本与系统 Tcl/Tk 版本不匹配

**解决**：选择兼容的 Python 版本（见版本兼容性表格）

---

## AI 执行注意事项

1. **版本检查优先**：执行前必须检查系统与 uv Python 的 Tcl/Tk 版本是否兼容
2. **路径替换**：将示例中的 Python 版本号替换为实际版本
3. **系统架构**：如果不是 x86_64，需调整库路径（如 `aarch64-linux-gnu`）
4. **无需 sudo**：所有操作都在用户目录下进行

---

**参考来源**：https://blog.csdn.net/2301_77162941/article/details/155105142
