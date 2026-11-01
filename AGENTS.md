# AGENTS.md

本文件是给接手本仓库的 Coding Agent（Codex / Claude Code / Cursor 等）的操作指南。
**Codex 会自动读取本文件**；完整背景见 [`docs/HANDOFF.md`](docs/HANDOFF.md)。

---

## 一句话

工作日 **10:00（北京时间）** 自动从钉钉拉考勤数据，统计 4 类异常人员，推送到钉钉群「好达群」，并把每日汇总发布成 GitHub Pages 看板。

## 先读什么

| 顺序 | 文件 | 用途 |
|------|------|------|
| 1 | `docs/HANDOFF.md` | 架构、业务口径、钉钉 API 坑位、运维、8 次历史故障 |
| 2 | `dingtalk_attendance_bot.py` | 主脚本，核心逻辑全在这（626 行） |
| 3 | `.github/workflows/schedule.yml` | 唯一定时入口，含「等到 10:00 再发」步骤 |
| 4 | `tests/test_attendance.py` | 离线回归测试 |

## 入口与运行

```bash
pip install -r requirements.txt            # 只有 requests

python -m unittest tests.test_attendance -v   # ★ 首选验证方式：禁网、禁发群
python dingtalk_attendance_bot.py             # ⚠️ 会真的发群，别随便跑
python dingtalk_attendance_bot.py --web-only  # 只生成看板快照，不发群
```

> 生产环境由 cron-job.org → GitHub Actions 触发，不需要你手动跑。

## 硬性规则（违反会直接导致线上事故）

1. **请假判定只能用 `getleavestatus`**。🚫 绝对不要用 `getleaveapproveduration` —— 它返回的是**排班工时**（全员 505 分钟），不是请假时长。这是历史上最坑的 bug，会让"全员都在请假"或"没人请假"。
2. **`getcolumnval` 参数格式**：`userid` 是**单数**（不支持数组/逗号多用户）、`column_id_list` 必须是**逗号字符串**、日期必须带 `HH:MM:SS`。传错会报 `850015 缺少参数`。
3. **考勤报表列 ID 必须运行时用 `getattcolumns` 解析**，禁止硬编码（列 ID 因组织而异）。
4. **外出/出差用报表 `out_time` / `business_trip_time` > 0 判定**，否则提交外出单的人会被误判成未打卡/缺勤。
5. **日期必须对齐**：昨日未打卡用**昨日**的请假/外出过滤；今日迟到/缺勤用**今日**的过滤。混用会让人凭空消失。
6. 请假 API 的时间戳是**毫秒**。
7. 周一「昨日」= 上周五（`format_yesterday()`）。
8. **发送时间由 `schedule.yml` 的「等待至 10:00」步骤控制**，Python 里没有 sleep 调度。改发送时间改那里或 cron-job.org。
9. 推送分支统一 `HEAD:main`（历史上有代码推在 `master`、GitHub 只从 `main` 跑，导致整天不触发的坑）。
10. **`GROUPS` 当前只有「好达群」**。「好达团队管理部」已于 2026-10 解散并移除。测试用假群注入，**不要依赖真实群数量**。

## 业务口径（HR 已确认，不要擅自改）

| 通报项 | 判定条件 | 需过滤 |
|--------|---------|--------|
| 昨日下班未打卡 | 昨日有打卡记录，但无 `OffDuty` 且 `timeResult==Normal` | 昨日请假 + 昨日外出/出差 + 白名单 |
| 今天请假 | `getleavestatus` 覆盖今日 | 白名单 |
| 今天迟到 | 今日 `OnDuty` 且 `timeResult==Late` | 今日请假 + 今日外出/出差 + 白名单 |
| 今天缺勤 | 今日完全没有打卡记录 | 今日请假 + 今日外出/出差 + 白名单 |

白名单：`WHITE_LIST_NAMES = ["陈迪煊"]`。
群发送失败会继续尝试其余群，最终有失败则抛错（让 run 标红便于发现）—— 这是有意设计，别改成静默吞掉。

## 改完代码后

```bash
python -m unittest tests.test_attendance -v   # 必须先过
git add . && git commit -m "..." && git push origin HEAD:main
```

无 git 环境时也可用 GitHub Contents API 改单文件。

## 改动前自查

- [ ] 是否影响 4 个名单的口径？（请假 / 外出 / 白名单 / 日期归属）
- [ ] 是否新增了会真实发群的动作？验证优先跑单测或 `--web-only`
- [ ] `getcolumnval` 参数格式对不对？
- [ ] 节后首个工作日，「昨日」是否需要处理？（见下方已知问题）
- [ ] 改完测试还是绿的吗？

## 当前已知问题（接手后可优先处理）

| 优先级 | 问题 |
|--------|------|
| 高 | GitHub PAT 是 classic token，**会过期**，过期即静默停发（2026-08 事故原因） |
| 中 | `format_yesterday()` 只回退周末，**没考虑法定节假日**，节后首个工作日「昨日」可能落进假期 |
| 中 | GitHub Actions 偶发 `queued` 卡住 |
| 中 | 发送时间靠 runner 空等 30 分钟，cron 改 `0 10 * * 1-5` 可省掉 |
| 低 | `scf/` 已弃用但仍与主脚本重复维护，建议删或明确只保留 |
| 低 | 依赖 `uapis.cn` 免费节假日接口（已有周末回退兜底） |

## 密钥

**本仓库是公开的，所有密钥均为 `<...>` 占位符，切勿把真实值写回仓库。**
真实凭证由负责人 Xander 私下提供。若需实际跑通，向他要，并且**只在本地临时使用**，不要提交。

## 约定

- 中文注释、中文输出，与现有代码风格保持一致
- 新增依赖要慎重（当前只有 `requests`，保持精简）
- 改动涉及线上发送逻辑时，先说明方案再动手
