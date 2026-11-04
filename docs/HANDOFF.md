# 钉钉考勤通报机器人 · 交接文档

> 最近更新：2026-10-29
> 交接对象：Coding Agent / 开发者（接手日常运维与二次开发）
> 项目负责人：Xander

---

## 0. ⚠️ 敏感信息提示

仓库是**公开**的，本文档因此做了脱敏：所有凭证已替换为 `<...>` 占位符。
真实值由项目负责人 Xander 私下提供，**切勿把真实密钥写回仓库任何文件**。
若已泄露，立即轮换（见 §8.5）。

---

## 1. 项目是什么

一个**自动向钉钉群推送每日考勤通报**的定时任务，并额外维护一个 **GitHub Pages 考勤看板**。

- 每个**工作日**自动运行，**10:00（北京时间）发送**到钉钉群
- 从钉钉考勤系统拉取数据，统计 4 类异常人员
- 通报格式：

```
【考勤通报】
1.昨日下班未打卡人员：
xxx、yyy

2.今天请假人员：
xxx、yyy

3.今天迟到人员：
xxx

4.今天缺勤人员：
xxx
```

- 群消息只展示非空项目，沿用上面的固定编号；四项均为空时发送 `【考勤通报】\n全部正常`。完整四项日志仍保留，供网页看板解析。

- 接收群：**好达群**（原「好达团队管理部」群已于 2026-10 解散，已从配置移除）
- 面向对象：公司 HR / 管理层
- 附带产物：`web/` 静态看板，由 `pages.yml` 发布到 GitHub Pages（公开只读，仅为每日汇总，不含原始日志/密钥）

---

## 2. 系统架构与数据流

```
cron-job.org (免费在线定时器, 工作日 09:30 Asia/Shanghai)  ← 仅作“触发器”
        │  POST workflow_dispatch
        ▼
GitHub Actions  schedule.yml (钉钉考勤通报)
        │  ① 等待至 10:00（北京时间）  ← 发送时间的真正控制点
        │  ② pip install requests && python dingtalk_attendance_bot.py
        ▼
钉钉开放平台 API  ──  取成员 / 考勤打卡 / 请假状态 / 外出出差报表
        │
        ▼
钉钉群机器人 Webhook（好达群）──  推送通报

旁路：schedule.yml 运行完成 → 触发 pages.yml
        │  python scripts/export_attendance.py  (读本次 run 的 job 日志)
        ▼
   web/data.json  →  GitHub Pages 看板
```

**为什么这么绕？**

- 最初用 GitHub Actions 内置 `schedule`，但**延迟不可控**（曾延迟 11 小时、甚至不触发），已废弃
- 本地方案依赖电脑开机，用户不接受
- 腾讯云函数 SCF（`scf/` 目录）3 个月后收费，已弃用
- 最终选定：**cron-job.org 定时触发 GitHub Actions**（免费、准点）

**为什么发送时间是 10:00 而不是触发时间？**
cron-job.org 保持在 09:30 触发（历史稳定），`schedule.yml` 在触发后**等待到 10:00 再执行发送**。
好处：无需改 cron-job.org 即可调整发送时间；若触发时已过 10:00（如排队延迟）则立即发送。
代价：runner 会空等约 30 分钟（公开仓库不额外计费）。
> 可选优化：把 cron-job.org 的 cron 从 `30 9 * * 1-5` 改为 `0 10 * * 1-5`，等待步骤会自动变成「已过 10:00，立即发送」的空操作，省去 30 分钟空等。

---

## 3. 代码结构

```
attendance-bot/
├── dingtalk_attendance_bot.py       ← 主脚本（抓数+统计+发群+生成网页快照）
├── .github/workflows/
│   ├── schedule.yml                 ← 考勤通报（唯一定时入口，含 10:00 等待）
│   ├── pages.yml                    ← 导出并发布 GitHub Pages 看板
│   └── snapshot.yml                 ← 只生成网页快照（--web-only，不发群）
├── scripts/export_attendance.py     ← 读 Actions 日志，解析通报，写 web/data.json
├── web/                             ← 静态看板（index.html/app.js/style.css）
├── tests/test_attendance.py         ← 离线回归测试（禁网、禁发群）
├── scf/index.py                     ← 腾讯云函数版（已弃用，仅保持逻辑同步）
└── attendance-bot-scf.zip           ← SCF 部署包（已弃用）
```

