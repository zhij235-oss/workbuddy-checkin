"""WorkBuddy（腾讯 CodeBuddy）每日签到适配器。

通过官方计费接口直接签到，不依赖 GUI / 模拟点击 / OCR：
  - 查询状态: POST /v2/billing/meter/checkin-status
  - 领取签到: POST /v2/billing/meter/daily-checkin

环境变量：
  WORKBUDDY_ACCESS_TOKEN   auth.accessToken（必填）
  WORKBUDDY_UID            account.uid（建议，写入 X-User-Id）
  WORKBUDDY_DOMAIN         默认 www.codebuddy.cn
  WORKBUDDY_ACCOUNT_NAME   仅日志展示
  WORKBUDDY_ENTERPRISE_ID  企业账号才需要
"""
from __future__ import annotations
import json
import logging
import os
from urllib import error, request
from adapters.base import BaseAdapter, CheckinResult

logger = logging.getLogger(__name__)

API_BASE = "https://www.codebuddy.cn"
STATUS_URL = f"{API_BASE}/v2/billing/meter/checkin-status"
CHECKIN_URL = f"{API_BASE}/v2/billing/meter/daily-checkin"
TIMEOUT = 20


class WorkBuddyAdapter(BaseAdapter):
    name = "workbuddy"

    def enabled(self) -> bool:
        return bool(os.environ.get("WORKBUDDY_ACCESS_TOKEN"))

    def _creds(self) -> dict:
        return {
            "token": os.environ.get("WORKBUDDY_ACCESS_TOKEN", ""),
            "uid": os.environ.get("WORKBUDDY_UID", "").strip(),
            "domain": os.environ.get("WORKBUDDY_DOMAIN", "www.codebuddy.cn").strip(),
            "enterprise_id": os.environ.get("WORKBUDDY_ENTERPRISE_ID", "").strip(),
            "account_name": os.environ.get("WORKBUDDY_ACCOUNT_NAME", "").strip(),
        }

    def _headers(self, creds: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {creds['token']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "WorkBuddy-Checkin/1.1",
        }
        if creds["uid"]:
            headers["X-User-Id"] = creds["uid"]
        if creds["domain"]:
            headers["X-Domain"] = creds["domain"]
        if creds["enterprise_id"]:
            headers["X-Enterprise-Id"] = creds["enterprise_id"]
            headers["X-Tenant-Id"] = creds["enterprise_id"]
        return headers

    def _post(self, url: str, creds: dict) -> tuple[int, str]:
        req = request.Request(
            url, data=b"{}", method="POST", headers=self._headers(creds)
        )
        try:
            with request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")
        except error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except error.URLError as e:
            return 0, f"请求失败: {e}"

    @staticmethod
    def _already_checked_in(payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("code") == 10001:
            return True
        msg = str(payload.get("msg") or payload.get("message") or "")
        if "已签到" in msg:
            return True
        data = payload.get("data")
        if isinstance(data, dict) and (
            data.get("today_checked_in") or data.get("checked_in")
        ):
            return True
        return bool(payload.get("today_checked_in") or payload.get("checked_in"))

    def checkin(self) -> CheckinResult:
        creds = self._creds()
        who = creds["account_name"] or "WorkBuddy"

        code, body = self._post(STATUS_URL, creds)
        if code != 200:
            return CheckinResult(
                self.name, False, None,
                f"状态查询 HTTP {code}（token 可能已过期）", raw=body[:300],
            )

        code, body = self._post(CHECKIN_URL, creds)
        payload: dict | None = None
        try:
            payload = json.loads(body) if body else None
        except json.JSONDecodeError:
            pass

        if self._already_checked_in(payload):
            return CheckinResult(self.name, True, None, f"[{who}] 今天已签到", raw=body[:300])

        if code != 200:
            return CheckinResult(
                self.name, False, None, f"领取失败 HTTP {code}", raw=body[:300]
            )

        data = payload.get("data") if isinstance(payload, dict) else None
        points = None
        streak = None
        if isinstance(data, dict):
            points = data.get("credit") or data.get("today_credit") or data.get("points")
            streak = data.get("streak_days")
        msg = f"[{who}] 签到成功"
        if points is not None:
            msg += f"，+{points} 积分"
        if streak is not None:
            msg += f"，连续 {streak} 天"
        return CheckinResult(self.name, True, points, msg, raw=body[:300])