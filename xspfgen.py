#! /usr/bin/env python

import argparse
import json
import subprocess
from pathlib import Path
import time
from math import log10
import xml.etree.ElementTree as ET
from urllib.parse import quote

parser = argparse.ArgumentParser()

parser.add_argument("-f", nargs="?", type=Path)
parser.add_argument("-p", nargs="?", default="")
parser.add_argument("path", nargs="?", default=Path("."),type=Path)

audio_format = (".mp3", ".flac", ".ogg", ".m4a", ".ape", ".acc", ".wav")


def format_time(seconds: int) -> str:
    minute, second = divmod(seconds, 60)
    return f"{minute:>2}min {second:02d}s"


def main():
    par = parser.parse_args()
    i = 0
    toal = 0

    # 命名空间处理
    NS = "http://xspf.org/ns/0/"
    ET.register_namespace("", NS)

    # 创建根元素
    root = ET.Element(f"{{{NS}}}playlist", version="1")
    track_list = ET.SubElement(root, f"{{{NS}}}trackList")

    for supdir, subdir, files in par.path.walk():
        for file in files:
            if file.endswith(audio_format):
                toal += 1

    lm = int(log10(toal) + 1)
    print("\033[?25l")

    start = int(time.time())

    for supdir, subdir, files in par.path.walk():
        for file in files:
            if file.endswith(audio_format):
                m = supdir / file
                p = subprocess.run(
                    [
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
                        m,
                    ],
                    stdout=subprocess.PIPE,
                    encoding="utf-8",
                )
                format_dict = json.loads(p.stdout)["format"]
                track = ET.SubElement(track_list, f"{{{NS}}}track")
                ET.SubElement(track, f"{{{NS}}}location").text = par.p + quote(m.as_posix())
                ET.SubElement(track, f"{{{NS}}}title").text = format_dict["tags"][
                    "title"
                ]
                ET.SubElement(track, f"{{{NS}}}creator").text = format_dict["tags"][
                    "artist"
                ]
                ET.SubElement(track, f"{{{NS}}}album").text = format_dict["tags"][
                    "album"
                ]
                try:
                    ET.SubElement(track, f"{{{NS}}}trackNum").text = format_dict[
                        "tags"
                    ]["track"]
                except KeyError:
                    pass
                ET.SubElement(track, f"{{{NS}}}duration").text = str(
                    int(float(format_dict["duration"]) * 1000)
                )

                # 进度条更新
                i += 1
                shiwei, gewei = divmod((i * 100) // toal, 10)
                now = int(time.time())
                print(
                    f"  {i:>{lm}}/{toal} |",
                    "#" * shiwei,
                    gewei,
                    " " * (9 - shiwei),
                    "| ",
                    format_time(now - start),
                    " | ",
                    format_time(int((now - start) * (toal / i - 1))),
                    sep="",
                    end="\033[K\r",
                )
    ET.indent(root)
    if par.f is not None:
        # 保存文件
        tree = ET.ElementTree(root)
        tree.write(par.f, encoding="UTF-8", xml_declaration=True)
    else:
        ET.dump(root)
    print(format_time(now - start), "\033[K")
    return


if __name__ == "__main__":
    try:
        main()
    finally:
        print("\033[?25h")
