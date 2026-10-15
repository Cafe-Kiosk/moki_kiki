"""손님에게 보이는 답변에서 내부 값을 지운다. run_checks 는 같은 패턴으로 남은 노출을 실패 처리한다.

지우는 것
  [담기완료] 같은 calc 태그                       — 모델이 calc 를 그대로 옮겨 적음 (S02 T2)
  #M05-HOT-ONE 같은 주문 단위 ID                   — 근거 문서의 ID 를 해시태그처럼 붙임
  (M03) · (B03) 처럼 괄호 안 메뉴·원두 ID
지우지 않는 것
  M0057 같은 시연 주문번호(M + 숫자 4자리), ⚠️/🧾 줄
"""
from __future__ import annotations
import re

TAG_RE = re.compile(r"\[[가-힣]{2,6}\]")
UNIT_ID_RE = re.compile(r"#?\bM\d{2}-[A-Z]+-[A-Z]+\b")
PAREN_ID_RE = re.compile(r"\s*\(\s*[MB]\d{2}(?:\s*[,·/]\s*[MB]\d{2})*\s*\)")

PATTERNS = {"태그": TAG_RE, "주문 단위 ID": UNIT_ID_RE, "괄호 안 메뉴 ID": PAREN_ID_RE}


def find_leaks(text: str) -> list[str]:
    """남아 있는 내부 값 목록. 비어 있으면 노출 없음."""
    return [f"{kind} {m.group().strip()}" for kind, pat in PATTERNS.items()
            for m in pat.finditer(str(text or ""))]


def sanitize_reply(text: str) -> str:
    out = []
    for ln in str(text or "").splitlines():
        if ln.lstrip().startswith(("⚠️", "⚠", "🧾")):     # 코드가 붙인 줄은 그대로
            out.append(ln)
            continue
        ln = PAREN_ID_RE.sub("", ln)
        ln = UNIT_ID_RE.sub("", ln)
        ln = TAG_RE.sub("", ln)
        out.append(re.sub(r"[ \t]{2,}", " ", ln).strip())
    return "\n".join(out).strip()
