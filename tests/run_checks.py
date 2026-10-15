"""데이터팀 검증질문 47개를 앱에 돌려 보고 결과를 기록한다.

    python tests/run_checks.py            # 앞 5개만 (기본, 비용 절약)
    python tests/run_checks.py --all      # 47개 전부 (LLM 약 90회)
    python tests/run_checks.py --ids Q01 Q04 Q47
    python tests/run_checks.py --ids Q09 --out tests/results_a.md   # 다른 파일에 저장
    python tests/run_checks.py --use-cache   # 답변 캐시 사용 (기본은 읽지도 쓰지도 않음)
    python tests/run_checks.py --text "2만 원으로 두 명 음료랑 간식"   # 시트에 없는 문장
    python tests/run_checks.py --scenarios tests/demo_scenarios.md [--only S02 S08]   # 여러 턴 시연 시나리오

프롬프트 팀이 실패 사례를 기록해 발표 4번(약점) 자료로 쓰기로 한 그 표다.
결과는 tests/results.md 로 저장된다.
"""
from __future__ import annotations
import sys, re, pathlib, argparse, openpyxl, datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import DATA_XLSX
from src.documents import _sheet_rows
from src.index import load_index
from src.cart import Cart
from src.kiosk import handle
import src.chain as chain


def load_questions():
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    return _sheet_rows(wb, "검증질문")


def record(res, cart) -> list[str]:
    """한 턴의 결과를 md 줄로. 검색에서 빠진 건지, 들어왔는데 모델이 무시한 건지 가리려면 전체가 필요하다."""
    found = ", ".join(n for _, n, _ in res.trace[:4])
    trace = "\n".join(f"- {how} · {name}" + (f" ({score})" if score is not None else "")
                      for how, name, score in res.trace) or "(검색 안 함)"
    sent = ", ".join(d.metadata.get("name", "?") for d in res.docs) or "(없음)"
    return [
        f"**의도** {res.intent} · 재작성: {res.rewritten} · LLM {res.llm_calls}회",
        f"**검색** {found}",
        f"**검색 전체 trace**\n{trace}",
        f"**모델에 넘긴 문서** {sent}",
        f"**calc**\n```\n{res.calc or '(없음)'}\n```",
        f"**답변** {res.reply}",
        f"**장바구니** {cart.as_text()}",
    ]


def parse_scenarios(text: str) -> list[dict]:
    """demo_scenarios.md → [{id, title, hti, qids, turns: [{say | staff_check, expect}]}]"""
    out, cur = [], None
    for ln in text.splitlines():
        if m := re.match(r"^##\s+(S\d+)\s*·\s*(.+)$", ln):
            cur = {"id": m[1], "title": m[2].strip(), "hti": "", "qids": "", "turns": []}
            out.append(cur)
        elif cur is None:
            continue
        elif m := re.match(r"^-\s*HTI:\s*(.+)$", ln):
            cur["hti"] = m[1].strip()
        elif m := re.match(r"^-\s*검증질문:\s*(.+)$", ln):
            cur["qids"] = m[1].strip()
        elif m := re.match(r"^\d+\.\s*\[직원확인\]", ln):
            cur["turns"].append({"staff_check": True, "expect": ""})
        elif m := re.match(r"^\d+\.\s*손님:\s*(.+)$", ln):
            cur["turns"].append({"say": m[1].strip(), "expect": ""})
        elif (m := re.match(r"^\s+기대:\s*(.+)$", ln)) and cur["turns"]:
            cur["turns"][-1]["expect"] = m[1].strip()
    return out


