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
버튼과 대화 중 확인 버튼을 누르면 문장 입력 없이 다음 단계로 진행할 수 있습니다. 메뉴를
고른 뒤에는 실제 카탈로그의 온도·크기·수량·허용 옵션과 추가금을 한 화면에서 확인하고,
기본 옵션 그대로 담거나 원하는 옵션을 한 번에 선택할 수 있습니다. 담기·수량 변경·옵션
수정·삭제 결과와 사진·합계는 서버 검증 뒤 장바구니에 즉시 반영됩니다.

사진 메뉴판은 `data/moki_data.xlsx`의 **사진메뉴판** 시트에 임베드된 대표 이미지 33장을
`public/assets/menu/`로 추출해 표시합니다. 원본 엑셀이 바뀌면 `python scripts/extract_menu_images.py`를
실행해 웹 자산을 다시 만들 수 있습니다.

첫 접속에는 한옥 미닫이문 인트로 뒤 **한국어·English·中文·日本語** 선택 창이 먼저
표시되고, 선택한 언어로 화면과 이후 AI 대화가 바뀝니다. 상단에서 언제든 언어를 바꿀 수
있으며 대화·장바구니·좌석은 유지됩니다. **손쉬운 보기**에서는 큰 글자·고대비·큰 터치
버튼을 각각 켜거나 한 번에 적용할 수 있습니다.

언어 선택 뒤 필요한 경우 **OpenAI API 키 연결** 창이 표시됩니다. 웹 화면에서
입력한 키는 `localStorage`·쿠키·파일에 저장하지 않고 현재 페이지 메모리에만 둔 뒤, 대화 요청을
처리할 때 같은 출처의 서버 함수로만 전달합니다. 새로고침하거나 탭을 닫으면 키가 사라집니다.
공용 기기에서는 이 방식을 사용하지 마세요. 공개 배포에 공용 서버 키를 두는 경우에는 별도의
접근 통제와 사용량 제한이 필요합니다.

주류 메뉴명·별칭·도수·추천 같은 정보 질문은 직원 코드 없이 바로 답합니다. 실제 주류를
장바구니에 담거나 주문하려는 경우에만 “직원 확인이 필요한 내용입니다. 직원을 부르겠습니다.”라고
안내하고 직원 코드 입력창을 표시합니다. 시연용 직원 코드는 `1234`이며, 확인 후 보류한 구매 요청을
자동으로 다시 처리합니다.

주문 검토 화면에서는 매장/포장, 이용 방식에 맞는 컵, 포장 용품, 결제 표시 방식, 분할 방식,
영수증 방식을 선택할 수 있습니다. 이 흐름은 HTI 검증을 위한 **시연용 상태 처리**이며 실제 금융
결제·쿠폰 검증·포인트 적립·영수증 발행·매장 접수는 하지 않습니다. 성공 응답과 주문번호에도
같은 제한을 명시합니다.

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
api/index.py                   Vercel API·서명 상태·장바구니·시연 주문 마감
public/                        다국어·손쉬운 보기·사진 메뉴·옵션/장바구니 웹 UI
scripts/build_index.py         인덱스 생성
tests/test_logic.py            기존 가격·정책·검색 규칙 검사
tests/test_artifact_integration.py  새 산출물 연동 검사
tests/test_hti_regressions.py   사진·언어·좌석·장바구니·시연 주문 통합 검사
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
환경변수 또는 Streamlit Secrets에 `OPENAI_API_KEY`를 설정할 수 있습니다.
`.env`·실제 키·개인 정보가 든 로그는 Git에 올리지 않습니다.

Vercel에서는 `pyproject.toml`이 `api.index:app`을 FastAPI 진입점으로 지정하고, `public/`의
정적 웹 화면을 함께 제공합니다. 프로젝트 루트는 저장소 최상위로 두고 별도의 Build Command나
Output Directory를 지정하지 않습니다. `pyproject.toml`에는 서버리스 실행에 필요한 최소 패키지만,
`requirements.txt`에는 Streamlit·FAISS를 포함한 전체 로컬 개발 패키지를 둡니다. Project Settings →
Environment Variables에 다음 값을 등록한 뒤 재배포합니다. 웹 방문자가 첫 화면에서 자신의 키를
입력하는 구성에서는 `OPENAI_API_KEY`가 선택 사항입니다. 공개 배포에 서버 공용 키를 설정하면 모든
방문자가 그 키의 사용량을 소비할 수 있으므로 별도의 접근 통제와 사용량 제한을 함께 적용해야 합니다.

```text
OPENAI_API_KEY=실제 OpenAI API 키 (방문자 키 입력 방식에서는 선택)
MOKI_MOCK=0
MOKI_STATE_SECRET=32자 이상의 별도 무작위 상태 서명 비밀값
```

웹에서 입력한 `OPENAI_API_KEY`는 요청 동안만 사용되고 저장되지 않습니다. 서버 환경변수를 설정하면
브라우저 밖에서 호출하는 API 요청의 기본 키로도 사용할 수 있습니다. 별도의 매장 접속 비밀번호는
사용하지 않습니다. 시연용 직원 확인 코드는 `1234`로 고정되어 있습니다. `MOKI_STATE_SECRET`은
브라우저가 주문번호나 직원 확인 상태를 위조하지 못하도록 상태를 서명하므로, 코드와 별개인
32자 이상의 무작위 값으로 설정해야 합니다. 선택 설정인
`MOKI_OPENAI_TIMEOUT_SECONDS`와
`MOKI_OPENAI_MAX_RETRIES`의 기본값은 각각 15초와 1회입니다.

```bash
openssl rand -hex 32  # MOKI_STATE_SECRET 생성 예시
```

`/api/health`는 엑셀 메뉴 33개, RAG 문서 122개, 사진 33개와 AI 연결 상태를 반환합니다.
Vercel 함수는 읽기 전용 번들에서 실행되므로 검색은 JSONL 기반 서버리스 검색기를 사용하며,
기존 Streamlit 앱은 로컬 및 Streamlit Cloud에서 FAISS 인덱스를 계속 사용합니다.

한국어·영어 RAG 자료를 근거로 ko/en/zh/ja 화면과 응답, 좌석 1~12, 엑셀 대표 사진 33장,
메뉴 질문·옵션·실시간 장바구니와 시연 주문을 지원합니다. 현재 판매 원장은 S/L/ONE/PACK 및
추가 샷 0~2회만 정의하므로 HTI 예시의 XL·샷 3회는 임의 가격을 만들지 않고 제공하지 않습니다.
실제 결제·매장 접수·쿠폰 계정·포인트 계정·영수증 발행은 연결하지 않았습니다. 가격·영양·도수·
사진은 가상 매장 설정이며, 주류 구매는 시연용 직원 코드 확인 뒤에만 확정할 수 있습니다.

[검증 결과와 남은 일](docs/team/03_검증과_남은일.md) · [발표·시연 대본](docs/team/04_발표와_시연.md) · [최신 HTI](docs/team/HTI_원문기준과_시연대응.md)
