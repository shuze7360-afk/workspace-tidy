#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workspace-tidy 的 ZCode 任务分组模块（可选）。

扫描 ZCode 的任务索引库（~/.zcode/v2/tasks-index.sqlite），把侧边栏未分组的会话
按配置里的关键词规则归入分组。非 ZCode 环境（找不到数据库）会优雅退出，不影响
tidy_core.py 的文件整理在 Codex / Claude Code 等其他工具中使用。

用法:
  python zcode_task_groups.py --config tidy.config.json --dry-run   # 默认
  python zcode_task_groups.py --config tidy.config.json --apply     # 写入（自动备份）

分组颜色合法值: gray / red / orange / yellow / green / blue / purple
安全设计: 写入前自动备份数据库；只新增 task_group_members 成员关系，不改其他表；
不改动已归组、已归档、已删除的任务；关键词命中即停（配置数组顺序即优先级）。
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import time

VALID_COLORS = {"gray", "red", "orange", "yellow", "green", "blue", "purple"}


def detect_dbs(cfg):
    home = os.path.expanduser("~")
    tasks_db = cfg.get("tasks_db") or os.path.join(home, ".zcode", "v2", "tasks-index.sqlite")
    cli_db = cfg.get("cli_db") or os.path.join(home, ".zcode", "cli", "db", "db.sqlite")
    return tasks_db, cli_db


def first_user_text(cli_db, task_id):
    """读会话首条用户消息文本，用于关键词匹配；读不到返回空串。"""
    if not os.path.isfile(cli_db):
        return ""
    try:
        con = sqlite3.connect("file:%s?mode=ro" % cli_db.replace("\\", "/"), uri=True)
        cur = con.cursor()
        rows = cur.execute(
            "SELECT p.data FROM part p JOIN message m ON m.id=p.message_id AND m.session_id=p.session_id "
            "WHERE p.session_id=? AND m.data LIKE '%\"role\":\"user\"%' ORDER BY p.rowid LIMIT 8",
            (task_id,)).fetchall()
        con.close()
    except sqlite3.Error:
        return ""
    for (data,) in rows:
        try:
            d = json.loads(data)
        except (ValueError, TypeError):
            continue
        if isinstance(d, dict) and d.get("type") == "text" and d.get("text"):
            return d["text"]
    return ""


def classify(task_id, title, body, groups, overrides, default_group):
    for prefix, gid in overrides.items():
        if task_id.startswith(prefix):
            return gid, "override"
    hay = ("%s\n%s" % (title, body)).lower()
    for g in groups:
        for kw in g.get("keywords", []):
            if str(kw).lower() in hay:
                return g["id"], kw
    return default_group, "default"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None, help="配置文件路径（缺省自动查找，同 tidy_core.py）")
    ap.add_argument("--apply", action="store_true", help="实际写入（缺省只打印计划）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划（默认行为，显式写出便于脚本化）")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tidy_core import find_config, load_config

    cfg = load_config(find_config(args.config)).get("zcode")
    if not cfg:
        print("配置中没有 zcode 段，跳过任务分组。")
        return
    tasks_db, cli_db = detect_dbs(cfg)
    if not os.path.isfile(tasks_db):
        print("未检测到 ZCode（%s 不存在），跳过任务分组——文件整理不受影响。" % tasks_db)
        return

    groups = cfg.get("groups", [])
    for g in groups:
        if g.get("color") and g["color"] not in VALID_COLORS:
            sys.exit("分组 %s 颜色非法: %s（合法值 %s）" % (g["id"], g["color"], sorted(VALID_COLORS)))
    overrides = cfg.get("overrides", {})
    default_group = cfg.get("default_group") or (groups[0]["id"] if groups else "")
    title_of = {g["id"]: g.get("title", g["id"]) for g in groups}

    con = sqlite3.connect(tasks_db, timeout=15)
    cur = con.cursor()
    ungrouped = cur.execute(
        "SELECT task_id, title, workspace_key, workspace_path, COALESCE(cron_automation_id,'') "
        "FROM tasks WHERE deleted=0 AND archived=0 AND NOT EXISTS ("
        "SELECT 1 FROM task_group_members m WHERE m.workspace_key=tasks.workspace_key "
        "AND m.task_id=tasks.task_id)").fetchall()
    if not ungrouped:
        print("无未分组任务，本次无需整理。")
        con.close()
        return

    now = int(time.time() * 1000)
    plan = []
    for task_id, title, wk, wp, cron_id in ungrouped:
        gid, how = classify(task_id, title or "", first_user_text(cli_db, task_id),
                            groups, overrides, default_group)
        plan.append((gid, task_id, title or "(无标题)", wk, wp))

    tag = "[apply]" if args.apply else "[dry-run]"
    print("%s 共 %d 条待归组:" % (tag, len(plan)))
    for gid, task_id, title, wk, wp in plan:
        print("  %s <- %s" % (title_of.get(gid, gid), title[:60]))

    if not args.apply:
        print("以上为 dry-run 计划；确认后加 --apply 执行。")
        con.close()
        return

    backup = tasks_db + ".bak-tidy-" + time.strftime("%Y%m%d")
    shutil.copy2(tasks_db, backup)
    try:
        cur.execute("BEGIN IMMEDIATE")
        for gid, task_id, title, wk, wp in plan:
            cur.execute("DELETE FROM task_group_members WHERE workspace_key=? AND task_id=?", (wk, task_id))
            cur.execute("INSERT INTO task_group_members (group_id, workspace_key, workspace_path, "
                        "workspace_identity, task_id, sort_order, added_at, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)", (gid, wk, wp, None, task_id, 99000, now, now, now))
        con.commit()
        print("已写入 %d 条（备份: %s）" % (len(plan), backup))
    except Exception as e:
        con.rollback()
        print("写入失败已回滚: %s" % e)
        sys.exit(1)
    finally:
        con.close()


if __name__ == "__main__":
    main()