| 文件 | 作用 | 状态 |
|------|------|------|
| `dingtalk_attendance_bot.py` | 核心逻辑：取数 → 统计 → 过滤 → 发群；`--web-only` 时只生成快照 | **线上运行** |
| `.github/workflows/schedule.yml` | 唯一入口 `workflow_dispatch` + 10:00 等待 | **线上运行** |
| `.github/workflows/pages.yml` | 生成/发布 Pages 看板 | **线上运行** |
| `.github/workflows/snapshot.yml` | 手动生成快照 | 线上可用 |
| `scripts/export_attendance.py` | 从 Actions 日志抽取通报生成 `data.json` | **线上运行** |
| `scf/index.py` | 同逻辑的云函数封装 | 已弃用，改动时同步即可 |

GitHub 仓库：`https://github.com/dixuan-pixel/attendance-bot`（默认分支 `main`）

---

## 4. 凭证与账号清单

### 4.1 钉钉企业内部应用

| 项 | 值 |
|----|----|
| Client ID (AppKey) | `<DINGTALK_CLIENT_ID>` |
| Client Secret (AppSecret) | `<DINGTALK_CLIENT_SECRET>` |
| AgentId | `<DINGTALK_AGENT_ID>` |

> 位置：钉钉开放平台 → 应用开发 → 企业内部应用
> 所需权限：考勤、通讯录、消息通知

### 4.2 群机器人 Webhook

| 群 | Webhook access_token | 加签密钥 |
|----|---------|---------|
| 好达群 | `<GROUP_WEBHOOK_TOKEN>` | `<GROUP_WEBHOOK_SECRET>` |

> 「好达团队管理部」群已于 2026-10 解散，其 Webhook 返回 `token is not exist`，已从 `GROUPS` 移除。
> 如需新增接收群：在钉钉群 → 群设置 → 智能群助手 → 添加自定义机器人，复制 Webhook+加签密钥，追加到 `GROUPS` 列表即可。

### 4.3 GitHub

| 项 | 值 |
|----|----|
| Token（classic PAT） | 见交接时私发（本文不落地明文，避免随文档扩散） |
| 所需权限 | `repo` + `workflow`（要能触发 workflow_dispatch 与推送代码） |
| 用途 | ① cron-job.org 触发用 ② 推送代码用 |

> ⚠️ **此 Token 会过期**，过期后 cron-job.org 返回 401、考勤停发。这是最近一次停发（2026-08）的原因。
> 到期请重新生成并同步更新到 cron-job.org 的请求头（见 §8.5）。

### 4.4 cron-job.org

| 项 | 值 |
|----|----|
| 账号 | Xander 注册的免费账号 |
| 作业 URL | `https://api.github.com/repos/dixuan-pixel/attendance-bot/actions/workflows/schedule.yml/dispatches` |
| 方法 | `POST` |
| 时区 | `Asia/Shanghai` |
| Cron | `30 9 * * 1-5`（触发 09:30，脚本内等到 10:00 发送） |
| 请求头 | `Authorization: token <PAT>` / `Accept: application/vnd.github+json` / `Content-Type: application/json` |
| 请求体 | `{"ref":"main"}` |

---

## 5. 钉钉 API 关键点与坑（重要）

脚本核心是一个 `DingTalkClient` 类，封装了旧版 `oapi.dingtalk.com` 接口。踩过的坑：

### 5.1 Token

- 新版 `POST https://api.dingtalk.com/v1.0/oauth2/accessToken`（`{appKey, appSecret}`）
- 失败自动回退旧版 `https://oapi.dingtalk.com/gettoken`

### 5.2 请假状态 —— 用 `getleavestatus`

```
POST /topapi/attendance/getleavestatus
{
  "userid_list": "uid1,uid2,...",   // 逗号字符串，可批量
  "start_time": <毫秒时间戳>,
  "end_time":   <毫秒时间戳>,
  "offset": 0, "size": 20
}
→ result.leave_status[] : {userid, start_time, end_time}
```
判断"当日请假"：请假区间与当天有交集即算。

