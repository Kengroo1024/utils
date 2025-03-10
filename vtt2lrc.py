#!/usr/bin/env python

import re
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("-s", default="*.vtt", help="search pattern")
# args = parser.parse_args()
# for vttFile in Path(".").glob(args.s):
#    subtime = re.findall(r'\d*:\d*:\d*\.\d*(?= --\>)', vttFile.read_text())
#    subword = vttFile.read_text().split('\n')[4:-1:4]
#    with open(vttFile.with_suffix('.lrc'), 'w') as lrcFile:
#        for (timeAxis, caption) in zip(subtime, subword):
#            temp = timeAxis.split(':')
#            subbed = temp[1] + ':' + temp[2][0:-1]
#            lrcFile.write(f"[{subbed}]{caption}\n")

if __name__ == "__main__":
    args = parser.parse_args()
    vttfiles = [i for i in Path().glob(args.s)]
    for vttfile in vttfiles:
        cues = iter(vttfile.read_text().split("\n\n"))
        try:
            if not next(cues).startswith("WEBVTT"):
                raise RuntimeError("错误的WEBVTT文件语法")
        except StopIteration:
            print("空文件")
        except RuntimeError as e:
            print(e)
        cuegroup = [i.split("\n") for i in cues if i != "\n"]
        for cue in cuegroup:
            linar = iter(cue)
            firstline = next(linar)
            if re.fullmatch(r"\d*", firstline):
                try:
                    if re.fullmatch(
                        r"\d*:\d*:\d*\.\d*(?= --\> )\d*:\d*:\d*\.\d*", next(linar)
                    ):
                        pass
                except BaseException:
                    exit()
            elif re.fullmatch(r"\d*:\d*:\d*\.\d*(?= --\> )\d*:\d*:\d*\.\d*", firstline):
                pass
            for line in linar:
                pass
