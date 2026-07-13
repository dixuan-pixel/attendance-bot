#!/usr/bin/env python3
"""
钉钉考勤通报 - 腾讯云函数 SCF 版本
定时触发器: cron(0 30 1 * * 1-5 *)  → 工作日 UTC 01:30 = 北京时间 09:30

部署方式:
  1. 在 SCF 控制台创建函数，Python 3.9 运行时
  2. 上传此代码包（含 requests 依赖）
  3. 添加定时触发器，cron 表达式: 0 30 1 * * 1-5 *
"""

import requests
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, List

# ============================================================
# 配置区
# ============================================================

CLIENT_ID = "dingtlilbw2uudhnf1cf"
CLIENT_SECRET = "nv92h8PppuyM8cn8OVI45q2uqOpskMm3n9rPnKE-dafxEi3MxtM4BUNg1LFrhfbp"
AGENT_ID = 4727999209

WHITE_LIST_NAMES = ["陈迪煊"]

LEAVE_PROCESS_CODE = None

GROUPS = [
    {"name": "好达团队管理部", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=7c605bd0e0dc82f15d9f5e95ab004797d077d38a83db7ebc5a6cbc70c8aec87e", "secret": "SEC2eed60acaf221629aa4f55986d5cec9aa76f526634caec60f4149333ce329e7b"},
    {"name": "好达群", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=d67acf704fc0fa194e9d7ac67eb60ad5593794e50d183674367781a5a525253e", "secret": "SECa313aa3c20476e1300f7ea7c884644c8fc47356a5ffb60f89dfabfedc4bf580e"},
]


# ============================================================
# 钉钉API客户端
# ============================================================

class DingTalkClient:
    def __init__(self, client_id: str, client_secret: str, agent_id: int):
        self.client_id = client_id
        self.client_secret = client_secret
        self.agent_id = agent_id
        self._token: Optional[str] = None
        self._token_expire: float = 0

    def _get_access_token(self) -> str:
        if self._token and time.time() < self._token_expire:
            return self._token

        try:
            resp = requests.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self.client_id, "appSecret": self.client_secret},
                timeout=10
            )
            data = resp.json()
            if "accessToken" in data:
                self._token = data["accessToken"]
                self._token_expire = time.time() + data.get("expireIn", 7200) - 60
                return self._token
        except:
            pass

        resp = requests.get(
            "https://oapi.dingtalk.com/gettoken",
            params={"appkey": self.client_id, "appsecret": self.client_secret},
            timeout=10
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取access_token失败: {data.get('errmsg')}")
        self._token = data["access_token"]
        self._token_expire = time.time() + data.get("expires_in", 7200) - 60
        return self._token

    def _request(self, method: str, path: str, json_data: dict = None) -> dict:
        token = self._get_access_token()
        url = f"https://oapi.dingtalk.com{path}"
        resp = requests.request(
            method, url + "?access_token=" + token,
            json=json_data,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"API调用失败 [{path}]: {data.get('errmsg', '')} (code={data.get('errcode')})")
        return data

    def get_all_user_ids(self) -> List[Dict]:
        users = []
        depts = []
        for retry in range(3):
            try:
                dept_data = self._request("POST", "/topapi/v2/department/listsub", json_data={
                    "dept_id": 1, "language": "zh_CN"
                })
                depts = dept_data.get("result", []) if isinstance(dept_data.get("result"), list) else [{"dept_id": 1}]
                break
            except:
                if retry < 2:
                    time.sleep(3)
                else:
                    depts = [{"dept_id": 1}]

        for dept in depts:
            did = dept.get("dept_id", 1)
            cursor = 0
            has_more = True
            while has_more:
                try:
                    data = self._request("POST", "/topapi/v2/user/list", json_data={
                        "dept_id": did, "cursor": cursor, "size": 100
                    })
                    result = data.get("result", {})
                    users.extend(result.get("list", []))
                    cursor = result.get("cursor", 0)
                    has_more = result.get("has_more", False)
                except:
                    break
        return users

    def get_attendance_list(self, work_date: str, user_ids: List[str]) -> List[Dict]:
        if not user_ids:
            return []
        all_records = []
        batch_size = 10
        for i in range(0, len(user_ids), batch_size):
            batch = user_ids[i:i + batch_size]
            for retry in range(3):
                try:
                    data = self._request("POST", "/attendance/list", json_data={
                        "workDateFrom": work_date + " 00:00:00",
                        "workDateTo": work_date + " 23:59:59",
                        "userIdList": batch,
                        "offset": 0,
                        "limit": 50
                    })
                    all_records.extend(data.get("recordresult", []))
                    break
                except Exception as e:
                    if retry < 2:
                        time.sleep(2)
            time.sleep(1)
        return all_records

    def get_leave_user_ids(self, user_ids: List[str], date_str: str) -> List[str]:
        if not user_ids:
            return []
        today_start = datetime.strptime(date_str + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        today_end = datetime.strptime(date_str + " 23:59:59", "%Y-%m-%d %H:%M:%S")
        start_ms = int(today_start.timestamp() * 1000)
        end_ms = int(today_end.timestamp() * 1000)

        leave_user_ids = set()
        userid_str = ",".join(user_ids)
        offset = 0
        has_more = True
        while has_more:
            data = self._request("POST", "/topapi/attendance/getleavestatus", json_data={
                "userid_list": userid_str,
                "start_time": start_ms,
                "end_time": end_ms,
                "offset": offset,
                "size": 20
            })
            result = data.get("result", {})
            has_more = result.get("has_more", False)
            for leave in result.get("leave_status", []):
                uid = leave.get("userid")
                ls = leave.get("start_time", 0)
                le = leave.get("end_time", 0)
                if ls <= end_ms and le >= start_ms:
                    leave_user_ids.add(uid)
            offset += 20
        return list(leave_user_ids)

    def send_webhook_message(self, webhook_url: str, message: str, secret: str = "") -> dict:
        timestamp = str(int(round(time.time() * 1000)))
        sign = ""
        if secret:
            sign_string = timestamp + "\n" + secret
            sign = base64.b64encode(
                hmac.new(secret.encode(), sign_string.encode(), digestmod=hashlib.sha256).digest()
            ).decode()
        url = webhook_url + f"&timestamp={timestamp}&sign={sign}"
        resp = requests.post(url, json={"msgtype": "text", "text": {"content": message}})
        data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"Webhook发送失败: {data.get('errmsg')}")
        return data


# ========== 工具函数 ==========

def should_skip_today(date_str: str = None) -> tuple:
    """通过免费节假日API判断今天是否需要跳过考勤通报。
    
    使用 UAPI (uapis.cn) 免费接口，无需注册，自动覆盖：
    - 法定节假日 → 跳过
    - 普通周末 → 跳过
    - 调休工作日 → 不跳过
    - 普通工作日 → 不跳过
    
    API 不可用时回退到简单周末判断。
    返回 (是否跳过, 原因)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    try:
        resp = requests.get(
            "https://uapis.cn/api/v1/misc/holiday-calendar",
            params={"date": date_str},
            timeout=5
        )
        data = resp.json()
        day = data.get("days", [{}])[0]
        is_workday = day.get("is_workday", None)
        if is_workday is True:
            return False, ""
        elif is_workday is False:
            holiday_name = day.get("legal_holiday_name", "")
            if holiday_name:
                return True, f"法定节假日({holiday_name})"
            return True, "周末"
    except Exception as e:
        print(f"[警告] 节假日API查询失败: {e}，回退到周末判断")

    # API 失败时的回退：按周末判断
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:
        return True, "周末(离线判断)"
    return False, ""


def format_yesterday() -> str:
    """获取上一个工作日。周一→上周五，其余→昨天。"""
    today = datetime.now()
    if today.weekday() == 0:  # 周一
        return (today - timedelta(days=3)).strftime("%Y-%m-%d")
    return (today - timedelta(days=1)).strftime("%Y-%m-%d")

def format_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def names_to_text(names: List[str], fallback: str = "无") -> str:
    return "、".join(names) if names else fallback


# ========== 核心逻辑 ==========

def run_attendance_report() -> dict:
    """执行考勤通报，返回结果字典"""
    client = DingTalkClient(CLIENT_ID, CLIENT_SECRET, AGENT_ID)
    yesterday = format_yesterday()
    today = format_today()

    # 步骤1: 获取成员
    users = client.get_all_user_ids()
    user_ids = [u["userid"] for u in users]
    name_map = {}
    for u in users:
        name_map[u["userid"]] = u.get("name", u["userid"])

    # 步骤2: 获取昨日打卡数据
    records = client.get_attendance_list(yesterday, user_ids)
    not_punched_out = []
    for uid in user_ids:
        name = name_map.get(uid, uid)
        user_recs = [r for r in records if r.get("userId") == uid]
        if user_recs:
            has_checkout = any(r.get("checkType") == "OffDuty" and r.get("timeResult") == "Normal" for r in user_recs)
            if not has_checkout:
                not_punched_out.append(name)

    # 获取今天的打卡记录
    today_records = client.get_attendance_list(today, user_ids)
    if len(today_records) == 0:
        return {"status": "skipped", "reason": "今日考勤数据获取失败"}

    late_today = []
    today_punched = set()
    for r in today_records:
        today_punched.add(r.get("userId"))
        if r.get("checkType") == "OnDuty" and r.get("timeResult") == "Late":
            late_today.append(name_map.get(r.get("userId"), r.get("userId")))

    absent_today = []
    for uid in user_ids:
        if uid not in today_punched:
            absent_today.append(name_map.get(uid, uid))

    # 步骤3: 获取请假人员
    leave_user_ids_today = client.get_leave_user_ids(user_ids, today) if user_ids else []
    leave_names = [name_map.get(uid, uid) for uid in leave_user_ids_today]
    leave_user_ids_yesterday = client.get_leave_user_ids(user_ids, yesterday) if user_ids else []
    leave_names_yesterday = set(name_map.get(uid, uid) for uid in leave_user_ids_yesterday)

    # 步骤4: 过滤
    leave_set = set(leave_names)
    late_today = [n for n in late_today if n not in leave_set]
    not_punched_out = [n for n in not_punched_out if n not in leave_names_yesterday]
    absent_today = [n for n in absent_today if n not in leave_set]

    # 白名单过滤
    white_set = set(WHITE_LIST_NAMES)
    if white_set:
        not_punched_out = [n for n in not_punched_out if n not in white_set]
        late_today = [n for n in late_today if n not in white_set]
        absent_today = [n for n in absent_today if n not in white_set]
        leave_names = [n for n in leave_names if n not in white_set]

    # 步骤5: 生成通报
    report = f"""【考勤通报】
1.昨日下班未打卡人员：
{names_to_text(not_punched_out)}

2.今天请假人员：
{names_to_text(leave_names)}

3.今天迟到人员：
{names_to_text(late_today)}

4.今天缺勤人员：
{names_to_text(absent_today)}
"""

    # 步骤6: 发送
    send_results = []
    for g in GROUPS:
        try:
            client.send_webhook_message(g["webhook_url"], report.strip(), g.get("secret", ""))
            send_results.append({"name": g["name"], "status": "success"})
            time.sleep(1)
        except Exception as e:
            send_results.append({"name": g["name"], "status": "failed", "error": str(e)})

    return {
        "status": "ok",
        "report": report,
        "stats": {
            "total_users": len(user_ids),
            "leave_today": len(leave_names),
            "leave_yesterday": len(leave_names_yesterday),
            "not_punched_out": len(not_punched_out),
            "late_today": len(late_today),
            "absent_today": len(absent_today),
        },
        "send_results": send_results
    }


# ========== SCF 入口函数 ==========

def main_handler(event, context):
    """腾讯云函数 SCF 入口"""
    skip, reason = should_skip_today()
    if skip:
        today_str = datetime.now().strftime("%Y-%m-%d")
        print(f"{today_str} 是{reason}，跳过考勤通报")
        return {"status": "skipped", "reason": reason}

    try:
        result = run_attendance_report()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"执行失败: {error_msg}")
        return {"status": "error", "message": str(e)}