> ⚠️ **绝对不要用 `getleaveapproveduration`**！它名字有误导性，返回的是**排班工时**（全员 505 分钟），不是请假时长。这是历史上最坑的一个 bug。
> ⚠️ 该 API 的时间戳是**毫秒**，且 `start_time/end_time` 必须是带时分秒的区间。

### 5.3 考勤报表 —— `getattcolumns` + `getcolumnval`

**步骤 1：动态解析列 ID**（列 ID 因组织而异，**切勿硬编码**）

```
POST /topapi/attendance/getattcolumns   body: {}
→ result[] : {id, name, alias}
```
脚本用到的 alias：

| alias | 含义 |
|-------|------|
| `out_time` | 外出时长 |
| `business_trip_time` | 出差时长 |
| `late_times` | 迟到次数 |
| `absenteeism_days` | 旷工天数 |
| `off_work_lack_card_times` | 下班缺卡次数 |
| `attendance_days` | 出勤天数 |
| `attend_result` | 考勤结果（文本） |

**步骤 2：取列值**

```
POST /topapi/attendance/getcolumnval
{
  "userid": "单个用户ID",              // ← 单数！不支持数组
  "column_id_list": "49171861,49171860",  // ← 必须是逗号字符串！传数组会报 850015 缺少参数
  "from_date": "2026-09-11 00:00:00",     // ← 必须带时分秒
  "to_date":   "2026-09-14 23:59:59"
}
→ result.column_vals[].column_vals[] : {date, value}
```
- 一次调用可返回**日期范围内每天**的值（省调用次数）
- 返回顺序不保证，需按 `column_vo.id` 和 `date` 自行归类

### 5.4 原始打卡记录

```
POST /attendance/list            // 注意：不是 /topapi/...
{
  "workDateFrom": "2026-09-11 00:00:00",
  "workDateTo":   "2026-09-11 23:59:59",
  "userIdList": ["uid1", ...],   // 这里是数组，批量
  "offset": 0, "limit": 50
}
→ recordresult[] : {
    userId, checkType(OnDuty/OffDuty),
    timeResult(Normal/Late/NotSigned/Absenteeism/...),
    approveTagName(外出/出差/请假),   // ← 打卡关联的审批类型
    approveId, procInstId, ...
  }
```
- `get_attendance_list` 做了分页（offset 步进 50）；**任一页失败整次结果作废并抛错**（保证不会用半截数据算出错误名单，见 tests）

### 5.5 限流

- 低层接口默认限流较严，脚本已加**分批（10 人/批）+ sleep(0.15~1s) + 重试 3 次**

---

## 6. 业务逻辑与统计口径

主流程在 `main(send_messages=True)`，4 个名单的定义与过滤规则：

| 通报项 | 判定条件 | 过滤掉 |
|--------|---------|--------|
| **1. 昨日下班未打卡** | 昨日有打卡记录，但**没有** `OffDuty` 且 `timeResult==Normal` 的记录 | 昨日请假 + **昨日外出/出差** + 白名单 |
| **2. 今天请假人员** | `getleavestatus` 覆盖今日的人 | 白名单 |
| **3. 今天迟到人员** | 今日 `OnDuty` 且 `timeResult==Late` | 今日请假 + **今日外出/出差** + 白名单 |
| **4. 今天缺勤人员** | 今日**完全没有打卡记录** | 今日请假 + **今日外出/出差** + 白名单 |

**关键点**：

- **请假/外出用「各自日期」过滤对应的项**：昨日未打卡用昨日请假过滤，今日迟到/缺勤用今日请假过滤（曾因混用导致邓银花被误杀）
- **外出/出差**：通过考勤报表 `out_time`/`business_trip_time > 0` 判定；只要当天有外出/出差单覆盖，就不计入未打卡/缺勤（贾志敏案例）
- 白名单：`WHITE_LIST_NAMES = ["陈迪煊"]`，不参与任何统计
- 发送群：`GROUPS`（当前仅「好达群」）；任一群发送失败会继续尝试其余群，最终若有失败则抛错（run 标红，便于发现）

---

## 7. 时间与节假日处理

### 7.1 发送时间

- cron-job.org 于工作日 **09:30** 触发 `schedule.yml`
- workflow 内「等待至 10:00」步骤：若当前 < 10:00 则 sleep 到 10:00；若已 > 10:00 立即执行
- 真正发群的时刻 = **10:00（北京时间）**

