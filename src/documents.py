"""데이터팀 엑셀(moki_data.xlsx) → RAG 문서로 변환.

설계 원칙 — 글자 수로 자르지 않고 '의미 단위'로 문서를 만든다.
메뉴 하나당 문서 하나이며, 그 메뉴의 주문 단위별 가격·영양·카페인을
한 덩어리로 유지한다. 가격만 따로 떨어져 검색되지 않게 하기 위해서다.

다만 검색에 쓰는 글과 모델에게 넘기는 글을 나눈다.
  page_content   = 짧은 검색용 요약 (이름·별칭·분류·한 줄 설명·태그·맛)
  metadata["full"] = 가격표·영양·알레르기·영문 안내까지 담은 전체 본문

한 문서에 전부 밀어 넣으면 임베딩이 평균값으로 흐려져, "하이볼"이라고 물어도
위스키 하이볼이 멀어지는 일이 생긴다. 검색은 짧은 글로 하고, 답변 근거로는
전체 본문을 넘기는 편이 정확하다.
"""
from __future__ import annotations
import openpyxl, hashlib
from langchain_core.documents import Document
from .config import DATA_XLSX


def _sheet_rows(wb, name):
    ws = wb[name]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows) if r and sum(1 for c in r if c) > 3)
    hdr = [str(c).strip() if c else "" for c in rows[hi]]
    out = []
    for r in rows[hi + 1:]:
        if not r or not r[0]:
            continue
        out.append({h: v for h, v in zip(hdr, r) if h})
    return out


def _won(v):
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return "-"


