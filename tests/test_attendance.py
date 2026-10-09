"""离线回归：禁止真实网络与群发送。"""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# 导入阶段提供网络禁用桩，不依赖本机安装 requests。
requests_stub = types.ModuleType('requests')
def deny_network(*args, **kwargs):
    raise AssertionError('测试禁止真实网络请求')
for method in ('get', 'post', 'request'):
    setattr(requests_stub, method, deny_network)
sys.modules['requests'] = requests_stub

class AttendanceTests(unittest.TestCase):
    def test_both_versions(self):
        for file in ('code/dingtalk_attendance_bot.py', 'code/scf/index.py'):
            with self.subTest(file=file):
                source = ROOT / file
                if not source.exists():
                    source = ROOT / file.removeprefix('code/')
                spec = importlib.util.spec_from_file_location('bot_test', source)
                bot = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(bot)
                with patch.object(bot.time, 'sleep'):
                    self.check_version(bot)

    def check_version(self, bot):
        client = bot.DingTalkClient('fake', 'fake', 0)
        calls = []
        def pages(*args, **kwargs):
            offset = kwargs['json_data']['offset']
            calls.append(offset)
            return {'recordresult': [{'userId': 'a'}] * (50 if offset == 0 else 2),
                    'hasMore': offset == 0}
        client._request = pages
        self.assertEqual(len(client.get_attendance_list('2026-10-09', ['a'])), 52)
        self.assertEqual(calls, [0, 50])
        # 第二页失败必须丢弃整次结果；每页独立重试。
        def partial(*args, **kwargs):
            if kwargs['json_data']['offset']:
                raise RuntimeError('page failed')
            return {'recordresult': [{'userId': 'a'}] * 50, 'hasMore': True}
        client._request = partial
        with self.assertRaises(RuntimeError):
            client.get_attendance_list('2026-10-09', ['a'])
        def leave(*args, **kwargs):
            self.assertEqual(kwargs['json_data']['start_time'], 1791475200000)
            self.assertEqual(kwargs['json_data']['end_time'], 1791561599000)
            return {'result': {'leave_status': [], 'has_more': False}}
        client._request = leave
        self.assertEqual(client.get_leave_user_ids(['a'], '2026-10-09'), [])
        client._resolve_att_columns = lambda: {'out_time': 1}
        with self.assertRaises(RuntimeError):
            client.get_out_trip_users(['a'], ['2026-10-09'])
        client._resolve_att_columns = lambda: {'out_time': 1, 'business_trip_time': 2}
        def fail(*args, **kwargs):
            raise RuntimeError('fetch failed')
        client._request = fail
        with self.assertRaises(RuntimeError):
            client.get_out_trip_users(['a'], ['2026-10-09'])
        # 主流程取数失败时必须中止，且不能发送。
        sent = []
        client.get_all_user_ids = lambda: [{'userid': 'a', 'name': '甲'}]
        client.get_attendance_list = fail
        client.send_webhook_message = lambda *a: sent.append(a)
        run = getattr(bot, 'main', None) or bot.run_attendance_report
        with patch.object(bot, 'DingTalkClient', return_value=client), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError): run()
        self.assertEqual(sent, [])
        # 成功取得全部数据后，一个群失败仍尝试另一个群，最终报错。
        client.get_attendance_list = lambda *a: [{'userId': 'a', 'checkType': 'OnDuty', 'timeResult': 'Normal'}]
        client.get_leave_user_ids = lambda *a: []
        client.get_out_trip_users = lambda *a: {}
        def send(*args):
            sent.append(args)
            if len(sent) == 1: raise RuntimeError('send failed')
        client.send_webhook_message = send
        with patch.object(bot, 'DingTalkClient', return_value=client), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError): run()
        self.assertEqual(len(sent), 2)
        if hasattr(bot, 'main_handler'):
            with patch.object(bot, 'should_skip_today', return_value=(False, '')), patch.object(bot, 'run_attendance_report', side_effect=RuntimeError('failed')), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError): bot.main_handler({}, None)

if __name__ == '__main__':
    unittest.main()
