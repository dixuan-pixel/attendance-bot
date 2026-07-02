#!/usr/bin/env python3
"""
钉钉考勤通报自动推送脚本 v2.0
使用钉钉新版API（ClientId + ClientSecret）

使用方法:
  1. 在钉钉开放平台创建企业内部应用，获取凭证
  2. 在 应用 → 权限管理 中申请考勤、消息通知等权限
  3. 配置下方 GROUPS 中的群ID
  4. 部署到 GitHub Actions / 阿里云函数计算 定时运行
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

# 钉钉应用凭证（在钉钉开放平台 → 应用开发 → 钉钉应用 中获取）
CLIENT_ID = "dingtlilbw2uudhnf1cf"           # Client ID (原 AppKey)
CLIENT_SECRET = "nv92h8PppuyM8cn8OVI45q2uqOpskMm3n9rPnKE-dafxEi3MxtM4BUNg1LFrhfbp"  # Client Secret (原 AppSecret)
AGENT_ID = 4727999209                         # AgentId

# 考勤白名单（这些人员不参与考勤统计，如高管、外包等，填写姓名）
WHITE_LIST_NAMES = ["陈迪煊"]

# 请假审批流程编码（需要在钉钉管理后台找到请假模板的流程编码）
# 注意：这是"流程编码"不是"表单ID"
# 可在钉钉管理后台→工作台→审批→请假→编辑→地址栏找processCode=
LEAVE_PROCESS_CODE = None

# 要发送的群（好达团队管理部群的ID已配好，好达群请补充）
GROUPS = [
    {"name": "好达团队管理部", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=7c605bd0e0dc82f15d9f5e95ab004797d077d38a83db7ebc5a6cbc70c8aec87e", "secret": "SEC2eed60acaf221629aa4f55986d5cec9aa76f526634caec60f4149333ce329e7b"},
    {"name": "好达群", "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=d67acf704fc0fa194e9d7ac67eb60ad5593794e50d183674367781a5a525253e", "secret": "SECa313aa3c20476e1300f7ea7c884644c8fc47356a5ffb60f89dfabfedc4bf580e"},
]


# ============================================================
# 钉钉API客户端
# ============================================================

class DingTalkClient:
    """钉钉开放平台API客户端（支持新版OAuth2认证）"""
    
    def __init__(self, client_id: str, client_secret: str, agent_id: int):
        self.client_id = client_id
        self.client_secret = client_secret
        self.agent_id = agent_id
        self._token: Optional[str] = None
        self._token_expire: float = 0
    
    def _get_access_token(self) -> str:
        """获取access_token（兼容新旧API）"""
        if self._token and time.time() < self._token_expire:
            return self._token
        
        # 先用新版API试试
        try:
            resp = requests.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={
                    "appKey": self.client_id,
                    "appSecret": self.client_secret
                },
                timeout=10
            )
            data = resp.json()
            if "accessToken" in data:
                self._token = data["accessToken"]
                self._token_expire = time.time() + data.get("expireIn", 7200) - 60
                return self._token
        except:
            pass
        
        # 新版API失败则用旧版API
        resp = requests.get(
            "https://oapi.dingtalk.com/gettoken",
            params={
                "appkey": self.client_id,
                "appsecret": self.client_secret
            },
            timeout=10
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"获取access_token失败: {data.get('errmsg')}")
        
        self._token = data["access_token"]
        self._token_expire = time.time() + data.get("expires_in", 7200) - 60
        return self._token
    
    def _request(self, method: str, path: str, json_data: dict = None) -> dict:
        """向旧版API（oapi.dingtalk.com）发起请求"""
        token = self._get_access_token()
        url = f"https://oapi.dingtalk.com{path}"
        
        resp = requests.request(
            method, url,
            params={"access_token": token},
            json=json_data,
            headers={"Content-Type": "application/json"},
            timeout=15
        )
        data = resp.json()
        
        if data.get("errcode") != 0:
            raise Exception(
                f"API调用失败 [{path}]: {data.get('errmsg', '')} "
                f"(code={data.get('errcode')})"
            )
        return data
    
    def _request_v2(self, method: str, path: str, json_data: dict = None) -> dict:
        """向新版API（api.dingtalk.com）发起请求"""
        token = self._get_access_token()
        url = f"https://api.dingtalk.com{path}"
        
        resp = requests.request(
            method, url,
            json=json_data,
            headers={
                "Content-Type": "application/json",
                "x-acs-dingtalk-access-token": token
            }
        )
        data = resp.json()
        return data
    
    # ========== 成员查询 ==========
    
    def get_all_user_ids(self) -> List[Dict]:
        """获取组织所有成员列表"""
        users = []
        
        # 先获取部门列表
        try:
            dept_data = self._request("POST", "/topapi/v2/department/listsub", json_data={
                "dept_id": 1,
                "language": "zh_CN"
            })
            depts = dept_data.get("result", []) if isinstance(dept_data.get("result"), list) else [{"dept_id": 1}]
        except:
            depts = [{"dept_id": 1}]
        
        # 从每个部门获取成员
        for dept in depts:
            did = dept.get("dept_id", 1)
            cursor = 0
            has_more = True
            while has_more:
                data = self._request("POST", "/topapi/v2/user/list", json_data={
                    "dept_id": did,
                    "cursor": cursor,
                    "size": 100
                })
                result = data.get("result", {})
                users.extend(result.get("list", []))
                cursor = result.get("cursor", 0)
                has_more = result.get("has_more", False)
        
        return users
    

        """获取用户详细信息（姓名、部门等）"""
        try:
            data = self._request("POST", "/topapi/v2/user/get", json_data={"userid": user_id})
            return data.get("result")
        except:
            return None
    
    # ========== 考勤API ==========
    
    def get_attendance_list(self, work_date: str, user_ids: List[str]) -> List[Dict]:
        if not user_ids:
            return []
        """获取指定日期的打卡结果"""
        all_records = []
        offset = 0
        
        while True:
            data = self._request("POST", "/attendance/list", json_data={
                "workDateFrom": work_date + " 00:00:00",
                "workDateTo": work_date + " 23:59:59",
                "userIdList": user_ids,
                "offset": offset,
                "limit": 50
            })
            records = data.get("recordresult", [])
            all_records.extend(records)
            
            if len(records) < 50:
                break
            offset += 50
        
        return all_records
    
    def get_leave_user_ids(self, start_ms: int, end_ms: int, process_code: str = None) -> List[str]:
        """获取请假人员的userid列表"""
        if not process_code:
            print(f"  ⚠ 未配置请假流程编码，跳过请假数据获取")
            return []
        try:
            # 获取请假审批实例ID列表（请假模板process_code，不同企业可能不同）
            data = self._request("POST", "/topapi/processinstance/listids", json_data={
                "process_code": process_code,
                "start_time": start_ms,
                "end_time": end_ms,
                "size": 100
            })
            instance_ids = data.get("result", {}).get("list", [])
            if not instance_ids:
                return []
            
            # 获取每个审批实例的详情，提取申请人
            leave_user_ids = set()
            for pid in instance_ids[:30]:
                try:
                    detail = self._request("POST", "/topapi/processinstance/get", json_data={
                        "process_instance_id": pid
                    })
                    result = detail.get("result", {})
                    # 只统计已同意的请假
                    if result.get("status") == "COMPLETED" and result.get("result") == "agree":
                        leave_user_ids.add(result.get("originator_userid"))
                except:
                    pass
            
            return list(leave_user_ids)
        except Exception as e:
            print(f"  ⚠ 获取请假数据失败: {e}")
            return []
    
    def get_time_attendance_report(self, start_date: str, end_date: str, user_ids: List[str]) -> List[Dict]:
        """获取考勤报表"""
        all_results = []
        cursor = 0
        has_more = True
        
        while has_more:
            data = self._request("POST", "/topapi/attendance/getcolumnval", json_data={
                "userIds": user_ids,
                "columnIdList": [],
                "fromDate": start_date,
                "toDate": end_date,
                "cursor": cursor,
                "size": 50
            })
            result = data.get("result", {})
            all_results.extend(result.get("columnVals", []))
            cursor = result.get("cursor", 0)
            has_more = result.get("hasMore", False)
        
        return all_results
    
    # ========== 消息发送 ==========
    
    def send_group_message(self, chat_id: str, message: str) -> dict:
        """发送群消息（通过OA审批/应用消息通道）"""
        return self._request("POST", "/topapi/message/conversation/send", json_data={
            "sender": None,
            "agent_id": self.agent_id,
            "cid": chat_id,
            "msgtype": "text",
            "msgcontent": json.dumps({"content": message})
        })

    def send_webhook_message(self, webhook_url: str, message: str, secret: str = "") -> dict:
        """发送群消息（通过群机器人Webhook，支持加签）"""
        # 生成签名
        timestamp = str(int(round(time.time() * 1000)))
        sign = ""
        if secret:
            sign_string = timestamp + "\n" + secret
            sign = base64.b64encode(
                hmac.new(secret.encode(), sign_string.encode(), digestmod=hashlib.sha256).digest()
            ).decode()
        
        # 拼接URL
        url = webhook_url + f"&timestamp={timestamp}&sign={sign}"
        
        resp = requests.post(url, json={
            "msgtype": "text",
            "text": {"content": message}
        })
        data = resp.json()
        if data.get("errcode") != 0:
            raise Exception(f"Webhook发送失败: {data.get('errmsg')}")
        return data


# ========== 工具函数 ==========

def is_weekday(dt: datetime) -> bool:
    """判断是否工作日（周一至周五）"""
    return dt.weekday() < 5


def format_yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def format_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def date_to_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp() * 1000)


def names_to_text(names: List[str], fallback: str = "无") -> str:
    return "、".join(names) if names else fallback


# ========== 主函数 ==========

def main():
    print("=" * 50)
    print("钉钉考勤通报推送 v2.0")
    print("=" * 50)

    if CLIENT_ID == "your_client_id_here":
        print("❌ 请先在脚本中填写 ClientId 和 ClientSecret")
        return

    client = DingTalkClient(CLIENT_ID, CLIENT_SECRET, AGENT_ID)
    
    yesterday = format_yesterday()
    today = format_today()
    
    try:
        # 步骤1: 获取成员
        print(f"\n[1/4] 获取组织成员...")
        users = client.get_all_user_ids()
        user_ids = [u["userid"] for u in users]
        print(f"  找到 {len(user_ids)} 名成员")
        
        # 获取姓名映射（直接使用部门成员列表中的姓名）
        name_map = {}
        for u in users:
            name_map[u["userid"]] = u.get("name", u["userid"])
        
        # 步骤2: 获取昨日打卡数据
        print(f"[2/4] 获取昨日({yesterday})考勤数据...")
        records = client.get_attendance_list(yesterday, user_ids)
        
        # 分析打卡情况
        not_punched_out = []  # 下班未打卡
        late_today = []       # 今早上班迟到
        absent_today = []     # 今天缺勤
        all_punched_today = set()
        
        for uid in user_ids:
            name = name_map.get(uid, uid)
            user_recs = [r for r in records if r.get("userId") == uid]
            if user_recs:
                # 检查下班打卡
                has_checkout = any(r.get("checkType") == "OffDuty" for r in user_recs)
                if not has_checkout:
                    not_punched_out.append(name)
        
        # 获取今天的打卡记录
        today_records = client.get_attendance_list(today, user_ids)
        today_punched = set()
        for r in today_records:
            today_punched.add(r.get("userId"))
            if r.get("checkType") == "OnDuty" and r.get("timeResult") == "Late":
                late_today.append(name_map.get(r.get("userId"), r.get("userId")))
        
        # 缺勤 = 今天没有任何打卡的
        for uid in user_ids:
            if uid not in today_punched:
                absent_today.append(name_map.get(uid, uid))
        
        # 步骤3: 获取请假人员
        print(f"[3/4] 获取今日请假人员...")
        today_start = date_to_ms(today)
        today_end = today_start + 86400000
        
        leave_user_ids = client.get_leave_user_ids(today_start, today_end, LEAVE_PROCESS_CODE) if user_ids else []
        leave_names = [name_map.get(uid, uid) for uid in leave_user_ids]
        print(f"  请假人数: {len(leave_names)}")
        
        # 步骤4: 去除请假人员
        leave_set = set(leave_names)
        not_punched_out = [n for n in not_punched_out if n not in leave_set]
        late_today = [n for n in late_today if n not in leave_set]
        absent_today = list(set(absent_today + leave_names))
        
        # 步骤4.5: 过滤白名单（白名单人员不参与考勤统计）
        white_set = set(WHITE_LIST_NAMES)
        if white_set:
            not_punched_out = [n for n in not_punched_out if n not in white_set]
            late_today = [n for n in late_today if n not in white_set]
            absent_today = [n for n in absent_today if n not in white_set]
            leave_names = [n for n in leave_names if n not in white_set]
        
        # 步骤5: 生成考勤通报
        print(f"[4/4] 生成并推送考勤通报...")
        
        if len(user_ids) == 0:
            report = "【考勤通报】\n数据获取中，请稍后查看钉钉管理后台的考勤统计..."
            print("  用户列表为空，发送提示消息")
        else:
            report = f"""【考勤通报】
1.昨日下班未打卡人员：
{names_to_text(not_punched_out)}

2.今天迟到人员：
{names_to_text(late_today)}

3.今天缺勤人员（含请假）：
{names_to_text(absent_today)}
"""
        print("\n" + report)
        
        # 步骤6: 发送到群
        for g in GROUPS:
            try:
                if "webhook_url" in g:
                    client.send_webhook_message(g["webhook_url"], report.strip(), g.get("secret", ""))
                else:
                    client.send_group_message(g["chat_id"], report.strip())
                print(f"  ✅ 已发送到: {g['name']}")
                time.sleep(1)  # 避免触发限流
            except Exception as e:
                print(f"  ❌ 发送到 {g['name']} 失败: {e}")
        
        print("\n✅ 完成！")
        
    except Exception as e:
        print(f"\n❌ 脚本执行失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # 如果是工作日才执行
    if is_weekday(datetime.now()):
        main()
    else:
        print("今天是周末，跳过考勤通报")
