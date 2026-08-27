"""签到结果推送：支持 Telegram / Server酱 / Bark / 自定义 Webhook，未配置则仅记日志。"""
from __future__ import annotations
import json
import logging
import os
from urllib import error, parse, request

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict, timeout: int = 15):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except error.URLError as e:
        return None, str(e)


def _post_form(url: str, fields: dict, timeout: int = 15):
    data = parse.urlencode(fields).encode("utf-8")
    req = request.Request(
        url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except error.URLError as e:
        return None, str(e)


def send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    status, body = _post_form(url, {"chat_id": chat_id, "text": text})
    try:
        data = json.loads(body or "{}")
        ok = bool(data.get("ok"))
    except json.JSONDecodeError:
        ok = status == 200
    logger.info("Telegram 推送%s (HTTP %s)", "成功" if ok else "失败", status)


def send_serverchan(sckey: str, title: str, text: str) -> None:
    url = f"https://sctapi.ftqq.com/{sckey}.send"
    status, _ = _post_json(url, {"title": title, "desp": text})
    logger.info("Server酱 推送状态: %s", status)


def send_bark(bark_url: str, title: str, text: str) -> None:
    url = f"{bark_url.rstrip('/')}/{title}/{text}"
    try:
        with request.urlopen(request.Request(url), timeout=15) as resp:
            logger.info("Bark 推送状态: %s", resp.status)
    except Exception as e:  # noqa: BLE001
        logger.warning("Bark 推送失败: %s", e)


def send_webhook(webhook: str, text: str) -> None:
    status, _ = _post_json(
        webhook, {"msgtype": "text", "text": {"content": text}}
    )
    logger.info("Webhook 推送状态: %s", status)


def send_notifications(text: str) -> None:
    sent: list[str] = []
    if bot := os.environ.get("TELEGRAM_BOT_TOKEN"):
        chat = os.environ.get("TELEGRAM_CHAT_ID")
        if chat:
            send_telegram(bot, chat, text)
            sent.append("Telegram")
    if sc := os.environ.get("SERVERCHAN_SCKEY"):
        send_serverchan(sc, "WorkBuddy 签到日报", text)
        sent.append("Server酱")
    if bk := os.environ.get("BARK_URL"):
        send_bark(bk, "WorkBuddy签到", text)
        sent.append("Bark")
    if wh := os.environ.get("NOTIFY_WEBHOOK"):
        send_webhook(wh, text)
        sent.append("Webhook")
    if not sent:
        logger.info("未配置任何推送渠道，报告仅输出到日志")