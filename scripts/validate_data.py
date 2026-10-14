"""카탈로그·판매 구성·정책·평가 자료와 검색 문서의 무결성 검사."""
import pathlib,sys,json,hashlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import openpyxl
from src.config import DATA_XLSX
from src.documents import _sheet_rows,build_documents
from src.cart import Cart,CartItem,option_rules
def main():
    wb=openpyxl.load_workbook(DATA_XLSX,data_only=True)
    menus=_sheet_rows(wb,"메뉴목록");variants=_sheet_rows(wb,"가격영양")
    mids={m["메뉴 ID"]:m for m in menus}
    assert len(menus)==len(mids)==33
    assert len(variants)==len({v["주문 단위 ID"] for v in variants})==52
    assert {m["분류"] for m in menus}=={"커피","차/논커피","디저트","주류","원두"}
    assert not ({"M19","M22","M30","M31"} & mids.keys())
    for v in variants:
        mid=v["주문 단위 ID"].split("-")[0];m=mids[mid]
        assert m["메뉴명"]==v["메뉴명"]
        assert type(v["가격(원)"]) is int and v["가격(원)"]>0
        c=Cart(table_id=1)
        assert c.add(CartItem(mid,v["주문 단위 ID"],m["메뉴명"],v["온도"],v["크기"]))[0]
    for rule in option_rules().values():
        assert {x.strip() for x in rule["적용 메뉴 ID"].split(",")} <= mids.keys()
    en=[x for x in _sheet_rows(wb,"한영안내") if x["메뉴 ID"] in mids]
    assert {x["메뉴 ID"] for x in en}==mids.keys()
    assert all(x.get("English description") and x.get("English name") for x in en)
    assert len(_sheet_rows(wb,"매장정책"))==19
    assert len(_sheet_rows(wb,"검증질문"))==47
    docs=build_documents()
    assert len(docs)==61 and len({d.metadata["doc_id"] for d in docs})==61
    assert not any(d.metadata["type"] in ("검증질문","선별내역") for d in docs)
    result={"menus":33,"variants":52,"options":6,"policies":19,"documents":61,
            "bilingual_menu_rows":33,"source_questions":47,"data_sha256":hashlib.sha256(DATA_XLSX.read_bytes()).hexdigest(),
            "all_checks_passed":True,"api_calls":0}
    (ROOT/"tests/data_validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
