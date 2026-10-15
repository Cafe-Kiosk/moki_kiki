"""인덱스를 한 번만 만든다. 팀원은 각자 처음 한 번 실행하면 된다.

    python scripts/build_index.py

문서 122개를 임베딩한다. MOCK 모드에서는 별도 개발용 인덱스를 무료로 만든다.
이후 app.py 는 저장된 인덱스를 불러만 쓰므로 임베딩 비용이 0이다.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from src.index import build_index

if __name__ == "__main__":
    build_index()
