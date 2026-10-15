"""확인 질문을 눌러서 답할 수 있는 퀵 리플라이로 변환한다."""
from __future__ import annotations

import re

from .cart import find_variants, menu_by_id
from .config import current_language


_MENU_NAMES = {
    "zh": {
        "M01": "浓缩咖啡", "M02": "美式咖啡", "M03": "拿铁", "M04": "卡布奇诺",
        "M05": "馥芮白", "M06": "香草拿铁", "M07": "Goun-gyeol 奶油拿铁", "M08": "黑巧摩卡",
        "M09": "冷萃咖啡", "M10": "冷萃拿铁", "M11": "埃塞俄比亚手冲咖啡",
        "M12": "低因手冲咖啡", "M13": "抹茶拿铁", "M14": "巧克力拿铁",
        "M15": "宝城红茶奶茶", "M16": "柚子茶", "M17": "路易波士茶", "M18": "黄油盐面包",
        "M20": "巴斯克芝士蛋糕", "M21": "杯装提拉米苏", "M23": "招牌拼配咖啡豆 200克",
        "M24": "埃塞俄比亚咖啡豆 200克", "M25": "低因咖啡豆 200克", "M26": "五味子茶",
        "M27": "红枣姜茶", "M28": "药果（2个）", "M29": "艾草糯米糕（4个）",
        "M32": "柚子烧酒嗨棒", "M33": "五味子烧酒气泡酒", "M34": "威士忌嗨棒",
        "M35": "浓缩咖啡马天尼", "M36": "拉格啤酒", "M37": "招牌红葡萄酒",
    },
    "ja": {
        "M01": "エスプレッソ", "M02": "アメリカーノ", "M03": "カフェラテ", "M04": "カプチーノ",
        "M05": "フラットホワイト", "M06": "バニララテ", "M07": "ゴウンギョル・クリームラテ",
        "M08": "ダークカフェモカ", "M09": "コールドブリュー", "M10": "コールドブリューラテ",
        "M11": "エチオピア・フィルターコーヒー", "M12": "デカフェ・フィルターコーヒー",
        "M13": "抹茶ラテ", "M14": "チョコレートラテ", "M15": "宝城紅茶ミルクティー",
        "M16": "柚子茶", "M17": "ルイボスティー", "M18": "バター塩パン",
        "M20": "バスクチーズケーキ", "M21": "カップティラミス", "M23": "ハウスブレンド豆 200g",
        "M24": "エチオピア豆 200g", "M25": "デカフェ豆 200g", "M26": "オミジャ茶",
        "M27": "ナツメ生姜茶", "M28": "ヤックァ 2個", "M29": "よもぎインジョルミ 4個",
        "M32": "柚子焼酎ハイボール", "M33": "オミジャ焼酎スプリッツ", "M34": "ウイスキーハイボール",
        "M35": "エスプレッソマティーニ", "M36": "ラガービール", "M37": "ハウス赤ワイン",
    },
}


def _locale(language: str | None = None) -> str:
    value = str(language or current_language()).lower()
    return value if value in {"ko", "en", "zh", "ja"} else "ko"


def _choice_value(label: str, language: str) -> str:
    return {
        "ko": f"{label}로 할게요",
        "en": f"{label}, please",
        "zh": f"请选择{label}",
        "ja": f"{label}でお願いします",
    }[language]


def _menu_name(menu: dict, language: str) -> str:
    menu_id = str(menu.get("메뉴 ID", ""))
    if language == "ko":
        return str(menu.get("메뉴명") or menu_id)
    if language == "en":
        return str(menu.get("영문명") or menu.get("메뉴명") or menu_id)
    return _MENU_NAMES.get(language, {}).get(
        menu_id, str(menu.get("영문명") or menu.get("메뉴명") or menu_id))


def _unique(values):
    seen, result = set(), []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _reply(label: str, value: str | None = None) -> dict[str, str]:
    return {"label": label.strip(), "value": (value or label).strip()}


def _menu_ids(plan: dict, rewrite_result: dict) -> list[str]:
    ids = []
    for action in plan.get("actions") or []:
        for target in action.get("targets") or []:
            if target.get("menu_id"):
                ids.append(str(target["menu_id"]))
    for query in rewrite_result.get("queries") or []:
        ids.extend(str(mid) for mid in query.get("menu_ids") or [])
    return _unique(ids)


