# P view

一款遵循 **Windows 11 设计语言**（参照系统"照片"应用）的极速图片查看器，功能对标 BandiView，
**无广告、无弹窗、无注册订阅**，仅支持 **简体中文 / English** 两种界面语言。

## 核心功能

### 图片浏览（BandiView 功能全保留）
- 直接查看压缩包内图片（无需解压）：**ZIP / CBZ / 7Z / TAR / TAR.GZ / RAR / CBR**
- 支持加密压缩包（ZIP-AES / ZipCrypto / 7Z 加密，弹出密码框；RAR 加密需系统解压工具支持）
- 常规格式：JPG / PNG / GIF / WebP / BMP / TIFF / ICO / TGA / PSD / DDS / EXR 等
- 现代格式：**HEIC / HEIF / HIF / AVIF**
- RAW 相机格式：CR2 / CR3 / NEF / ARW / DNG / ORF / RAF / RW2 等（同名 RAW+JPG 可合并显示）
- 动图播放：GIF / 动图 WebP / APNG（播放/暂停、逐帧、倍速帧率还原）

### 查看控制
- 查看模式：原始 100% / 适应窗口 / 适应宽度 / 适应高度 / 拉伸小图
- **智能双页模式**（左→右 / 右←左，漫画阅读）、**条漫 Webtoon 长条模式**
- 缩放锁定（跨图片保持缩放比例）、鼠标滚轮翻页/缩放可切换
- 旋转 90°/180°、水平/垂直翻转、基于 EXIF 自动旋转
- 图像效果：反色 / 灰度 / 复古 / Gamma / 亮度 / 对比度 / 饱和度 / RGB 通道 / 锐化滤镜
- 插值质量切换（快速双线性 / 高质量）
- 透明区域背景：棋盘格 / 白 / 黑；图像区背景：自动取色 / 深灰 / 浅灰 / 白 / 黑

### 幻灯片与全屏
- 幻灯片放映：1-60 秒间隔、循环、随机、切换特效（淡入淡出 / 滑动）
- 全屏（F11 / F / Alt+Enter）、窗口置顶、窗口适应图片

### 文件管理
- 缩略图栏（底部胶片条）与图像导航器（缩略图网格）
- 排序：名称 / 修改日期 / 大小 / 类型，支持降序
- 重命名（F2）、删除到回收站（Del）、在资源管理器中显示（Ctrl+Enter）
- 复制图像 / 路径 / 文件到剪贴板，从剪贴板粘贴打开（Ctrl+V）
- **批量图像转换**（Ctrl+T）：格式 / 质量 / 缩放 / 旋转 / 输出位置 / 命名规则
- 打印（Ctrl+P）、设为桌面背景（填充/适应/居中）
- 书签系统（B 添加 / 书签管理器）、最近打开、记忆压缩包内上次浏览位置
- 图片收藏夹 1/2（设置中配置路径，Ins 快速归档）
- 用外部编辑器打开（Ctrl+E，可在设置指定 Photoshop 等）

### Windows 11 风格 UI
- 自定义无边框标题栏 + 系统圆角 + Mica 云母材质（跟随系统主题时）
- 深色 / 浅色 / 跟随系统主题，自动读取系统强调色
- 悬浮式顶部/底部工具栏、Toast 通知、Fluent 风格图标
- 语言：简体中文 / English（切换后自动重启生效）

## 快捷键（节选）

| 按键 | 功能 | 按键 | 功能 |
|---|---|---|---|
| → / ↓ / Space | 下一张 | ← / ↑ | 上一张 |
| Home / End | 第一张 / 最后一张 | [ / ] | 上/下一个文件夹(压缩包) |
| 0 / 9 / 8 | 100% / 适应窗口 / 适应宽度 | 7 / 6 / 5 | 双页→ / 双页← / 条漫 |
| Z | 拉伸小图 | Alt+←/→/↓ | 旋转 |
| Ctrl+M / Ctrl+F | 水平 / 垂直翻转 | Ctrl+I / Ctrl+Y | 反色 / 灰度 |
| Ctrl+G | 图像调整 | F8 | 幻灯片 |
| Enter | 导航器 | Tab | 文件信息/EXIF |
| B | 添加书签 | F2 / Del | 重命名 / 删除 |
| Ctrl+T | 批量转换 | Ctrl+P | 打印 |
| F11 / F | 全屏 | Ctrl+A | 窗口置顶 |

完整列表见：设置 → 快捷键（F1）。

## 运行

- 直接运行 `dist/Pview/Pview.exe`（绿色版，无需安装）
- 源码运行：`python main.py [图片/文件夹/压缩包路径]`
- 支持"打开方式"关联：选择 Pview.exe 即可

## 技术栈

Python 3.13 + PySide6 (Qt 6) + Pillow + py7zr + pyzipper + rarfile + pillow-heif + pillow-avif + psd-tools，PyInstaller 打包。

RAR 解压优先使用 WinRAR 的 UnRAR.exe（如已安装），否则使用系统自带 bsdtar
（加密 RAR 需 UnRAR 支持）。

## 目录结构

```
PView/
├── main.py            # 程序入口（开发运行）
├── Pview.spec         # PyInstaller 打包配置
├── pview/             # 源码包（界面/查看器/设置等模块）
├── assets/            # 图标源文件（pview.ico/png）
├── tools/             # 开发与自动化验证脚本
├── docs/              # 截图、快捷键报告、验证输出（verify_out）
├── release/           # 分发压缩包（Pview-win64.zip）
├── dist/Pview/        # 打包产物：Pview.exe + _internal（可直接分发）
└── dist_old*/         # 上一版本备份（保留一个）
```