def build_documents() -> list[Document]:
    wb = openpyxl.load_workbook(DATA_XLSX, data_only=True)
    menus    = _sheet_rows(wb, "메뉴목록")
    variants = _sheet_rows(wb, "가격영양")
    beans    = _sheet_rows(wb, "원두")
    options  = _sheet_rows(wb, "옵션규칙")
    policies = _sheet_rows(wb, "매장정책")
    bilingual = {r["메뉴 ID"]: r for r in _sheet_rows(wb, "한영안내")}

    # 메뉴명 → 주문 단위 목록
    by_menu: dict[str, list[dict]] = {}
    for v in variants:
        by_menu.setdefault(str(v["주문 단위 ID"]).split("-")[0], []).append(v)

    docs: list[Document] = []

    # ── ① 메뉴 문서 ────────────────────────────────────────
    for m in menus:
        mid, name = m["메뉴 ID"], str(m["메뉴명"]).strip()
        vs = by_menu.get(mid, [])
        en = bilingual.get(mid, {})

        price_lines = []
        for v in vs:
            temp, size = v.get("온도"), v.get("크기")
            bits = [b for b in (temp if temp != "NA" else None,
                                size if size not in ("ONE", None) else None) if b]
            label = "/".join(bits) if bits else "기본"
            extra = []
            if v.get("카페인(mg)") not in (None, ""):
                extra.append(f"카페인 {v['카페인(mg)']}mg")
            if v.get("열량(kcal)") not in (None, ""):
                extra.append(f"{v['열량(kcal)']}kcal")
            if v.get("도수(계산 기준)") is not None:
                extra.append(f"시연 도수 {v['도수(계산 기준)'] * 100:.1f}%")
                extra.append(f"계산 액체량 {v.get('계산 액체량(ml)')}ml")
            for column in ("당류(g)", "탄수화물(g)", "단백질(g)", "지방(g)", "나트륨(mg)"):
                if v.get(column) is not None: extra.append(f"{column} {v[column]}")
            if v.get("제공량(표준 구성)"):
                extra.append(f"{v['제공량(표준 구성)']}{v.get('단위','')}")
            price_lines.append(
                f"  · {v['주문 단위 ID']} [{label}] {_won(v.get('가격(원)'))}"
                + (f"  ({', '.join(extra)})" if extra else ""))

        body = [
            f"[메뉴] {name} — {m['분류']} · {mid}",
            f"영문명: {m.get('영문명','')}",
            f"별칭: {m.get('별칭','')}",
            f"설명: {m.get('설명','')}",
            "주문 가능한 구성과 가격:",
            *price_lines,
            f"맛: 단맛 {m.get('단맛 1~5')}/5, 산미 {m.get('산미 1~5')}/5, "
            f"쓴맛 {m.get('쓴맛 1~5')}/5, 바디 {m.get('바디 1~5')}/5",
            f"원재료: {m.get('원재료(가상 레시피)','')}",
            f"알레르기 유발 재료: {m.get('알레르기 유발 재료','')}",
            f"추천 태그: {m.get('추천 태그','')}",
            f"판매 단위: {m.get('판매 단위','')} · 식감: {m.get('식감','')}",
            f"주류 구분: {m.get('주류 구분','')}",
        ]
        if m.get("페어링 ID"):
            body.append(f"어울리는 메뉴: {m['페어링 ID']}")
        if en:
            body += [
                "--- English ---",
                f"English name: {en.get('English name','')}",
                f"Description: {en.get('English description','')}",
                f"Ingredients: {en.get('Ingredients','')}",
                f"Allergens: {en.get('Allergen ingredients','')}",
                f"Texture: {en.get('Texture','')} · Order unit: {en.get('Order unit','')}",
                f"Alcohol: {en.get('Alcohol status','')}",
            ]

        full = "\n".join(str(x) for x in body)
        search_text = "\n".join([
            f"{name} ({m['분류']}) / {m.get('영문명','')}",
            f"별칭: {m.get('별칭','')}",
            str(m.get("설명", ""))[:90],
            f"태그: {m.get('추천 태그','')}",
            f"단맛{m.get('단맛 1~5')} 산미{m.get('산미 1~5')} "
            f"쓴맛{m.get('쓴맛 1~5')} 바디{m.get('바디 1~5')}",
            str(m.get("주류 구분", "")),
        ])
        docs.append(Document(
            page_content=search_text,
            metadata={"type": "메뉴", "menu_id": mid, "name": name,
                      "category": m["분류"], "description": m["설명"],
                      "description_en": en.get("English description", ""),
                      "order_unit": m.get("판매 단위", ""),
                      "is_alcohol": str(m.get("주류 구분", "")).startswith("주류 포함"),
                      "variant_ids": ",".join(str(v["주문 단위 ID"]) for v in vs),
                      "full": full}))

    # ── ② 원두 문서 ────────────────────────────────────────
    for b in beans:
        full = "\n".join([
                f"[원두] {b['원두명']} · {b['원두 ID']}",
                f"산지: {b.get('산지 설정','')} · 가공: {b.get('가공 설정','')} · 로스팅: {b.get('로스팅','')}",
                f"맛 노트(향 표현이며 원재료가 아님): {b.get('맛 노트(재료 아님)','')}",
                f"산미 {b.get('산미 1~5')}/5, 쓴맛 {b.get('쓴맛 1~5')}/5, 바디 {b.get('바디 1~5')}/5",
                f"디카페인: {b.get('디카페인','')} · 샷당 카페인 {b.get('카페인(mg/샷)')}mg",
                f"원두 판매 메뉴: {b.get('판매 메뉴 ID','')}",
        ])
        docs.append(Document(
            page_content=f"{b['원두명']} 원두 · {b.get('로스팅','')} · "
                         f"{b.get('맛 노트(재료 아님)','')} · 디카페인 {b.get('디카페인','')}",
            metadata={"type": "원두", "bean_id": b["원두 ID"],
                      "name": b["원두명"], "full": full}))

    # ── ③ 옵션 규칙 문서 ───────────────────────────────────
    for o in options:
        full = "\n".join([
                f"[옵션] {o['옵션명']} · {o['옵션 ID']}",
                f"적용 메뉴: {o.get('적용 메뉴 ID','')}",
                f"입력 형식: {o.get('입력 형식','')} · 기본값: {o.get('기본값','')}",
                f"선택값과 추가금: {str(o.get('선택값과 추가금','')).replace(chr(10),' / ')}",
                f"제한: {o.get('제한','')}",
                f"변경 시 처리: {o.get('변경 처리','')}",
                f"English: {o.get('English name','')} — {o.get('English restrictions','')}",
        ])
        docs.append(Document(
            page_content=f"옵션: {o['옵션명']} ({o.get('English name','')}) — "
                         f"{str(o.get('제한',''))[:110]}",
            metadata={"type": "옵션", "option_id": o["옵션 ID"],
                      "name": o["옵션명"], "full": full}))

    # ── ④ 매장 정책 문서 ───────────────────────────────────
    for p in policies:
        full = "\n".join([
            f"[매장 정책] {p['주제']} · {p['정책 ID']} ({p.get('구분','')})",
            str(p.get("내용", "")),
            f"English: {p.get('English policy','')}",
        ])
        docs.append(Document(
            page_content=f"매장 정책 — {p['주제']}: {str(p.get('내용',''))[:150]}",
            metadata={"type": "정책", "policy_id": p["정책 ID"],
                      "name": p["주제"], "full": full}))

    version = hashlib.sha256(DATA_XLSX.read_bytes()).hexdigest()
    for doc in docs:
        md = doc.metadata
        md["doc_id"] = md.get("menu_id") or md.get("bean_id") or md.get("option_id") or md.get("policy_id")
        md["version"] = version
    return docs


if __name__ == "__main__":
    ds = build_documents()
    from collections import Counter
    print(f"총 {len(ds)}개 문서 ·", dict(Counter(d.metadata["type"] for d in ds)))
    print("\n" + "─" * 70)
    print("검색용 텍스트:\n" + ds[1].page_content)
    print("\n전체 본문:\n" + ds[1].metadata["full"][:420])
