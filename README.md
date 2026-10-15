# 모키 커피바 — RAG 테이블 주문 키오스크

AI응용 실습문제(RAG) · 4조. 손님이 테이블에서 글로 메뉴를 묻고 주문하는 과제 시연용 앱입니다.
메뉴 사실은 검색하고, 가격·옵션·주문 상태는 코드로 검증합니다.

## 팀원은 여기부터 읽어주세요

**[팀원용 통합 안내 — 2026-10-15](docs/team/README.md)**

컨셉부터 데이터·HTI·개발·프롬프트·발표까지의 전체 과정, 역할별 인수인계,
검증 범위와 남은 일, 최신 16장 발표 PDF·PPT를 모았습니다.

| 항목 | 현재 상태 | 확인할 곳 |
|---|---|---|
| 이 기능 브랜치 앱 | 한·영 RAG 122개와 v1.3 에이전트 프롬프트 적용 | `app.py`, `src/`, `prompts/` |
| 별도 수정 후보 `bb5b0a2` | [PR #1](https://github.com/Cafe-Kiosk/moki_kiki/pull/1)의 과거 작업 기록 | `codex/complete-moki-order-flow` |
| 최신 발표 | 16장 발표 자료 | [PDF](docs/team/presentation/팀과제_4조_모키커피바.pdf) · [PPT](docs/team/presentation/모키_커피바_최종발표.pptx) |

발표 자료와 별도 수정 후보의 모든 기능이 현재 `main`이나 공유 배포본에 반영됐다는 뜻은 아닙니다.

## 처리 흐름

```text
손님 입력 → 질의 재작성(LLM) → 하이브리드 검색 → 의도·실행계획(LLM)
                                               → 서버 검증·장바구니 → 답변 생성(LLM)
```

에이전트가 실행 계획을 만들더라도 장바구니 변경 전에 메뉴·주문 단위·수량·옵션·주류 조건을
코드에서 다시 검증합니다. `needs_clarification=true`이면 상태 변경을 보류합니다.

화면은 따뜻한 목재·한지·호박색 조명을 사용한 한옥 카페바 콘셉트입니다. 첫 화면의 추천
버튼과 대화 중 확인 버튼을 누르면 문장 입력 없이 다음 단계로 진행할 수 있습니다. 메뉴와
온도·크기 선택지는 가능한 경우 실제 카탈로그에서 생성합니다.

사진 메뉴판은 `data/moki_data.xlsx`의 **사진메뉴판** 시트에 임베드된 대표 이미지 33장을
`assets/menu/`로 추출해 표시합니다. 원본 엑셀이 바뀌면 `python scripts/extract_menu_images.py`를
실행해 웹 자산을 다시 만들 수 있습니다.

첫 접속에는 한옥 미닫이문 인트로가 재생됩니다. 실행 후 왼쪽 사이드바의 **API 연결**에서
OpenAI API 키를 입력하면 현재 브라우저 세션에만 적용되며, **데모 모드**를 켜면 API 비용
없이 화면과 기본 흐름을 확인할 수 있습니다.

히어로 배경은 “Make a nice house with a modern interpretation of the hanok house in the Joseon
Dynasty in Korea”를 바탕으로 생성한, 여백이 넉넉한 현대 한옥 카페입니다. 한복을 입은 모키 마스코트는
인트로·히어로에 등장하고, AI 답변 말풍선에는 손님에게 귀 기울이는 전용 모키 아바타가 표시됩니다.
마지막 답변은 음성으로 들을 수 있습니다.

## 빠른 시작

Python 3.12 또는 3.13을 권장합니다.

```bash
git clone https://github.com/Cafe-Kiosk/moki_kiki.git
cd moki_kiki
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m streamlit run app.py
```

API 호출 없이 화면과 규칙 검색을 개발하려면 `.env`에서 `MOKI_MOCK=1`로 설정합니다.

```bash
MOKI_MOCK=1 python -m streamlit run app.py
```

화면 체험 모드는 시스템 프롬프트와 실제 AI를 사용하지 않는 UI 시험 모드이며, 실제 RAG/LLM
대화 품질의 근거로 사용하지 않습니다. 자연스러운 다중 턴 대화를 확인하려면 API 키를 연결하고
화면 체험 모드를 끄세요. 개발용 인덱스는 `index/faiss_mock/`에 생성되어 운영 인덱스를 덮어쓰지 않습니다.

## RAG 데이터와 인덱스

- `data/moki_data.xlsx`: 가격·주문 검증 원장
- `data/rag_documents.jsonl`: 앱이 직접 적재하는 한·영 검색 문서 122개
- `docs/team/data/rag_documents.jsonl`: 팀 산출물 보관본

문서 구성은 메뉴 66, 원두 6, 매장정책 38, 용어집 12개입니다. 각 엔티티는 한국어와 영어
문서로 나뉘며, 메뉴 문서 안에 주문 단위별 가격·영양·카페인·허용 옵션을 함께 둡니다.

실제 API 모드의 인덱스가 JSONL과 다르면 최초 1회 122개 문서를 다시 임베딩합니다.
팀에서는 한 명만 운영용 인덱스를 만든 뒤 결과를 공유하세요.

```bash
MOKI_MOCK=0 python scripts/build_index.py
git add index/faiss
git commit -m "RAG 인덱스 갱신"
```

인덱스 재생성에는 임베딩 비용이 발생합니다. 데이터와 JSONL을 바꾸지 않았다면 반복 생성하지 않습니다.

## 프롬프트

| 파일 | 역할 |
|---|---|
| `prompts/system.md` | 응대 규칙·근거 제한·안전·접근성 |
| `prompts/rewrite.md` | 검색 질의 재작성 |
| `prompts/intent.md` | 의도 분류와 실행 계획 |
| `prompts/few_shot.md` | 예외·악성 고객·접근성 대응 예시 50개 |
| `prompts/schemas/rewrite.json` | 재작성 출력 JSON Schema |
| `prompts/schemas/intent.json` | 실행 계획 출력 JSON Schema |
| `prompts/offtopic.md` | 범위 밖 질문 응대 |

구조화 출력이 스키마 검증에 실패하면 상태를 변경하지 않는 안전한 계획으로 돌아갑니다.
few-shot 라이브러리는 전체를 매번 넣지 않고 현재 발화·안전 플래그·상태에 맞는 2~4개만
답변 생성 단계에 제공합니다. 예시는 응답 방식 참고용이며 메뉴·가격·정책의 사실 근거로 쓰지 않습니다.

웹 사이드바의 **콘텐츠 연결**은 엑셀 메뉴 33개, RAG 문서 122개, 대표 사진 33장과 시스템
프롬프트 필수 규칙이 서로 일치하는지 확인합니다. 고객 화면에는 내부 벡터 거리나 기준값 대신
실제로 답변에 사용된 메뉴·원두·매장 안내만 읽기 쉬운 이름으로 표시합니다.

## 구조와 담당

| 담당 | 기존 팀 담당자 | 수정 위치 |
|---|---|---|
| 데이터 | 류성환 · 오승재 | `data/`, `src/documents.py`, 검색 인덱스 |
| 프롬프트 | 안나량 · 이주연 | `prompts/`, `tests/prompt_core_cases.csv` |
| 개발 | 박채원 · 신기훈 | `app.py`, `src/`, `tests/` |

```text
app.py                         Streamlit 화면
prompts/                       시스템·재작성·의도 프롬프트와 스키마
src/config.py                  모델·경로·비용 설정
src/documents.py               JSONL → LangChain 문서 122개
src/index.py                   FAISS 인덱스·소스 매니페스트·캐시
src/retrieve.py                별칭·정책·맛점수 + 벡터 하이브리드 검색
src/router.py                  질의 재작성 + 의도/실행계획
src/cart.py                    옵션·수량·가격·주류 검증
src/chain.py                   근거 기반 답변 생성 + 캐시
src/kiosk.py                   전체 파이프라인
src/quick_replies.py           확인 질문 → 메뉴·옵션 선택 버튼
scripts/build_index.py         인덱스 생성
tests/test_logic.py            기존 가격·정책·검색 규칙 검사
tests/test_artifact_integration.py  새 산출물 연동 검사
tests/prompt_core_cases.csv    프롬프트팀 핵심 평가 케이스 60개
```

## 검증

API를 호출하지 않는 로컬 검사는 다음과 같이 실행합니다.

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/test_logic.py
```

`tests/prompt_core_cases.csv`의 60개 케이스는 실제 모델을 사용하는 별도 평가 자료이며 기본 단위
테스트에서 자동 호출하지 않습니다.

## 공유 실행과 제한

Streamlit Cloud에서는 저장소 `Cafe-Kiosk/moki_kiki`, 브랜치 `main`, 진입 파일 `app.py`를 지정합니다.
환경변수 또는 Streamlit Secrets에 `OPENAI_API_KEY`와 `MOKI_PASSWORD`를 설정합니다.
`.env`·실제 키·비밀번호·개인 정보가 든 로그는 Git에 올리지 않습니다. 공개 앱은 접근 비밀번호를
반드시 설정합니다.

한국어·영어 RAG 자료와 ko/en/zh/ja 응답 지침, 좌석 1~12, 메뉴 질문과 시연 주문을 지원합니다.
실제 결제·매장 접수·직원 인증·쿠폰·포인트·영수증은 연결하지 않았습니다. 가격·영양·도수·사진은
가상 매장 설정이며, 주류는 직원 확인 대기까지만 처리합니다.

[검증 결과와 남은 일](docs/team/03_검증과_남은일.md) · [발표·시연 대본](docs/team/04_발표와_시연.md) · [최신 HTI](docs/team/HTI_원문기준과_시연대응.md)