def run_scenarios(path: str, only: list[str] | None, out_path: str, use_cache: bool):
    scs = parse_scenarios((ROOT / path).read_text(encoding="utf-8"))
    if only:
        scs = [s for s in scs if s["id"] in only]
    n_turns = sum(1 for s in scs for tn in s["turns"] if "say" in tn)
    print(f"시나리오 {len(scs)}개 · 손님 발화 {n_turns}턴 — LLM 최대 약 {n_turns * 2}회\n")
    store = load_index()
    out = ["# 시연 시나리오 실행 결과\n",
           f"실행 {datetime.date.today()} · {len(scs)}개 · 답변 캐시 {'사용' if use_cache else '끔'}\n"]
    total_calls = 0
    for s in scs:
        cart, history = Cart(table_id=5), []          # 시나리오 안에서는 장바구니·대화가 이어진다
        out += [f"\n## {s['id']} · {s['title']}", f"- HTI: {s['hti']}", f"- 검증질문: {s['qids']}"]
        for i, tn in enumerate(s["turns"], 1):
            if tn.get("staff_check"):
                cart.staff_checked = True
                out.append(f"\n### {i}. [직원확인] 나이 확인 완료로 바꿈")
                continue
            res = handle(tn["say"], store, cart, history)
            history += [{"role": "user", "content": tn["say"]},
                        {"role": "assistant", "content": res.reply}]
            total_calls += res.llm_calls
            print(f"[{s['id']}-{i}] {tn['say']}\n   답변 : {res.reply[:120]}\n")
            out += [f"\n### {i}. 손님: {tn['say']}", f"**기대** {tn['expect'] or '-'}"]
            out += record(res, cart)
            out.append("**판정** (직접 적기: 통과 / 실패 / 부분)")
    out.insert(2, f"LLM 호출 합계 {total_calls}회\n")
    (ROOT / out_path).write_text("\n".join(out), encoding="utf-8")
    print(f"LLM 호출 {total_calls}회 · 저장: {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--out", default="tests/results.md")
    ap.add_argument("--text", nargs="*", help="검증질문 시트에 없는 문장을 바로 돌린다")
    ap.add_argument("--use-cache", action="store_true",
                    help="답변 캐시를 읽고 쓴다. 기본은 끔 — 프롬프트를 고쳐도 옛 답변이 나오지 않게")
    ap.add_argument("--scenarios", help="여러 턴 시연 시나리오 파일 (tests/demo_scenarios.md)")
    ap.add_argument("--only", nargs="*", help="--scenarios 에서 돌릴 시나리오 ID")
    a = ap.parse_args()
    chain.USE_CACHE = a.use_cache
    if a.scenarios:
        out = a.out if a.out != "tests/results.md" else "tests/results_demo.md"
        return run_scenarios(a.scenarios, a.only, out, a.use_cache)

    qs = load_questions()
    if a.text:
        qs = [{"질문 ID": f"T{i}", "유형": "직접 입력", "테스트 질문": s, "기대 처리": "-"}
              for i, s in enumerate(a.text, 1)]
    elif a.ids:
        qs = [q for q in qs if q["질문 ID"] in a.ids]
    elif not a.all:
        qs = qs[: a.limit]

    print(f"검증질문 {len(qs)}개 실행 — LLM 약 {len(qs)*2}회\n")
    store = load_index()
    out = [f"# 검증질문 실행 결과\n",
           f"실행 {datetime.date.today()} · {len(qs)}개 · 답변 캐시 {'사용' if a.use_cache else '끔'}\n"]

    for q in qs:
        cart = Cart(table_id=5)          # 질문마다 새 장바구니
        res = handle(str(q["테스트 질문"]), store, cart, [])
        print(f"[{q['질문 ID']}] {q['유형']} · {q['테스트 질문']}")
        print(f"   검색 : {', '.join(n for _, n, _ in res.trace[:4])}")
        print(f"   답변 : {res.reply[:150]}\n")
        out += [
            f"\n## {q['질문 ID']} · {q['유형']}",
            f"**질문** {q['테스트 질문']}",
            f"**기대** {q['기대 처리']}",
        ] + record(res, cart) + ["**판정** (직접 적기: 통과 / 실패 / 부분)"]

    (ROOT / a.out).write_text("\n".join(out), encoding="utf-8")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
