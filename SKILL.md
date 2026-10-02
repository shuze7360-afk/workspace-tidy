---
name: workspace-tidy
description: AI编程工作区的每周自动整理。扫描根目录散落文件并按配置归位到分类目录、清理临时垃圾、校验目录联接，在 ZCode 中还会把侧边栏未分组任务按关键词归入分组。配置驱动、默认 dry-run、写前备份，适用于 ZCode / Codex / Claude Code 等任何能读文件、跑脚本的 AI 编程工具。
---

# workspace-tidy · AI 编程工作区自动整理

把"工作区每周整理"沉淀为可复用技能：散落文件归位、垃圾清理、联接校验、（ZCode 专属）任务自动分组。本技能**配置驱动且与具体工具解耦**——ZCode、Codex、Claude Code 等任何具备"读文件 + 执行命令"能力的 Agent 都能执行。

## 输入

1. `--config <路径>`：整理配置（JSON）。缺省时依次查找工作区根目录 `tidy.config.json`、技能目录 `config/tidy.config.json`，都没有则使用 `config/tidy.config.example.json` 的内置默认值。
2. `--root <路径>`：工作区根目录，默认当前目录。

## 执行流程

1. 读配置文件，向用户确认本次整理范围（分类目录、垃圾模式、联接清单）。
2. 运行 `python <技能目录>/scripts/tidy_core.py --config <配置> --root <工作区> --dry-run`，审阅计划。
3. 计划无异议后加 `--apply` 实际执行（脚本会先在 `logs/` 写操作清单）。
4. 按脚本输出处理失效联接：它只会打印重建命令（PowerShell `New-Item -ItemType Junction` / `ln -s`），由你复核后执行或让用户手动执行。
5. **（仅 ZCode 环境，其他工具会自动跳过）** 运行 `python <技能目录>/scripts/zcode_task_groups.py --config <配置> --dry-run`，审阅归组计划后加 `--apply`。脚本自动探测 `~/.zcode/v2/tasks-index.sqlite`，找不到就提示"非 ZCode 环境，已跳过"。
6. 若移动了文件或目录结构变化，同步更新工作区的导航文档（如 README.md / AGENTS.md 的目录树）。
7. 输出报告：移动/删除/重建/归组清单、跳过项及原因；一切正常时明确写"本次巡检无需整理"。

## 安全铁律（违反即事故）

- **只整理根目录散落文件，绝不移动、重命名或删除任何项目文件夹**——项目文件夹可能被工具配置（MCP/扩展）或绝对路径引用，移动即断链。
- 白名单文件（配置里 `protected`）与最近 `min_age_hours`（默认 72）小时内修改过的文件一律不动，只给归类建议。
- 删除仅限配置 `junk_patterns` 明确匹配的临时产物；拿不准的文件移入归档目录并在报告说明，绝不直接删。
- 写数据库前必须先备份（分组脚本已内置）；对数据库只操作成员关系表，不碰其他表。
- 不运行归档目录里的历史脚本；不改动 Agent 工具自身的配置目录（如 `~/.zcode`、`~/.codex`），唯一例外是分组脚本对自身数据库与日志的读写。

## 跨工具说明

- **ZCode / Claude Code**：把本目录复制到 `~/.zcode/skills/workspace-tidy/`（或 `~/.claude/skills/`）即作为技能被自动发现。
- **Codex 及其他 Agent**：无技能加载器的工具，直接把本仓库发给 Agent 并要求"读 SKILL.md 按流程执行"即可；本仓库的 AGENTS.md 是等价入口。
- 两个脚本只用 Python 标准库、路径全部基于用户主目录或参数解析，Windows / macOS / Linux 通用；非 ZCode 环境下分组模块优雅退出，其余功能完全一致。
