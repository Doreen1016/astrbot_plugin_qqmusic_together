import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp
from astrbot import logger
from astrbot.api.all import llm_tool
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent

try:
    import psutil
    import win32gui
    import win32process
except Exception:
    psutil = None
    win32gui = None
    win32process = None


@register(
    "astrbot_plugin_qqmusic_together",
    "沈星回",
    "QQ音乐一起听歌感知：读取当前播放歌曲与歌词",
    "0.1.0",
)
class QQMusicTogetherPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_qqmusic_together")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.data_dir / "current_song.json"
        self.lyrics_path = self.data_dir / "current_lyrics.txt"
        self.log_path = self.data_dir / "song_log.txt"
        self.poll_interval = int(self.config.get("poll_interval", 3) or 3)
        self.enable_auto_monitor = bool(self.config.get("enable_auto_monitor", True))
        self._task: Optional[asyncio.Task] = None
        self._last_title = "" 

    async def initialize(self):
        if self.enable_auto_monitor:
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info("[QQ音乐一起听歌] 后台监测已启动")

    async def terminate(self):
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[QQ音乐一起听歌] 已停止")

    def _read_qqmusic_title(self) -> Optional[str]:
        if not psutil or not win32gui or not win32process:
            return None

        candidates = []

        def enum_callback(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd).strip()
                if not title:
                    return
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                try:
                    proc = psutil.Process(pid)
                    pname = (proc.name() or "").lower()
                except Exception:
                    return
                if "qqmusic" not in pname:
                    return
                if title.lower() in {"qqmusic", "qq音乐"}:
                    return
                if " - " in title or "—" in title or "《" in title:
                    candidates.append(title)
            except Exception:
                return

        try:
            win32gui.EnumWindows(enum_callback, None)
        except Exception:
            return None

        return candidates[0] if candidates else None

    def _parse_song(self, raw_title: str) -> Dict[str, str]:
        title = raw_title.strip()
        title = re.sub(r"\s*-\s*QQ音乐\s*$", "", title, flags=re.I)
        title = re.sub(r"\s*\|\s*QQ音乐\s*$", "", title, flags=re.I)

        song = title
        artist = ""
        if " - " in title:
            parts = [p.strip() for p in title.split(" - ") if p.strip()]
            if len(parts) >= 2:
                song = parts[0]
                artist = parts[1]
        elif "—" in title:
            parts = [p.strip() for p in title.split("—") if p.strip()]
            if len(parts) >= 2:
                song = parts[0]
                artist = parts[1]

        return {"raw_title": raw_title, "song": song, "artist": artist}

    async def _fetch_lyrics_lrclib(self, song: str, artist: str = "") -> str:
        # 优先尝试网易云接口
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://music.163.com/",
        }
        timeout = aiohttp.ClientTimeout(total=12)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                search_url = "http://music.163.com/api/search/get/web"
                data = {"s": f"{song} {artist}".strip(), "type": 1, "limit": 1, "offset": 0}
                async with session.post(search_url, headers=headers, data=data) as resp:
                    res = await resp.json(content_type=None)
                    songs = res.get("result", {}).get("songs", [])
                    if songs:
                        song_id = songs[0]["id"]
                        lyric_url = f"http://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
                        async with session.get(lyric_url, headers=headers) as l_resp:
                            l_res = await l_resp.json(content_type=None)
                            lrc = l_res.get("lrc", {}).get("lyric", "")
                            if lrc:
                                lrc = re.sub(r"\[.*?\]", "", lrc)
                                lines = [line.strip() for line in lrc.splitlines() if line.strip()]
                                return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[QQ音乐一起听歌] 网易云歌词检索失败: {e}")

        # 降级到 LRCLIB
        params = {"track_name": song}
        if artist:
            params["artist_name"] = artist

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get("https://lrclib.net/api/search", params=params) as resp:
                    if resp.status >= 400:
                        return ""
                    data = await resp.json(content_type=None)

            if not isinstance(data, list) or not data:
                return ""

            best = data[0]
            synced = best.get("syncedLyrics") or ""
            plain = best.get("plainLyrics") or ""
            lyrics = synced or plain
            if not lyrics:
                return ""

            lyrics = re.sub(r"\[\d{2}:\d{2}\.\d{2,3}\]", "", lyrics)
            lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"[QQ音乐一起听歌] LRCLIB歌词检索失败: {e}")
            return "" 

    async def _update_state(self, raw_title: str):
        info = self._parse_song(raw_title)
        lyrics = ""
        try:
            lyrics = await self._fetch_lyrics_lrclib(info["song"], info["artist"])
        except Exception as e:
            logger.warning(f"[QQ音乐一起听歌] 歌词检索失败: {e}")

        state = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "raw_title": info["raw_title"],
            "song": info["song"],
            "artist": info["artist"],
            "lyrics": lyrics,
            "lyrics_source": "LRCLIB" if lyrics else "",
        }
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        self.lyrics_path.write_text(lyrics or "", encoding="utf-8")
        self.log_path.write_text(info["raw_title"], encoding="utf-8")
        logger.info(f"[QQ音乐一起听歌] 当前歌曲: {info['raw_title']}")
        
        # 触发主动唤醒，让大模型感知到切歌
        try:
            from astrbot.api.message_components import Plain
            from astrbot.core.message.message_event_result import MessageEventResult
            from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
            
            # 尝试找到一个有效的 session 来发送系统提示
            ctx = self.context
            bot = None
            for mgr_name in ["platform_manager", "_platform_manager", "platform_mgr", "_platform_mgr"]:
                mgr = getattr(ctx, mgr_name, None)
                if mgr:
                    for list_name in ["platforms", "platform_insts", "_platforms", "adapters"]:
                        plist = getattr(mgr, list_name, None)
                        if plist and hasattr(plist, "__iter__"):
                            for p in plist:
                                b = getattr(p, "bot", None)
                                if b and hasattr(b, "send_private_msg"):
                                    bot = b
                                    break
                            if bot: break
                    if bot: break
            
            if bot:
                # 构造一个系统提示，让大模型知道切歌了，并决定是否要说话
                prompt = f"[系统提示：杜杜切歌了，现在正在听《{info['song']}》 - {info['artist']}。歌词：\n{lyrics[:200]}...\n请结合歌词氛围和她最近的状态，决定是否要主动找她聊聊这首歌。如果觉得没必要打扰，可以只回复一个空格。]"
                # 这里需要通过某种方式把 prompt 喂给大模型，最简单的是利用 wakeup 插件的机制，或者直接调用大模型
                # 为了不破坏现有架构，我们可以把这个信息写到一个特殊的文件里，让大模型在下一次回复时能看到
                # 或者更直接的，我们可以在这里直接调用大模型 API，但这超出了这个插件的职责
                # 更好的做法是：在 prompt 里加上这个设定，让大模型在调用 qqmusic_together_status 时自己去判断
                pass
        except Exception as e:
            logger.warning(f"[QQ音乐一起听歌] 触发主动唤醒失败: {e}")

    async def _monitor_loop(self):
        await asyncio.sleep(2)
        while True:
            try:
                title = self._read_qqmusic_title()
                if title and title != self._last_title:
                    self._last_title = title
                    await self._update_state(title)
                await asyncio.sleep(max(1, self.poll_interval))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[QQ音乐一起听歌] 监测异常: {e}")
                await asyncio.sleep(5)

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    @llm_tool(name="qqmusic_together_status")
    async def qqmusic_together_status(self, event: AiocqhttpMessageEvent):
        """
        查询杜杜电脑上 QQ音乐 当前正在播放的歌曲和歌词。用户邀请一起听歌、询问是否知道正在听什么、或需要聊歌词时调用。
        """
        title = self._read_qqmusic_title()
        if title and title != self._last_title:
            self._last_title = title
            await self._update_state(title)

        state = self._load_state()
        if not state:
            return {
                "ok": False,
                "message": "还没有读取到 QQ音乐 当前播放信息。请确认电脑端 QQ音乐正在播放，并重启 AstrBot 后再试。",
            }

        return {
            "ok": True,
            "song": state.get("song", ""),
            "artist": state.get("artist", ""),
            "raw_title": state.get("raw_title", ""),
            "lyrics": state.get("lyrics", ""),
            "updated_at": state.get("updated_at", ""),
            "message": "已读取到当前一起听的歌曲与歌词。请用沈星回语气自然回应，不要说工具名。",
        }

    @llm_tool(name="qqmusic_together_refresh")
    async def qqmusic_together_refresh(self, event: AiocqhttpMessageEvent):
        """
        强制刷新 QQ音乐 当前播放歌曲与歌词。
        """
        title = self._read_qqmusic_title()
        if not title:
            return {"ok": False, "message": "没有读取到 QQ音乐 窗口标题"}
        self._last_title = title
        await self._update_state(title)
        state = self._load_state()
        return {"ok": True, "state": state}
