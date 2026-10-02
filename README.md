# workspace-tidy · AI 编程工作区自动整理技能

把"项目工作区每周整理"沉淀成一个 **AI Agent 技能**：散落文件自动归位、临时垃圾清理、
目录联接校验，以及在 [ZCode](https://zcode.ai) 中把侧边栏未分组任务自动归组——让工作区
和任务列表始终保持"一眼能找到"的状态。

**跨工具兼容**：不依赖任何专有 API。ZCode、Codex、Claude Code 等**任何能读文件、
执行命令的 AI 编程工具**都可以执行本技能；在非 ZCode 环境里，任务分组模块会自动跳过，
文件整理功能完全一致。

## 它解决什么问题

AI 编程工具用久了，工作区常见两类混乱：

- **文件层面**：根目录堆满临时脚本、截图、备份，找不到哪个文件属于哪个项目；
- **会话层面**（ZCode）：侧边栏几十个历史会话平铺，新会话不知道该归到哪个项目。

本技能用一份 `tidy.config.json` 描述你的分类体系（目录 + 关键词 + 白名单 + 联接 + 分组），
Agent 每周按配置巡检一次，配合自动化调度即可完全无人值守。

## 快速开始

### 方式一：作为 ZCode / Claude Code 技能安装

```bash
# ZCode
git clone https://github.com/<你的用户名>/workspace-tidy.git
mkdir -p ~/.zcode/skills && cp -r workspace-tidy ~/.zcode/skills/workspace-tidy

# Claude Code 同理
mkdir -p ~/.claude/skills && cp -r workspace-tidy ~/.claude/skills/workspace-tidy
```

然后对 Agent 说："按 workspace-tidy 技能整理当前工作区"。

### 方式二：Codex / 其他 Agent 直接使用

把本仓库放入工作区，对 Agent 说：

> 读 workspace-tidy/SKILL.md，按它的流程和铁律整理当前工作区。

（仓库内的 [AGENTS.md](AGENTS.md) 是等价入口，Codex 会自动读取。）

### 配置你的分类体系

```bash
cp config/tidy.config.example.json tidy.config.json   # 放到你的工作区根目录
```

编辑 `tidy.config.json`：

| 字段 | 说明 |
| --- | --- |
| `categories` | 分类目录 + 关键词（大小写不敏感，匹配文件名/会话文本），命中即归位 |
| `junk_patterns` | 垃圾文件通配模式（默认含 `nul`、`*$*.png`、`*.tmp` 等） |
| `protected` | 白名单文件，永不移动 |
| `min_age_hours` | 最近 N 小时内修改的文件不动（默认 72，保护进行中的工作） |
| `archive_dir` | 无规则匹配/拿不准的文件的归档目录 |
| `junctions` | 需要保持存活的目录联接（junction/symlink），失效时打印重建命令 |
| `zcode.groups` | ZCode 侧边栏分组：id / 中文标题 / 颜色 / 关键词，`overrides` 按任务 id 前缀强制归组 |

## 脚本用法

```bash
python scripts/tidy_core.py --config tidy.config.json --dry-run   # 默认，只打印计划
python scripts/tidy_core.py --config tidy.config.json --apply     # 实际执行（写操作清单到 logs/）
python scripts/zcode_task_groups.py --config tidy.config.json --dry-run   # ZCode 任务归组
python scripts/zcode_task_groups.py --config tidy.config.json --apply
```

两个脚本只用 Python 3 标准库，Windows / macOS / Linux 通用。

## 配合定时自动化（以 ZCode 为例）

创建一条每周定时自动化（如"每周五 21:00"），提示词模板：

> 对当前工作区执行每周整理巡检：按 workspace-tidy 技能执行。先读工作区导航文档与
> tidy.config.json；运行 tidy_core.py --dry-run 审阅后 --apply；再运行
> zcode_task_groups.py（先 --dry-run 后 --apply）；处理失效联接时只复核脚本给出的
> 重建命令；同步更新 README.md 目录树；最后报告移动/删除/归组清单与跳过原因，
> 无变更则明确说"本次巡检无需整理"。铁律见 SKILL.md：绝不移动项目文件夹，
> 72 小时内的新文件只给建议，拿不准的文件只归档不删除。

## 安全设计

- **默认 dry-run**：不加 `--apply` 不落盘；
- **写前备份**：分组脚本写库前自动备份数据库；文件移动前写操作清单；
- **绝不移动项目文件夹**：只整理根目录散落文件，避免断开工具配置里的绝对路径引用；
- **新近文件保护**：72 小时内修改的文件只给归类建议；
- **删除克制**：仅限垃圾模式明确匹配，`nul` 等 Windows 保留名有专用删除路径；
- **环境解耦**：非 ZCode 环境自动跳过分组模块，其余功能照常。

## 隐私说明

本仓库为通用技能模板：**不包含任何个人数据**——示例配置全部使用中性分类
（科研学术/项目开发/内容创作/学习提升/系统运维），示例路径均为占位符。
你自己的 `tidy.config.json` 与运行日志只会存在于本机，请勿提交到公共仓库
（`.gitignore` 已默认忽略 `tidy.config.json`）。

## License

[MIT](LICENSE)
