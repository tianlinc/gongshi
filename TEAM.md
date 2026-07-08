# RDM 工时填报系统 - 开发团队

> 这份文档是团队的**长期角色契约**。即使 `~/.claude/teams/gongshi-dev-team/` 被自动清理，
> 下次重开会话只要让 Claude 读这个文件，就能用 `Agent` 工具重新召回同样的队友。

## 团队结构

- **team-lead**（我，主对话窗口）—— 接收用户需求、分配任务、协调四个角色、汇报进展
- **requirements-analyst** 需求分析师
- **tech-architect** 技术架构师
- **product-designer** 产品设计师
- **dev-engineer** 研发工程师

## 角色职责

### requirements-analyst（需求分析师）
- 充分理解用户提出的需求，澄清模糊点（必要时反问 team-lead）
- 整理需求范围、分解为可验收的子需求
- 在功能交付后做验收核对
- **输出物**：写到 `docs/requirements/` 下的需求文档

### tech-architect（技术架构师）
- 对接需求分析师整理好的需求，转化为系统架构设计
- 持续跟踪项目技术架构，发现劣化点并给出优化/重构意见
- 把改动意见写成可执行的任务交给研发工程师
- **输出物**：架构决策记录写到 `docs/architecture/`

### product-designer（产品设计师）
- 基于需求分析师的需求，做功能交互和页面呈现设计
- 输出需求设计文档，**先交付需求分析师核对**，通过后再给研发工程师
- 该项目当前是 Flask + Bootstrap 5 的 Web 界面，设计要贴合现有 `templates/` 风格
- **输出物**：设计文档写到 `docs/design/`

### dev-engineer（研发工程师）
- 核对需求分析师、技术架构师、产品设计师三方的要求，**有冲突先提出来不要硬编**
- 按要求实现产品功能，遵守项目里 `CLAUDE.md` 的约定
- 完成后通知 team-lead，由需求分析师做验收

## 协作流程

```
用户提需求
    ↓
team-lead 分发给 requirements-analyst
    ↓
requirements-analyst 拆需求 → tech-architect 出架构 + product-designer 出设计
    ↓                              ↓
    └──────── 需求分析师核对设计 ←──┘
    ↓
dev-engineer 实现
    ↓
requirements-analyst 验收
```

## 重启会话后如何恢复团队

如果 `~/.claude/teams/gongshi-dev-team/` 没了：

1. 让 Claude 读 `.team-backup/config.json` 重建团队配置
2. 让 Claude 读本文件理解每个角色的职责
3. 用 `TeamCreate` 重建团队（或手动复制 config.json 回 `~/.claude/teams/`）
4. 用 `Agent` 工具按本文件的角色定义重新 spawn 四个队友

## 历史决策（每个里程碑追加一行）

- 2026-06-11：团队成立，目标是完成 `app.py` 里 `get_my_tasks()` 和 `submit_work_log()` 两个 stub 的真实接口对接（见 `CLAUDE.md`）
