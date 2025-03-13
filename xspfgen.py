#!/usr/bin/env python

import argparse
import asyncio
import json
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

# 命名空间常量
NS = "http://xspf.org/ns/0/"
NS_PLAYLIST = f"{{{NS}}}playlist"
NS_TRACKLIST = f"{{{NS}}}trackList"
NS_TRACK = f"{{{NS}}}track"
NS_LOCATION = f"{{{NS}}}location"
NS_TITLE = f"{{{NS}}}title"
NS_CREATOR = f"{{{NS}}}creator"
NS_ALBUM = f"{{{NS}}}album"
NS_TRACKNUM = f"{{{NS}}}trackNum"
NS_DURATION = f"{{{NS}}}duration"

# 初始化参数解析
parser = argparse.ArgumentParser(
    description="Generate XSPF playlist files with async support."
)
parser.add_argument("-f", "--file", type=Path, help="Output file path")
parser.add_argument(
    "-p", "--prefix", default="", help="Path prefix for media locations"
)
parser.add_argument(
    "path",
    nargs="?",
    default=Path("."),
    type=Path,
    help="Directory to scan (default: current directory)",
)
parser.add_argument(
    "-i", "--indent", action="store_true", help="Apply indentation to XML output"
)
parser.add_argument(
    "-m", "--metadata", action="store_true", help="Include media metadata in playlist"
)
parser.add_argument("-v", "--video", action="store_true",
                    help="Include video files")
parser.add_argument("-a", "--audio", action="store_true",
                    help="Include audio files")
parser.add_argument("-n", "--name", help="Playlist title")
parser.add_argument(
    "-j",
    "--concurrency",
    type=int,
    default=8,
    help="Maximum concurrent tasks (default: 8)",
)

# 支持的媒体格式（不区分大小写）
AUDIO_FORMATS = {".mp3", ".flac", ".ogg", ".m4a", ".ape", ".acc", ".wav"}
VIDEO_FORMATS = {".mp4", ".avi", ".mkv", ".ts", ".mov"}

HIDE_CURSOR_CHARACTER = "\033[?25l"
PRINT_CURSOR_CHARACTER = "\033[?25h"
CLEAR_LINE_CHARACTER = "\033[K"


def format_time(seconds: int) -> str:
    """格式化时间显示为 mm min ss s"""
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:>2}min {seconds:02d}s"


class AsyncProgressBar:
    """异步终端进度条"""

    def __init__(self, total: int) -> None:
        self.total = total
        self.completed = 0
        self.start_time = time.time()
        self.progress_width = len(str(total))
        self.lock = asyncio.Lock()
        self._hidden_cursor = False

    async def update(self) -> None:
        """原子更新进度"""
        async with self.lock:
            self.completed += 1
            if not self._hidden_cursor:
                sys.stdout.write(HIDE_CURSOR_CHARACTER)
                self._hidden_cursor = True
            elapsed = int(time.time() - self.start_time)
            progress = self.completed / self.total
            filled = int(20 * progress)
            bar = "#" * filled + "-" * (20 - filled)
            remaining = int(elapsed / progress -
                            elapsed) if progress > 0 else 0
            sys.stdout.write(
                f"\r  {self.completed:>{self.progress_width}}/{self.total} "
                + f"[{bar}] {format_time(elapsed)} < {format_time(remaining)}"
                + CLEAR_LINE_CHARACTER
            )
            sys.stdout.flush()

    async def cleanup(self) -> None:
        """恢复终端状态"""
        async with self.lock:
            if self._hidden_cursor:
                sys.stdout.write(PRINT_CURSOR_CHARACTER)
                self._hidden_cursor = False


async def async_get_metadata(
    file_path: Path, sem: asyncio.Semaphore
) -> Dict[str, Optional[str]]:
    """异步获取媒体元数据"""
    async with sem:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-hide_banner",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_entries",
            "format_tags=title,artist,album,track",
            "-show_entries",
            "format=duration",
            "-i",
            str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {}

        if proc.returncode != 0:
            return {}

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return {}

        format_info = data.get("format", {})
        tags = format_info.get("tags", {})
        return {
            "title": tags.get("title"),
            "artist": tags.get("artist"),
            "album": tags.get("album"),
            "track": tags.get("track"),
            "duration": format_info.get("duration", "0"),
        }