### 7.2 「昨日」的定义 —— `format_yesterday()`

```python
周一 → 上周五（-3 天）   其余 → 昨天（-1 天）
```
> ⚠️ **已知局限**：只考虑周末，**没考虑法定节假日**。若节后首个工作日是周二~周五，"昨日"可能落到假期里。可考虑改成"用节假日 API 回溯到最近一个工作日"。

### 7.3 是否跳过当天 —— `should_skip_today()`

- 调用免费接口 `https://uapis.cn/api/v1/misc/holiday-calendar?date=YYYY-MM-DD`
- 取字段 `days[0].is_workday`：
  - `true` → 发送（含**调休补班**的周末）
  - `false` → 跳过（法定节假日 / 普通周末）
- 接口失败时回退到简单周末判断
- 入口处判断，跳过则直接退出、不发消息

> 因此 cron 只需工作日触发，节假日/周末由脚本自己兜底判断。

---

## 8. 部署与运维

### 8.1 修改代码后的发布流程

1. 改 `dingtalk_attendance_bot.py`（如需同时改 `scf/index.py`）
2. 本地验证（见 §9）
3. 提交并推送：
   ```bash
   git add .
   git commit -m "..."
   git push https://<PAT>@github.com/dixuan-pixel/attendance-bot.git HEAD:main
   ```
   > 注意：本地克隆后默认分支就是 `main`，直接 `HEAD:main` 即可（历史上有 `master`/`main` 分支不一致的坑）

> 也可用 GitHub Contents API 直接改单文件（本项目多次使用，适合无 git 环境）。

### 8.2 手动触发一次（不等到点儿）

```bash
curl -X POST \
  -H "Authorization: token <PAT>" \
  -H "Accept: application/vnd.github+json" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  "https://api.github.com/repos/dixuan-pixel/attendance-bot/actions/workflows/schedule.yml/dispatches"
# 期望返回 HTTP 204
```
> ⚠️ 注意：手动触发同样会走「等到 10:00」；若在 10:00 前触发会空等，10:00 才会发群。

### 8.3 只更新网页（不发群）

```bash
# 方式一：手动运行 snapshot.yml（--web-only）
# 方式二：手动运行 pages.yml（重新导出日志并部署 Pages）
```

### 8.4 查看运行结果

```bash
curl -s -H "Authorization: token <PAT>" \
  "https://api.github.com/repos/dixuan-pixel/attendance-bot/actions/runs?per_page=5"
```

### 8.5 Token 轮换（重要）

1. 打开 `https://github.com/settings/tokens`
2. 生成新 classic token，勾选 `repo` + `workflow`
3. 更新 cron-job.org 作业请求头里的 `Authorization: token <新token>`
4. 更新本仓库推送命令里用的 token

---

## 9. 本地运行与测试

```bash
pip install requests
python dingtalk_attendance_bot.py            # 会真发群
python dingtalk_attendance_bot.py --web-only # 只生成快照，不发群
```

### 9.1 离线回归测试

```bash
python -m unittest tests.test_attendance -v
```
- 用 stub 替换 `requests`，**禁止真实网络**；断言不会发群
- 覆盖：分页、分页失败整次作废、请假时间戳边界、外出列缺失/失败、取数失败中止不发、多群部分失败仍尝试其余群

### 9.2 干跑验证建议

直接运行会**真的把消息发到群**。若只想验证数据，复制 `main()` 计算逻辑、去掉最后发送段，把 4 个名单 print 出来比对即可。

调试单个 API 的建议写法：

```python
from dingtalk_attendance_bot import DingTalkClient, CLIENT_ID, CLIENT_SECRET, AGENT_ID
client = DingTalkClient(CLIENT_ID, CLIENT_SECRET, AGENT_ID)
print(client.get_leave_user_ids(user_ids, "2026-09-14"))
```

---

## 10. 历史修复记录（踩坑时间线）