def _variant_replies(menu_id: str, question: str,
                     language: str) -> list[dict[str, str]]:
    variants = find_variants(menu_id)
    if len(variants) < 2:
        return []

    q = question.lower()
    asks_temp = any(word in q for word in (
        "온도", "따뜻", "차갑", "핫", "아이스", "hot", "iced", "temperature",
        "温度", "热饮", "冰饮", "温か", "冷た", "ホット", "アイス",
    ))
    asks_size = any(word in q for word in (
        "크기", "사이즈", "size", " s", " l", "尺寸", "大小", "规格", "サイズ", "大きさ",
    ))
    asks_variant = any(word in q for word in (
        "구성", "옵션", "variant", "option", "选项", "选择", "オプション", "選択", "構成",
    ))
    if not (asks_temp or asks_size or asks_variant):
        return []
    temps = _unique(str(v.get("온도")) for v in variants if v.get("온도") not in (None, "NA"))
    sizes = _unique(str(v.get("크기")) for v in variants if v.get("크기") not in (None, "ONE"))

    temp_label = {
        "ko": {"HOT": "따뜻하게", "ICED": "아이스"},
        "en": {"HOT": "Hot", "ICED": "Iced"},
        "zh": {"HOT": "热饮", "ICED": "冰饮"},
        "ja": {"HOT": "ホット", "ICED": "アイス"},
    }[language]
    size_label = {
        "ko": lambda value: f"{value} 사이즈",
        "en": lambda value: f"Size {value}",
        "zh": lambda value: f"{value} 杯型",
        "ja": lambda value: f"{value} サイズ",
    }[language]
    if asks_temp and not asks_size and len(temps) > 1:
        return [_reply(temp_label.get(temp, temp),
                       _choice_value(temp_label.get(temp, temp), language))
                for temp in temps]
    if asks_size and not asks_temp and len(sizes) > 1:
        return [_reply(size_label(size), _choice_value(size_label(size), language))
                for size in sizes]

    replies = []
    for variant in variants:
        temp, size = str(variant.get("온도")), str(variant.get("크기"))
        bits = []
        if temp != "NA":
            bits.append(temp_label.get(temp, temp))
        if size != "ONE":
            bits.append(size_label(size))
        if not bits:
            continue
        label = " · ".join(bits)
        replies.append(_reply(label, _choice_value(label, language)))
    return replies[:4]


def _question_replies(question: str, language: str) -> list[dict[str, str]]:
    if any(word in question.lower() for word in (
            "수량", "몇 잔", "몇 개", "quantity", "how many",
            "数量", "几杯", "几个", "数量", "何杯", "何個")):
        unit = {"ko": "개", "en": "", "zh": "份", "ja": "個"}[language]
        return [_reply(f"{qty}{unit}", _choice_value(f"{qty}{unit}", language))
                for qty in range(1, 4)]

    # 번호나 글머리표로 제시된 선택지
    listed = re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-•])\s*([^\n]{1,40})", question)
    if 2 <= len(listed) <= 4:
        return [_reply(item.rstrip(".?!。！？ "),
                       _choice_value(item.rstrip(".?!。！？ "), language))
                for item in listed]

    # "A와 B 중", "A 또는 B 중" 형태
    match = re.search(
        r"([^\n?.]{1,45}?)\s*(?:와|과|또는)\s*([^\n?.]{1,45}?)\s*중(?:에서)?",
        question,
    )
    if match:
        choices = []
        for raw in match.groups():
            value = re.sub(r"^(?:혹시|그러면|그럼|메뉴는)\s*", "", raw).strip(" ,")
            choices.append(_reply(value, _choice_value(value, language)))
        return choices

    # 짧은 슬래시 선택지: HOT / ICED, S / L 등
    slash = re.search(r"([^\s/]{1,16})\s*/\s*([^\s/]{1,16})", question)
    if slash:
        return [_reply(value, _choice_value(value, language)) for value in slash.groups()]

    yes_no_phrases = (
        "해드릴까요", "진행할까요", "맞나요", "괜찮을까요",
        "would you like", "shall i", "is that right", "okay", "吗", "是否", "可以吗",
        "しますか", "いかがですか", "よろしいですか", "ですか",
    )
    if any(phrase in question.lower() for phrase in yes_no_phrases):
        labels = {
            "ko": (("네, 좋아요", "네, 그렇게 해주세요"),
                   ("아니요", "아니요, 다른 선택지를 볼게요")),
            "en": (("Yes, please", "Yes, please"), ("No", "No, show me other choices")),
            "zh": (("好的", "好的，请这样办"), ("不用", "不用，请给我看其他选项")),
            "ja": (("はい", "はい、それでお願いします"),
                   ("いいえ", "いいえ、他の選択肢を見せてください")),
        }[language]
        return [_reply(label, value) for label, value in labels]
    return []


def build_quick_replies(question: str, plan: dict | None = None,
                        rewrite_result: dict | None = None,
                        language: str | None = None) -> list[dict[str, str]]:
    """실제 카탈로그를 우선하고, 없을 때만 질문 문구에서 선택지를 찾는다."""
    plan = plan or {}
    rewrite_result = rewrite_result or {}
    language = _locale(language)
    menu_ids = _menu_ids(plan, rewrite_result)

    if 2 <= len(menu_ids) <= 4:
        replies = []
        for menu_id in menu_ids:
            menu = menu_by_id(menu_id)
            if menu:
                name = _menu_name(menu, language)
                replies.append(_reply(name, _choice_value(name, language)))
        if len(replies) >= 2:
            return replies

    if len(menu_ids) == 1:
        replies = _variant_replies(menu_ids[0], question, language)
        if len(replies) >= 2:
            return replies

    return _question_replies(question, language)[:4]


def is_choice_prompt(text: str) -> bool:
    normalized = text.lower()
    return any(word in normalized for word in (
        "선택", "골라", "어느", "무엇을", "어떤", "할까요", "하시겠", "원하세요",
        "확인이 필요", "알려주세요", "알려주시겠", "맞나요", "수량", "몇 잔", "몇 개",
        "choose", "which", "would you like", "how many", "confirm",
        "选择", "请选", "哪个", "哪一个", "是否", "可以吗", "请告诉", "数量", "几杯", "几个",
        "選択", "選ん", "どれ", "どちら", "何を", "いかがですか", "しますか",
        "よろしいですか", "教えて", "確認", "数量", "何杯", "何個",
    ))
