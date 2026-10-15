"""prompts/ 폴더의 마크다운을 읽어 프롬프트로 쓴다.

프롬프트 팀이 파이썬을 건드리지 않고 .md 파일만 고쳐도 되게 분리했다.
파일 맨 위의 설명 블록(--- 윗부분, > 로 시작하는 줄, # 제목)은 지우고 본문만 쓴다.
"""
from __future__ import annotations
import json
import pathlib
from functools import lru_cache

PROMPT_DIR = pathlib.Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=8)
def load(name: str) -> str:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    if "\n---\n" in raw:                 # 설명 블록과 본문을 --- 로 나눈 경우
        raw = raw.split("\n---\n", 1)[1]
    lines = [ln for ln in raw.splitlines()
             if not ln.startswith("#") and not ln.lstrip().startswith(">")]
    return "\n".join(lines).strip()


@lru_cache(maxsize=4)
def load_schema(name: str) -> dict:
    """프롬프트팀의 구조화 출력 JSON Schema를 읽는다."""
    path = PROMPT_DIR / "schemas" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
