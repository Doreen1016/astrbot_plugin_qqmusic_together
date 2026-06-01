# QQ音乐一起听歌插件

这是一个用于 AstrBot 的 QQ音乐一起听歌感知插件。它可以读取当前电脑端 QQ音乐正在播放的歌曲和歌词，并提供一个网页面板供查看。

## 功能

- 自动读取 QQ音乐 窗口标题，获取当前播放的歌曲名和歌手。
- 自动从网易云音乐或 LRCLIB 获取歌词。
- 提供一个本地网页面板，实时显示当前歌曲和歌词。
- 提供大模型工具，允许大模型查询当前播放状态。

## 安装

1. 将本插件文件夹放入 AstrBot 的 `data/plugins` 目录下。
2. 重启 AstrBot。

## 依赖

本插件需要以下 Python 库：
- `psutil`
- `pywin32` (提供 `win32gui` 和 `win32process`)
- `aiohttp`
- `uvicorn`
- `fastapi`

你可以通过以下命令安装依赖：
```bash
pip install -r requirements.txt
```

## 配置

在 AstrBot 的插件配置页面，你可以配置以下选项：
- `poll_interval`: 轮询间隔(秒)，默认 3 秒。
- `enable_auto_monitor`: 是否启用后台自动监测，默认开启。
- `enable_web_panel`: 是否启用网页面板，默认开启。
- `web_host`: 网页监听地址，默认 `127.0.0.1`。
- `web_port`: 网页端口，默认 `8765`。

## 使用方法

1. 确保电脑端 QQ音乐 正在运行并播放歌曲。
2. 确保 AstrBot 已启动并加载了本插件。
3. 如果启用了网页面板，可以在浏览器中访问 `http://127.0.0.1:8765` 查看当前播放状态。
4. 在与大模型对话时，大模型可以调用 `qqmusic_together_status` 工具查询当前播放状态。

## 注意事项

- 本插件仅支持 Windows 系统，因为依赖于 Windows API 读取窗口标题。
- 确保 QQ音乐 窗口没有被完全最小化到系统托盘，否则可能无法读取到窗口标题。

## 作者

dd

---

【astrbot插件分享】QQ音乐一起听歌感知插件

✨ 插件功能：
能让你的 AI 实时感知你电脑端 QQ音乐 正在播放的歌曲和歌词。纯本地读取窗口标题，不截图，安全轻量。

💡 效果体验：
当你邀请 AI 一起听歌，或者问它“我们在听什么”时，它可以直接读取当前播放状态，陪你聊歌词、聊氛围。
插件还自带一个极简的本地网页面板，可以实时显示当前歌曲和滚动歌词。

🛠️ 使用方法：
1. 将插件文件夹放入 AstrBot 的 data/plugins 目录下。
2. 在终端运行 pip install -r requirements.txt 安装依赖。
3. 重启 AstrBot，在电脑端打开 QQ音乐 播放歌曲即可。

🔗 项目地址：
https://github.com/Doreen1016/astrbot_plugin_qqmusic_together