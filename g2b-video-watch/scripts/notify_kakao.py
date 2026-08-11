# -*- coding: utf-8 -*-
"""
새로 발견된 공고를 카카오톡 '나에게 보내기'로 전송합니다.

필요한 환경변수:
  KAKAO_REST_API_KEY   카카오 개발자센터 앱의 REST API 키
  KAKAO_REFRESH_TOKEN  talk_message 동의를 받은 리프레시 토큰
  SITE_URL             대시보드 주소 (메시지의 버튼 링크로 들어갑니다)
"""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def refresh_access_token(rest_key, refresh_token):
    r = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": rest_key,
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()

    # 만료가 한 달 미만으로 남으면 카카오가 새 리프레시 토큰을 함께 내려줍니다.
    if payload.get("refresh_token"):
        (ROOT / "new_refresh_token.txt").write_text(payload["refresh_token"])
        print("새 리프레시 토큰이 발급되었습니다. 시크릿을 갱신하세요.")

    return payload["access_token"]


def money(won):
    if not won:
        return "금액 미공개"
    if won >= 100_000_000:
        return f"{won / 100_000_000:.1f}억원".replace(".0억", "억")
    return f"{won // 10_000:,}만원"


def dday(close_at):
    if not close_at:
        return ""
    try:
        left = (datetime.fromisoformat(close_at) - datetime.now(KST)).days
    except ValueError:
        return ""
    if left < 0:
        return "마감"
    return "오늘 마감" if left == 0 else f"D-{left}"


def build_text(items, site_url):
    head = f"영상 공고 {len(items)}건이 새로 올라왔습니다.\n"
    lines = []
    for it in items[: config.NOTIFY_MAX_ITEMS]:
        tag = "사전규격" if it["kind"] == "prespec" else "입찰"
        left = dday(it.get("close_at"))
        meta = " · ".join(x for x in [left, money(it.get("budget"))] if x)
        lines.append(f"\n[{tag}] {it['title'][:60]}\n{it['org'][:30]} · {meta}")

    rest = len(items) - config.NOTIFY_MAX_ITEMS
    tail = f"\n\n외 {rest}건" if rest > 0 else ""
    return (head + "".join(lines) + tail)[:1900]


def main():
    rest_key = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    site_url = os.environ.get("SITE_URL", "https://www.g2b.go.kr/").strip()

    path = ROOT / "new_items.json"
    items = json.loads(path.read_text("utf-8")) if path.exists() else []

    if not items and config.NOTIFY_ONLY_NEW:
        print("새 공고가 없어 알림을 보내지 않습니다.")
        return
    if not (rest_key and refresh_token):
        print("카카오 키가 없어 알림을 건너뜁니다.")
        return

    token = refresh_access_token(rest_key, refresh_token)
    template = {
        "object_type": "text",
        "text": build_text(items, site_url),
        "link": {"web_url": site_url, "mobile_web_url": site_url},
        "button_title": "공고 보러가기",
    }

    r = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=20,
    )
    if r.status_code == 200:
        print(f"카카오톡 알림 전송 완료 ({len(items)}건)")
    else:
        print(f"전송 실패 {r.status_code}: {r.text[:300]}")


if __name__ == "__main__":
    main()
