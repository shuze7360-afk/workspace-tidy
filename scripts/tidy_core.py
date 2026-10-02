#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workspace-tidy 核心脚本：工作区根目录每周整理（跨 AI 编程工具通用）。

用法:
  python tidy_core.py --config tidy.config.json --dry-run   # 默认行为，只打印计划
  python tidy_core.py --config tidy.config.json --apply     # 实际执行

行为:
  1) 根目录散落文件按关键词规则移动到分类目录（跳过白名单与新近文件）
  2) 删除明确的临时垃圾（--apply 时；删除清单写入日志）
  3) 校验目录联接（junction/symlink）存活，失效时打印重建命令（不自动执行）

安全设计:
  - 默认 dry-run，不加 --apply 不落盘
  - --apply 前先把完整计划写入 logs_dir 下的清单文件
  - 白名单/最近 min_age_hours 小时内修改的文件一律不动
  - 只移动根目录散落"文件"，绝不移动/删除任何"文件夹"

仅依赖 Python 标准库；Windows / macOS / Linux 通用。
"""
import argparse
import datetime
import fnmatch
import json
import os
import shutil
import stat as stat_module
import sys
import time

DEFAULT_CONFIG_PATHS = ("tidy.config.json", "config/tidy.config.json",
                        "config/tidy.config.example.json")


def find_config(explicit):
    if explicit:
        if not os.path.isfile(explicit):
            sys.exit("配置文件不存在: %s" % explicit)
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(os.getcwd(), p) for p in DEFAULT_CONFIG_PATHS]
    candidates += [os.path.join(os.path.dirname(here), p) for p in DEFAULT_CONFIG_PATHS]
    for c in candidates:
        if os.path.isfile(c):
            return c
    sys.exit("未找到配置文件，请用 --config 指定")


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_stat(full):
    """带 \\\\?\\ 前缀的 stat，能正确处理 nul 等 Windows 保留名与超长路径。"""
    if os.name == "nt" and not full.startswith("\\\\?\\"):
        full = "\\\\?\\" + os.path.abspath(full)
    try:
        return os.stat(full)
    except OSError:
        return None


def iter_root_files(root):
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        st = safe_stat(full)
        if st is not None and stat_module.S_ISDIR(st.st_mode):
            continue  # 目录一律不碰，只处理散落文件
        yield name, full


def hours_since(full):
    st = safe_stat(full)
    if st is None:
        # 无法 stat（如 Windows 保留名文件），视为足够久远，交由垃圾规则裁决
        return float("inf")
    return (time.time() - st.st_mtime) / 3600.0


def classify(name, categories):
    low = name.lower()
    for cat in categories:
        for kw in cat.get("keywords", []):
            if str(kw).lower() in low:
                return cat["dir"]
    return None


def is_junk(name, patterns):
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns)


def force_remove(path):
    """兼容 Windows 保留名 nul：加 \\\\?\\ 前缀删除。
    注意不要用 os.path.abspath——新版 Python 会把 nul 解析成 \\\\.\\nul 设备路径。"""
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        path = "\\\\?\\" + os.path.normpath(path)
    os.remove(path)


def unique_dest(dest):
    if not os.path.exists(dest):
        return dest
    stem, ext = os.path.splitext(dest)
    return "%s_%s%s" % (stem, time.strftime("%Y%m%d%H%M%S"), ext)


def check_junctions(root, junctions):
    lines = []
    problems = 0
    for j in junctions:
        link = os.path.join(root, j["link"])
        target = os.path.join(root, j["target"])
        real = os.path.realpath(link) if os.path.exists(link) else None
        ok = real is not None and os.path.normcase(os.path.abspath(real)) == os.path.normcase(os.path.abspath(target))
        if ok:
            lines.append("[联接][正常] %s -> %s" % (j["link"], j["target"]))
        else:
            problems += 1
            lines.append("[联接][失效] %s -> %s" % (j["link"], j["target"]))
            if os.name == "nt":
                lines.append("  重建命令(请人工确认后执行): powershell -Command \"New-Item -ItemType Junction "
                             "-Path '%s' -Target '%s'\"" % (link, target))
            else:
                lines.append("  重建命令(请人工确认后执行): ln -s '%s' '%s'" % (os.path.abspath(target), link))
    return lines, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="配置文件路径（缺省自动查找）")
    ap.add_argument("--root", default=os.getcwd(), help="工作区根目录（默认当前目录）")
    ap.add_argument("--apply", action="store_true", help="实际执行（缺省只打印计划）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不落盘（默认行为，显式写出便于脚本化）")
    args = ap.parse_args()

    cfg_path = find_config(args.config)
    cfg = load_config(cfg_path)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        sys.exit("工作区目录不存在: %s" % root)

    protected = set(cfg.get("protected", []))
    min_age = float(cfg.get("min_age_hours", 72))
    categories = cfg.get("categories", [])
    junk_patterns = cfg.get("junk_patterns", [])
    archive_dir = cfg.get("archive_dir", "attic_deprecated")
    logs_dir = os.path.join(root, cfg.get("logs_dir", "logs"))

    moves, junk, skipped = [], [], []
    for name, full in iter_root_files(root):
        if name in protected or name == os.path.basename(cfg_path):
            continue
        if hours_since(full) < min_age:
            skipped.append("[跳过][新近文件] %s（仅 %.0f 小时前修改）" % (name, hours_since(full)))
            continue
        if is_junk(name, junk_patterns):
            junk.append(full)
            continue
        dest_rel = classify(name, categories)
        if dest_rel:
            dest_dir = os.path.join(root, dest_rel)
            os.makedirs(dest_dir, exist_ok=True) if args.apply else None
            moves.append((full, unique_dest(os.path.join(dest_dir, name))))
        else:
            skipped.append("[跳过][无匹配规则] %s" % name)

    lines = []
    tag = "[apply]" if args.apply else "[dry-run]"
    lines.append("%s 配置: %s" % (tag, cfg_path))
    lines.append("%s 工作区: %s" % (tag, root))

    for src, dest in moves:
        lines.append("[移动] %s -> %s" % (os.path.basename(src), os.path.relpath(dest, root)))
        if args.apply:
            shutil.move(src, dest)
    for j in junk:
        lines.append("[删垃圾] %s" % os.path.basename(j))
        if args.apply:
            force_remove(j)

    jlines, problems = check_junctions(root, cfg.get("junctions", []))
    lines.extend(jlines)
    lines.extend(skipped)

    moved = len(moves)
    lines.append("%s 汇总: 移动 %d，删垃圾 %d，联接失效 %d，跳过 %d"
                 % (tag, moved, len(junk), problems, len(skipped)))
    if not args.apply:
        lines.append("以上为 dry-run 计划；确认后加 --apply 执行。")

    report = "\n".join(lines)
    print(report)
    if args.apply:
        os.makedirs(logs_dir, exist_ok=True)
        manifest = os.path.join(logs_dir, "tidy_%s.log" % time.strftime("%Y%m%d_%H%M%S"))
        with open(manifest, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print("操作清单已写入: %s" % manifest)


if __name__ == "__main__":
    main()
