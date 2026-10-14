"""데이터팀 검증질문 47개를 앱에 돌려 보고 결과를 기록한다.

    python tests/run_checks.py            # 앞 5개만 (기본, 비용 절약)
    python tests/run_checks.py --all      # 47개 전부 (LLM 약 90회)
    python tests/run_checks.py --ids Q01 Q04 Q47

프롬프트 팀이 실패 사례를 기록해 발표 4번(약점) 자료로 쓰기로 한 그 표다.
결과는 tests/results.md 로 저장된다.
"""
from __future__ import annotations
import sys, pathlib, argparse, openpyxl, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import DATA_XLSX
from src.documents import _sheet_rows
from src.index import load_index
from src.cart import Cart
from src.kiosk import handle


def load_questions():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    return _sheet_rows(wb, "검증질문")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int, default=5)
    a = ap.parse_args()

    qs = load_questions()
    if a.ids:
        qs = [q for q in qs if q["질문 ID"] in a.ids]
    elif not a.all:
        qs = qs[: a.limit]

    print(f"검증질문 {len(qs)}개 실행 — LLM 약 {len(qs)*2}회\n")
    store = load_index()
    out = [f"# 검증질문 실행 결과\n", f"실행 {datetime.date.today()} · {len(qs)}개\n"]

    for q in qs:
        cart = Cart(table_id=5)          # 질문마다 새 장바구니
        res = handle(str(q["테스트 질문"]), store, cart, [])
        found = ", ".join(n for _, n, _ in res.trace[:4])
        print(f"[{q['질문 ID']}] {q['유형']} · {q['테스트 질문']}")
        print(f"   검색 : {found}")
        print(f"   답변 : {res.reply[:150]}\n")
        out += [
            f"\n## {q['질문 ID']} · {q['유형']}",
            f"**질문** {q['테스트 질문']}",
            f"**기대** {q['기대 처리']}",
            f"**검색** {found}",
            f"**답변** {res.reply}",
            f"**장바구니** {cart.as_text()}",
            "**판정** (직접 적기: 통과 / 실패 / 부분)",
        ]

    (ROOT / "tests" / "results.md").write_text("\n".join(out), encoding="utf-8")
    print(f"저장: tests/results.md")


if __name__ == "__main__":
    main()
