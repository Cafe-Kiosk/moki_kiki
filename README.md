# 모키 커피바 — RAG 테이블 주문 키오스크

AI응용 실습문제(RAG) · 4조. 손님이 테이블에서 **글로** 메뉴를 묻고 주문하는 과제 시연용 앱입니다.
메뉴 사실은 검색하고, 가격과 주문 상태는 코드로 처리합니다.

## 팀원은 여기부터 읽어주세요

**[팀원용 통합 안내 — 2026-10-15](docs/team/README.md)**

컨셉부터 데이터·HTI·개발·프롬프트·발표까지의 전체 과정, 역할별 인수인계,
실행 방법, 검증의 범위, 남은 일, 최신 16장 발표 PDF·PPT를 모았습니다.

| 버전 | 현재 상태 | 확인할 곳 |
|---|---|---|
| `main`의 앱 | 기존 팀 개발본. 이 문서 업로드는 앱 코드를 변경하지 않음 | `app.py`, `src/` |
| 수정 후보 `bb5b0a2` | [PR #1](https://github.com/Cafe-Kiosk/moki_kiki/pull/1), 10월 15일 확인 당시 OPEN/DRAFT/미병합 | `codex/complete-moki-order-flow` |
| 최신 발표 | 16장, 수정 후보로 수행한 시연을 설명 | [PDF](docs/team/presentation/팀과제_4조_모키커피바.pdf) · [PPT](docs/team/presentation/모키_커피바_최종발표.pptx) |

발표 자료가 업로드되었다고 수정 후보가 `main`에 병합되거나 팀 공유앱에 배포된 것은 아닙니다.

## 기존 main 앱 실행

```bash
git clone https://github.com/Cafe-Kiosk/moki_kiki.git
cd moki_kiki
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# .env에서 OPENAI_API_KEY를 본인에게 허용된 값으로 설정
python -m streamlit run app.py
```

Python 3.12는 수정 후보의 기존 검증 환경입니다. 이번 문서 작업에서 새 환경 설치는 재시험하지 않았습니다.
최신 발표와 같은 프로그램을 실행하려면 [수정 후보 실행 절차](docs/team/02_실행과_역할별_인수인계.md)를 따르세요.

```bash
MOKI_MOCK=1 python -m streamlit run app.py
```

MOCK는 합성 응답·가짜 벡터를 사용하는 화면 시험 모드입니다. 실제 RAG/LLM 시연 근거로 사용하지 않습니다.
저장 인덱스가 포함되어 있으므로 데이터와 검색 문서를 바꾸지 않았다면 다시 만들 필요가 없습니다.
변경한 경우 관련 검증을 먼저 하고 `python scripts/build_index.py`로 갱신합니다. 재생성에는 임베딩 비용이 듭니다.

## 구조와 담당

```text
입력 → 요청 해석(LLM) → 관련 자료 검색 → 응답 생성(LLM)
                         ↘ 옵션·가격·장바구니·주문 상태(코드)
```

| 담당 | 기존 팀 담당자 | 수정 위치 |
|---|---|---|
| 데이터 | 류성환 · 오승재 | `data/moki_data.xlsx` → 문서 생성·검색 인덱스와 함께 검증 |
| 프롬프트 | 안나량 · 이주연 | main: `prompts/*.md`; 수정 후보: `system.txt`·`router.md`·실행 스키마 |
| 개발 | 박채원 · 신기훈 | `app.py`, `src/`, `tests/` |

데이터는 메뉴 33·판매 구성 52·원두 정보 3·옵션 6·정책 19입니다.
앱은 엑셀에서 61개 문서를 만들며, [데이터팀 전달 JSONL](docs/team/data/rag_documents.jsonl)은 한영 각 61개로 총 122개입니다.
전달 JSONL은 참고용이며 현재 앱의 직접 적재 경로는 엑셀입니다.

## 공유 실행과 제한

Streamlit Cloud에서는 저장소 `Cafe-Kiosk/moki_kiki`, 선택한 브랜치, 진입 파일 `app.py`를 지정합니다.
환경변수 또는 Streamlit Secrets에 `OPENAI_API_KEY`와 `MOKI_PASSWORD`를 설정합니다.
`.env`·실제 키·비밀번호·개인 정보가 든 로그는 Git에 올리지 않습니다. 공개 앱은 접근 비밀번호를 설정합니다.

한국어·영어, 좌석 1~12, 메뉴 질문과 시연 주문을 지원하는 가상 서비스입니다.
실제 결제·매장 접수·직원 인증·쿠폰·포인트·영수증은 연결하지 않았습니다.
가격·영양·도수·사진은 가상 매장 설정입니다. 주류는 직원 확인 대기까지만 설명합니다.

[검증 결과와 남은 일](docs/team/03_검증과_남은일.md) · [발표·시연 대본](docs/team/04_발표와_시연.md) · [최신 HTI](docs/team/HTI_원문기준과_시연대응.md)