| 日期 | 问题 | 修复 |
|------|------|------|
| 2026-07-08 | 请假名单恒为空 | `getleaveapproveduration` 返回排班工时（全员 505 分钟）→ 改用 `getleavestatus` |
| 2026-07-10 | 定时不触发 | GitHub 默认分支是 `main`，代码在 `master` → 同步到 `main` |
| 2026-07-13 | 周末/节假日误发 | 接入节假日 API，自动跳过 |
| 2026-07-15 | 邓银花被误杀 | 昨日未打卡错用**今日**请假过滤 → 改为各日期各自过滤 |
| 2026-07-17 | 重复发送 | GitHub 内置 `schedule` + cron-job.org 双触发 → 删除内置 `schedule` |
| 2026-07-20 | 周一"昨日"错 | `format_yesterday()` 周一回退到周日 → 改为回退到上周五 |
| 2026-08-10 | 停发 | GitHub Token 过期 → cron-job.org 401 → 换新 token |
| 2026-09-14 | 外出单被误判 | 未处理外出/出差 → 新增 `get_out_trip_users()`，按报表 `out_time`/`business_trip_time` 剔除 |
| 2026-10 | 新增看板 | 引入 `pages.yml`/`snapshot.yml`/`export_attendance.py`/`web/`，Actions 日志→Pages 看板 |
| 2026-10-29 | 发送时间 09:30→10:00；群调整 | 移除已解散的「好达团队管理部」；workflow 加「等到 10:00」步骤；测试改用假群不再依赖群数量 |

---

## 11. 已知问题 & 待改进

| 优先级 | 问题 | 建议 |
|--------|------|------|
| 高 | **GitHub PAT 会过期**，过期即停发且不易察觉 | 换成无过期的 fine-grained token；或加监控告警 |
| 中 | `format_yesterday()` 节后首个工作日不准 | 改用节假日 API 回溯最近工作日 |
| 中 | GitHub Actions 偶发 `queued` 卡住 | 可加重试 / 换托管（如自建 runner） |
| 中 | 发送时间用「等待到 10:00」，runner 空等约 30 分钟 | 可把 cron 改 `0 10 * * 1-5` 省去空等 |
| 低 | 依赖 UAPI 免费接口 | 已有回退；可换更稳的数据源 |
| 低 | `scf/` 版本已弃用但与主脚本重复维护 | 决定：要么同步维护，要么删除 |
| 低 | `web/data.json` 依赖 Actions 日志保留期 | 老 run 日志过期后看板旧记录缺失属正常 |

---

## 12. 常见故障排查

| 现象 | 排查步骤 |
|------|---------|
| 群里没收到通报 | ①查 GitHub Actions runs ②HTTP 401→token 过期，换 token ③`queued` 卡住→手动触发或本地补发 |
| 某群失败、另一群正常 | 看日志 `token is not exist` → 该群机器人被删/解散，需重建 Webhook 或从 `GROUPS` 移除 |
| 通报时间不对（非 10:00） | 查 workflow「等待至 10:00」步骤日志；确认 TZ/时区 |
| 通报里名单不对 | 对比钉钉后台「考勤统计」；重点查请假/外出/出差过滤是否正确 |
| cron-job.org 报错 | 检查请求头三件套、请求体、时区是否 `Asia/Shanghai` |
| API 报 850015「缺少参数」 | `getcolumnval` 的 `column_id_list` 必须传**逗号字符串**，`userid` 必须是**单数** |
| 全员被算请假/未打卡 | 检查是否又用了 `getleaveapproveduration`，或日期格式没带时分秒 |
| 看板没更新 | 查 pages.yml 是否成功；`export_attendance.py` 依赖 `GITHUB_TOKEN` 与 run 日志 |

---

## 13. 交接清单（交给 Codex 后需知晓）

- [x] 源码已在仓库 `dixuan-pixel/attendance-bot`（main）
- [x] 完整交接文档（本文件）
- [x] 凭证清单（§4，Token 明文通过安全渠道单独提供）
- [x] API 坑位说明（§5）
- [x] 业务口径（§6）
- [x] 时间/节假日逻辑（§7，发送时间 10:00）
- [x] 看板子系统说明（§2/§3/§8.3）
- [x] 历史修复记录（§10）
- [x] 故障排查手册（§12）
- [x] 离线回归测试（§9.1）
- [ ] **待你确认**：是否需将 Token 换成 fine-grained（无过期）
- [ ] **待你确认**：`scf/` 目录保留还是删除
- [ ] **可选**：cron-job.org 改 `0 10 * * 1-5`，省去 30 分钟空等

---

_本文档随项目演进更新。有疑问找 Xander。_
