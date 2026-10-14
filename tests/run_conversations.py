"""실제 여러 턴의 상태 전이를 검증한다."""
import sys,os,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from src.cart import Cart
from src.kiosk import handle
from src.index import load_index
from src.router import route
from unittest.mock import patch
def run():
    if "--key-stdin" in sys.argv:os.environ["OPENAI_API_KEY"]=sys.stdin.readline().strip()
    s=load_index();out=[]
    conversations=[
      ["따뜻한 디카페인 라떼랑 약과 한 접시 주세요","라떼는 작은 걸로요","라떼만 하나 더","주문 내역 보여줘","그 내용으로 시연 주문 확정할게요","추가로 아이스 아메리카노 작은 거 하나 주세요","영어로 바꿔줘","Show my current order","Cancel all items","Yes, cancel the draft cart"],
      ["저는 우유 알레르기가 있고 카페인 30mg 이하 음료를 원해요","오트로 바꾼 디카페인 아이스 라떼 작은 거 하나 주세요"],
      ["아이스 라떼 작은 거 하나 주세요","직전 변경 취소해줘"]]
    for number,questions in enumerate(conversations,1):
        c=Cart(table_id=3);history=[]
        for question in questions:
            routing=route(question,history,c.snapshot()|{"pending_actions":c.pending_actions,"pending_cancel":c.pending_cancel,"previous_orders":c.previous_orders})
            with patch("src.kiosk.route",return_value=routing): result=handle(question,s,c,history)
            history += [{"role":"user","content":question},{"role":"assistant","content":result.reply}]
            out.append({"conversation":number,"question":question,"plan":routing,"reply":result.reply,"state":c.snapshot(),"previous_orders":c.previous_orders})
            print(number,question,c.total,c.status(),flush=True)
    (ROOT/"tests/live_conversations.json").write_text(json.dumps(out,ensure_ascii=False,indent=2))
    assert [r["state"]["total_krw"] for r in out] == [0,10700,16900,16900,16900,4500,4500,4500,4500,0,0,6700,5500,0]
    assert out[4]["state"]["order_status"] == "confirmed_demo"
    assert out[5]["previous_orders"][0]["total_krw"] == 16900
    assert out[9]["previous_orders"][0]["order_no"] == out[4]["state"]["order_no"]
    assert all(i["bean"] == "B03" for i in out[2]["state"]["cart"] if i["menu_id"] == "M03")
    assert out[11]["state"]["avoid_allergens"] == ["우유"] and out[11]["state"]["max_caffeine_mg"] == 30
    print("14턴 상태 검증 통과",flush=True)
if __name__=="__main__":run()