async def generate_playlist(
    root_path: Path,
    suffixes: Tuple[str, ...],
    output_file: Optional[Path],
    indent: bool,
    use_metadata: bool,
    playlist_name: Optional[str],
    path_prefix: str,
    concurrency: int,
) -> None:
    """异步生成播放列表"""
    ET.register_namespace("", NS)
    # 创建XML根元素
    attrib = {"version": "1"}
    if playlist_name:
        attrib["title"] = playlist_name
    root = ET.Element(NS_PLAYLIST, attrib)
    track_list = ET.SubElement(root, NS_TRACKLIST)

    # 收集媒体文件
    media_files: List[Path] = [
        (dir_path / filename)
        for dir_path, _, filenames in root_path.walk()
        for filename in filenames
        if Path(filename).suffix.lower() in suffixes
    ]

    # 初始化进度条和信号量
    progress = AsyncProgressBar(
        len(media_files)) if sys.stdout.isatty() else None
    sem = asyncio.Semaphore(concurrency)

    # 异步获取元数据
    metadata_tasks = []
    for file_path in media_files:
        if use_metadata:
            task = asyncio.create_task(async_get_metadata(file_path, sem))
            metadata_tasks.append(task)
        else:
            metadata_tasks.append(asyncio.sleep(0))  # 占位任务

    # 处理结果并构建XML
    for file_path, metadata_task in zip(media_files, metadata_tasks):
        metadata = await metadata_task if use_metadata else {}
        # 构建track元素
        track = ET.SubElement(track_list, NS_TRACK)
        location = quote(f"{path_prefix}{file_path.as_posix()}")
        ET.SubElement(track, NS_LOCATION).text = location

        if metadata:
            if metadata.get("title"):
                ET.SubElement(track, NS_TITLE).text = metadata["title"]
            if metadata.get("artist"):
                ET.SubElement(track, NS_CREATOR).text = metadata["artist"]
            if metadata.get("album"):
                ET.SubElement(track, NS_ALBUM).text = metadata["album"]
            if metadata.get("track"):
                ET.SubElement(track, NS_TRACKNUM).text = metadata["track"]
            try:
                duration_ms = int(float(metadata["duration"]) * 1000)
                ET.SubElement(track, NS_DURATION).text = str(duration_ms)
            except (ValueError, KeyError):
                pass

        # 更新进度条
        if progress:
            await progress.update()

    # 格式化输出
    if indent:
        ET.indent(root)

    # 写入文件或标准输出
    if output_file:
        ET.ElementTree(root).write(
            output_file, encoding="utf-8", xml_declaration=True)
        if progress:
            elapsed = int(time.time() - progress.start_time)
            sys.stdout.write(f"\nTotal time: {format_time(elapsed)}\n")
    else:
        ET.dump(root)

    # 清理终端状态
    if progress:
        await progress.cleanup()


async def main() -> None:
    args = parser.parse_args()
    # 确定文件类型
    selected_formats = set()
    if args.audio:
        selected_formats.update(AUDIO_FORMATS)
    if args.video:
        selected_formats.update(VIDEO_FORMATS)

    # 输出检查
    if not args.file and sys.stdout.isatty():
        print(
            "Error: Output file required for terminal output. Use -f option or redirect."
        )
        sys.exit(1)

    try:
        await generate_playlist(
            root_path=args.path,
            suffixes=tuple(selected_formats),
            output_file=args.file,
            indent=args.indent,
            use_metadata=args.metadata,
            playlist_name=args.name,
            path_prefix=args.prefix,
            concurrency=args.concurrency,
        )
    except asyncio.CancelledError:
        if sys.stdout.isatty():
            sys.stdout.write(PRINT_CURSOR_CHARACTER)  # 确保恢复光标


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.stdout.write(PRINT_CURSOR_CHARACTER)
        sys.stdout.flush()
