#!/bin/bash
set -e

# ============================================
#   IEI Timer Faster 桌面版 一键构建 (macOS)
# ============================================
# INSPUR-80: macOS 平台构建脚本
#
# 前置条件:
#   - Python 3.8+
#   - macOS 10.13+（pywebview Cocoa/WebKit 后端）
#
# 产物:
#   dist/IEI_Timer_Faster_Setup.dmg — 安装镜像（拖拽到 /Applications）
# ============================================

# 确保从脚本所在目录执行
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  IEI Timer Faster 桌面版 一键构建 (macOS)"
echo "============================================"
echo ""

# ============================================================
#  步骤 1: 检查 Python 3
# ============================================================
echo "[1/5] 检查 Python 3..."
PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "[X] 未找到 Python 3，请先安装 Python 3.8+"
    echo "     下载: https://www.python.org/downloads/"
    exit 1
fi
$PYTHON --version

# ============================================================
#  步骤 2: 安装依赖
# ============================================================
echo "[2/5] 安装依赖..."
$PYTHON -m pip install -r requirements.txt pyinstaller || {
    echo "[X] 依赖安装失败"
    exit 1
}
echo "[OK] 依赖已就绪"

# ============================================================
#  步骤 3: 准备 macOS 图标 (.icns)
# ============================================================
echo "[3/5] 准备图标..."
ICON_OK=0
if [ -f "iei_timer.icns" ]; then
    ICON_OK=1
    echo "[OK] iei_timer.icns 已存在"
elif [ -f "iei_timer.ico" ]; then
    echo "    尝试从 iei_timer.ico 转换..."
    # 使用 Python 提取 .ico 中的最大图标 → PNG → iconutil 生成 .icns
    $PYTHON -c "
import os, struct, shutil

# 1) 从 .ico 提取最大尺寸的 PNG
with open('iei_timer.ico', 'rb') as f:
    data = f.read()
count = data[4] | (data[5] << 8)
best_size, best_off, best_len = 0, 0, 0
for i in range(count):
    o = 6 + i * 16
    w = data[o]; h = data[o + 1]
    if w == 0: w = 256
    if h == 0: h = 256
    sz = w * h
    es, eo = struct.unpack_from('<II', data, o + 8)
    if sz > best_size:
        best_size, best_off, best_len = sz, eo, es
if best_off == 0:
    exit(1)
img = data[best_off : best_off + best_len]
if img[:8] != b'\x89PNG\r\n\x1a\n':
    exit(1)
with open('iei_timer.png', 'wb') as f:
    f.write(img)

# 2) sips → iconset → iconutil
if not shutil.which('iconutil'):
    print('[!] iconutil 不可用，跳过 .icns 生成（应用使用默认图标）')
    exit(0)

iconset = 'tmp.iconset'
os.makedirs(iconset, exist_ok=True)
sizes = [16, 32, 64, 128, 256, 512]
for sz in sizes:
    os.system(f'sips -z {sz} {sz} iei_timer.png --out {iconset}/icon_{sz}x{sz}.png 2>/dev/null')
    if sz <= 256:
        os.system(f'sips -z {sz*2} {sz*2} iei_timer.png --out {iconset}/icon_{sz}x{sz}@2x.png 2>/dev/null')
os.system(f'iconutil -c icns {iconset} -o iei_timer.icns 2>/dev/null')
shutil.rmtree(iconset, ignore_errors=True)
if os.path.exists('iei_timer.icns'):
    print('[OK] iei_timer.icns 已生成')
else:
    print('[!] .icns 生成失败，应用使用默认图标')
" 2>/dev/null || true
    [ -f "iei_timer.icns" ] && ICON_OK=1
fi
if [ $ICON_OK -eq 0 ]; then
    echo "[!] 图标未就绪，应用将使用默认图标"
fi

# ============================================================
#  步骤 4: PyInstaller 构建
# ============================================================
echo "[4/5] PyInstaller 构建中...（约 2-5 分钟）"
echo ""

# 清理旧的构建产物
rm -rf build/service 2>/dev/null || true
rm -rf "dist/IEI Timer Faster" "dist/IEI Timer Faster.app" 2>/dev/null || true

$PYTHON -m PyInstaller --noconfirm service.spec || {
    echo ""
    echo "[X] 构建失败，请检查上方错误信息"
    echo "   常见原因:"
    echo "    1. 依赖未安装 — 执行 pip install -r requirements.txt pyinstaller"
    echo "    2. 磁盘空间不足"
    exit 1
}

echo ""
echo "============================================"
echo "  PyInstaller 构建完成!"
echo "============================================"
echo ""

# ============================================================
#  步骤 5: 清理中间产物 + 打包 .dmg
# ============================================================
echo "[5/5] 打包 .dmg 安装镜像..."

# 删除 COLLECT onedir 中间产物（.app bundle 已自包含所有文件）
if [ -d "dist/IEI Timer Faster" ]; then
    rm -rf "dist/IEI Timer Faster"
    echo "[OK] 中间产物已清理"
fi

if [ ! -d "dist/IEI Timer Faster.app" ]; then
    echo "[X] .app bundle 未生成，请检查 PyInstaller 输出"
    echo "   预期: dist/IEI Timer Faster.app/"
    echo "   实际:"
    ls -la dist/ 2>/dev/null || echo "    （dist/ 为空）"
    exit 1
fi

# 移除旧的 .dmg
rm -f "dist/IEI_Timer_Faster_Setup.dmg"

# 创建 .dmg
echo "[OK] 正在创建 .dmg..."
hdiutil create \
    -volname "IEI Timer Faster" \
    -srcfolder "dist/IEI Timer Faster.app" \
    -ov -format UDZO \
    "dist/IEI_Timer_Faster_Setup.dmg" || {
    echo "[X] .dmg 创建失败，请手动执行:"
    echo "    hdiutil create -volname \"IEI Timer Faster\" -srcfolder \"dist/IEI Timer Faster.app\" -ov -format UDZO dist/IEI_Timer_Faster_Setup.dmg"
    exit 1
}

# 清理 .app（已打包进 .dmg）
rm -rf "dist/IEI Timer Faster.app"
echo "[OK] .app 已清理（已打包进 .dmg）"

echo ""
echo "============================================"
echo "  全流程构建完成!"
echo ""
echo "  安装镜像: dist/IEI_Timer_Faster_Setup.dmg"
echo ""
echo "  使用方法:"
echo "    1. 双击 IEI_Timer_Faster_Setup.dmg"
echo "    2. 将 IEI Timer Faster.app 拖入 Applications 文件夹"
echo "    3. 从 Launchpad 或 Applications 目录启动"
echo ""
echo "  卸载:"
echo "    将 /Applications/IEI Timer Faster.app 移到废纸篓"
echo "    用户数据目录: ~/Library/Application Support/gongshi/"
echo "============================================"
