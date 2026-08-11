# -*- coding: utf-8 -*-
"""
나라장터 오픈API에서 용역 입찰공고 + 사전규격을 받아와
영상 관련 건만 골라 docs/data/notices.json 으로 저장합니다.

필요한 환경변수:
  G2B_SERVICE_KEY          조달청_나라장터 입찰공고정보서비스 인증키 (Decoding 키)
  G2B_PRESPEC_SERVICE_KEY  조달청_나라장터 사전규격정보서비스 인증키 (없으면 위 키 재사용)
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "notices.json"

BID_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch"
PRESPEC_URL = "https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc"


# --------------------------------------------------------------------------
# API 호출
# --------------------------------------------------------------------------
def fetch_once(url, service_key, q, timeout=60):
    """인증키를 붙여 한 번 요청합니다."""
    if "%" in service_key:
        return requests.get(url + "?serviceKey=" + service_key, params=q, timeout=timeout)
    q = dict(q, serviceKey=service_key)
    return requests.get(url, params=q, timeout=timeout)


def fetch_with_retry(url, service_key, q, tries=5):
    """나라장터 서버가 응답을 자주 끊어서, 실패하면 잠시 쉬었다가 다시 시도합니다."""
    waits = [5, 15, 30, 60]
    last = None
    for attempt in range(tries):
        try:
            resp = fetch_once(url, service_key, q)
            if resp.status_code == 200:
                return resp
            last = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.exceptions.RequestException as e:
            last = e

        if attempt < tries - 1:
            wait = waits[min(attempt, len(waits) - 1)]
            print(f"  응답이 없어 {wait}초 뒤 다시 시도합니다 ({attempt + 1}/{tries - 1})")
            time.sleep(wait)

    raise RuntimeError(f"{tries}번 시도했지만 실패했습니다: {last}")


def call_api(url, service_key, params, max_pages=20):
    """페이지를 끝까지 돌면서 items 리스트를 모아 반환합니다."""
    items = []
    for page in range(1, max_pages + 1):
        q = dict(params)
        q.update({"pageNo": page, "numOfRows": 100, "type": "json"})

        resp = fetch_with_retry(url, service_key, q)

        try:
            body = resp.json()["response"]["body"]
        except Exception:
            # 인증키 오류 등은 XML로 돌아옵니다.
            raise RuntimeError(f"응답을 해석할 수 없습니다: {resp.text[:400]}")

        chunk = body.get("items") or []
        if isinstance(chunk, dict):
            chunk = chunk.get("item") or []
        if isinstance(chunk, dict):
            chunk = [chunk]
        if not chunk:
            break

        items.extend(chunk)

        total = int(body.get("totalCount") or 0)
        if len(items) >= total:
            break
        time.sleep(0.5)

    return items


# --------------------------------------------------------------------------
# 필드 이름이 서비스마다 조금씩 달라서 후보를 순서대로 찾습니다.
# --------------------------------------------------------------------------
def pick(item, keys, default=""):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", "null"):
            return str(v).strip()
    return default


def parse_dt(raw):
    """'2026-08-11 18:00:00', '202608111800' 등을 ISO 문자열로."""
    if not raw:
        return ""
    s = re.sub(r"[^0-9]", "", str(raw))
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(s) >= length:
            try:
                return datetime.strptime(s[:length], fmt).replace(tzinfo=KST).isoformat()
            except ValueError:
                continue
    return ""


def to_int(raw):
    s = re.sub(r"[^0-9]", "", str(raw or ""))
    return int(s) if s else 0


# --------------------------------------------------------------------------
# 영상 관련성 판정
# --------------------------------------------------------------------------
def norm(text):
    """띄어쓰기·가운뎃점·괄호 등을 지워서 표기 차이를 없앱니다.
    '홍보 영상 제작' 과 '홍보영상제작' 이 같은 것으로 취급됩니다."""
    return re.sub(r"[\s·ㆍ・,.\-_~()\[\]{}/\\'\"]+", "", str(text)).lower()


def score_title(title):
    """(점수, 매칭된 키워드 목록)을 반환. 제외 키워드에 걸리면 (0, [])."""
    t = norm(title)

    for bad in config.EXCLUDE:
        if norm(bad) in t:
            return 0, []

    score, hits = 0, []
    for kw in config.STRONG:
        if norm(kw) in t:
            score += 3
            hits.append(kw)

    # 강한 키워드에 이미 포함된 낱말은 중복으로 세지 않습니다.
    blob = "".join(norm(h) for h in hits)
    for kw in config.WEAK:
        nk = norm(kw)
        if nk in t and nk not in blob:
            score += 1
            hits.append(kw)

    return score, hits


# --------------------------------------------------------------------------
# 정규화
# --------------------------------------------------------------------------
def normalize_bid(item):
    no = pick(item, ["bidNtceNo"])
    ord_ = pick(item, ["bidNtceOrd"], "00")
    return {
        "id": f"bid-{no}-{ord_}",
        "kind": "bid",
        "no": f"{no}-{ord_}",
        "title": pick(item, ["bidNtceNm"]),
        "org": pick(item, ["ntceInsttNm", "dminsttNm"]),
        "demand_org": pick(item, ["dminsttNm"]),
        "posted_at": parse_dt(pick(item, ["bidNtceDt", "rgstDt"])),
        "close_at": parse_dt(pick(item, ["bidClseDt", "opengDt"])),
        "budget": to_int(pick(item, ["asignBdgtAmt", "presmptPrce"])),
        "method": pick(item, ["cntrctCnclsMthdNm", "bidMethdNm"]),
        "contact": pick(item, ["ntceInsttOfclNm"]),
        "tel": pick(item, ["ntceInsttOfclTelNo"]),
        "url": pick(item, ["bidNtceDtlUrl"]),
    }


def normalize_prespec(item):
    no = pick(item, ["bfSpecRgstNo"])
    return {
        "id": f"pre-{no}",
        "kind": "prespec",
        "no": no,
        "title": pick(item, ["prdctClsfcNoNm", "bfSpecRgstNoNm", "sthngNm", "prdctNm"]),
        "org": pick(item, ["orderInsttNm", "rlDminsttNm", "dminsttNm"]),
        "demand_org": pick(item, ["rlDminsttNm", "dminsttNm"]),
        "posted_at": parse_dt(pick(item, ["rgstDt", "rcptDt"])),
        "close_at": parse_dt(pick(item, ["opninRgstClseDt"])),
        "budget": to_int(pick(item, ["asignBdgtAmt", "budgetAmount"])),
        "method": "사전규격 의견등록",
        "contact": pick(item, ["ofclNm", "ntceInsttOfclNm"]),
        "tel": pick(item, ["ofclTelNo", "ntceInsttOfclTelNo"]),
        "url": pick(item, ["specDocFileUrl1", "bfSpecRgstNoUrl"]),
    }


# --------------------------------------------------------------------------
def collect():
    key = os.environ.get("G2B_SERVICE_KEY", "").strip()
    if not key:
        raise SystemExit("G2B_SERVICE_KEY 가 설정되지 않았습니다.")
    prespec_key = os.environ.get("G2B_PRESPEC_SERVICE_KEY", "").strip() or key

    now = datetime.now(KST)
    begin = now - timedelta(days=config.LOOKBACK_DAYS)
    span = {
        "inqryDiv": "1",
        "inqryBgnDt": begin.strftime("%Y%m%d%H%M"),
        "inqryEndDt": now.strftime("%Y%m%d%H%M"),
    }

    found = []

    print(f"[입찰공고] {span['inqryBgnDt']} ~ {span['inqryEndDt']} 조회 중…")
    raw = call_api(BID_URL, key, span)
    print(f"  전체 {len(raw)}건 수신")
    found += [normalize_bid(x) for x in raw]

    if config.COLLECT_PRESPEC:
        try:
            print("[사전규격] 조회 중…")
            raw = call_api(PRESPEC_URL, prespec_key, span)
            print(f"  전체 {len(raw)}건 수신")
            found += [normalize_prespec(x) for x in raw]
        except Exception as e:
            print(f"  사전규격 조회를 건너뜁니다: {e}")

    # 영상 관련만 남기기
    matched = []
    for rec in found:
        if not rec["title"]:
            continue
        score, hits = score_title(rec["title"])
        if score < config.MIN_SCORE:
            continue
        rec["score"] = score
        rec["hits"] = hits[:5]
        rec["starred"] = any(o in rec["org"] for o in config.WATCH_ORGS)
        matched.append(rec)

    print(f"→ 영상 관련 {len(matched)}건")
    return matched


def merge(matched):
    """기존 목록과 합치고, 처음 본 공고에 first_seen 을 찍습니다."""
    old = {}
    if DATA_FILE.exists():
        try:
            old = {n["id"]: n for n in json.loads(DATA_FILE.read_text("utf-8"))["notices"]}
        except Exception:
            old = {}

    now_iso = datetime.now(KST).isoformat()
    fresh = []
    for rec in matched:
        prev = old.get(rec["id"])
        if prev:
            rec["first_seen"] = prev.get("first_seen", now_iso)
        else:
            rec["first_seen"] = now_iso
            fresh.append(rec)
        old[rec["id"]] = rec

    # 오래된 건 정리
    cutoff = datetime.now(KST) - timedelta(days=config.KEEP_DAYS)
    kept = []
    for rec in old.values():
        seen = rec.get("first_seen") or rec.get("posted_at")
        try:
            if seen and datetime.fromisoformat(seen) < cutoff:
                continue
        except ValueError:
            pass
        kept.append(rec)

    kept.sort(key=lambda r: (r.get("close_at") or "9999", r.get("posted_at") or ""))

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(
            {"updated_at": now_iso, "total": len(kept), "notices": kept},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"저장 완료: {DATA_FILE}  (전체 {len(kept)}건 / 신규 {len(fresh)}건)")
    return fresh


if __name__ == "__main__":
    new_items = merge(collect())
    # 알림 스크립트가 이어받을 수 있게 남겨둡니다.
    (ROOT / "new_items.json").write_text(
        json.dumps(new_items, ensure_ascii=False), encoding="utf-8"
    )
