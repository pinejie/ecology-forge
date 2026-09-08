# -*- coding: utf-8 -*-
"""
SDK 工具搜索脚本

用法：
    python3 search_sdk.py 关键词
    python3 search_sdk.py 关键词1 关键词2    # 多关键词，取并集
    python3 search_sdk.py                    # 无参数，列出全部

搜索范围：@expose 标记的 description 和 method name。
"""

import os
import re
import sys

SDK_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_expose_files():
    """扫描 SDK 目录，解析所有 @expose 标记，返回 [(文件名, 方法名, 描述, 行号)]"""
    results = []
    for fname in sorted(os.listdir(SDK_DIR)):
        if not fname.endswith(".py") or fname in ("mcp_register.py", "mcp_server.py", "search_sdk.py"):
            continue
        filepath = os.path.join(SDK_DIR, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # @expose 在 def 上面，所以先记 @expose 行号，再往下找 def
        pending_expose = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            if "@expose(" in stripped or stripped == "@expose(":
                pending_expose.append(i)
                # 单行形式 @expose(description="...")
                desc_match = re.search(r'description="([^"]+)"', stripped)
                if desc_match:
                    # 找紧接着的 def
                    for j in range(i, min(i + 30, len(lines))):
                        next_line = lines[j].strip()
                        if next_line.startswith("def ") and not next_line.startswith("def _"):
                            method = next_line.split("(")[0].replace("def ", "")
                            break
                        if next_line.startswith("async def ") and not next_line.startswith("async def _"):
                            method = next_line.split("(")[0].replace("async def ", "")
                            break
                    else:
                        method = ""
                    results.append((fname, method, desc_match.group(1), i))
                    pending_expose.pop()
                continue

            # 多行 @expose，继续找 description
            if pending_expose:
                desc_match = re.search(r'description="([^"]+)"', stripped)
                if desc_match:
                    expose_line = pending_expose.pop()
                    for j in range(i, min(i + 30, len(lines))):
                        next_line = lines[j].strip()
                        if next_line.startswith("def ") and not next_line.startswith("def _"):
                            method = next_line.split("(")[0].replace("def ", "")
                            break
                        if next_line.startswith("async def ") and not next_line.startswith("async def _"):
                            method = next_line.split("(")[0].replace("async def ", "")
                            break
                    else:
                        method = ""
                    results.append((fname, method, desc_match.group(1), expose_line))

    return results


def search(keywords):
    """按关键词搜索，返回匹配结果"""
    all_tools = parse_expose_files()
    if not keywords:
        return all_tools

    matched = []
    for fname, method, desc, line in all_tools:
        for kw in keywords:
            if kw in desc or kw in method:
                matched.append((fname, method, desc, line))
                break

    return matched


def main():
    keywords = sys.argv[1:]
    results = search(keywords)

    if not keywords:
        print("=== SDK 全部工具（%d 个）===\n" % len(results))
    else:
        print("=== 搜索关键词：%s（%d 个结果）===\n" % (" / ".join(keywords), len(results)))

    for fname, method, desc, line in results:
        short_file = fname.replace(".py", "")
        print("[%s] %s (第 %d 行)" % (short_file, method, line))
        print("  描述: %s" % desc)
        print()

    if not results:
        print("未找到匹配的工具。")


if __name__ == "__main__":
    main()
