# 모키 커피바 — RAG 테이블 주문 키오스크

사용자가 테이블에서 글로 메뉴를 묻고 주문을 구성하는 **과제 시연용 앱**이다.
메뉴 지식은 검색하고, 판매 구성·옵션·수량·금액·주문 상태는 코드로 검증한다.

## 실행

Python 3.12에서 검증했다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock.txt
cp .env.example .env
# .env의 OPENAI_API_KEY를 본인에게 허용된 키로 설정
streamlit run app.py
```

배포 환경에서는 환경변수 또는 Streamlit Secrets에 OPENAI_API_KEY와 MOKI_PASSWORD를 설정한다.
비밀값은 제출물·Git·검증 로그에 포함하지 않는다. 공용 키를 사용하는 공개 배포에는 비밀번호를 설정한다.

```bash
MOKI_MOCK=1 streamlit run app.py
```

이 모드는 합성 응답과 가짜 벡터를 쓰는 **화면 시험 전용**이며, 실제 RAG/LLM 시연으로 제시하지 않는다.

## 기준과 범위

- [컨셉](docs/01_컨셉.md): 좌석 1~12, 매장 이용 기본, 가상 메뉴.
- [HTI](docs/02_HTI.md) · [발표용 20개 핵심 과업과 시연](docs/07_발표용_핵심과업과_시연.md): Google Drive 「박채원 HTI」 A~H 기준. 원문과 지원 조건을 구별한다.
- 데이터 v4: 메뉴 33·판매 구성 52·원두 3·옵션 6·정책 19. 원본 엑셀 값은 보존했다.
- 한국어·영어, 메뉴 탐색·추천·비교·성분 정보, 장바구니·수정·부분 분리·삭제·되돌리기·취소 확인.
- 최종 내역을 본 뒤 명시적으로 시연 확정. 확정 내역 보존, 추가 주문은 새 장바구니.
- 주류는 해당 손님의 직원 확인 대기까지 지원한다. 고객 체크나 대화로 승인하지 않는다.
- 실제 결제·접수·쿠폰·포인트·영수증·직원 호출·제조 상태는 미연동이다.

## 구조

입력 → 질의 재작성/복합 행동 분류(LLM) → 관련 문서 검색 → 상태·옵션·금액 검증 → 근거 응답/코드 결과.
모든 복합 변경은 복사본에서 확인하고 성공 뒤 한 번에 반영한다. 후속 조건 답변은 미완료 요청에 연결한다.

문서는 메뉴 33·원두 3·옵션 6·정책 19 = **61개**다. 한 메뉴의 가격·영양·한영 정보를 묶으며 평가 질문은 검색에 넣지 않는다.
짧은 검색 문장과 전체 답변 근거를 분리한다. 규칙 검색으로 필요한 문서를 먼저 확보하고 벡터 검색을 보완한다.

저장 인덱스는 데이터·문서·모델·파일 해시를 확인한다. 현재 검색 문장이 기존 벡터와 같아 재임베딩 없이 근거 메타데이터를 갱신했다. 파일이 바뀌면 인덱스 불일치를 명시적으로 알린다.

```bash
python scripts/validate_data.py
python -m unittest discover -s tests -p test_regressions.py -v
python tests/test_logic.py
# 실제 API를 쓰는 질문 실행
python tests/run_checks.py --ids Q04 Q09 R05
# 데이터/검색 문장을 바꿨을 때만 임베딩 비용을 쓰는 재생성
python scripts/build_index.py
```

## 검증 기록

[시험 결과](tests/results.md) · [데이터 검사](tests/data_validation.json) · [변경과 검토](docs/06_변경과_검증결과.md).

기존 67개 시험안은 원문 그대로 보존했다. 현재 HTI 번호 연결은 tests/fixtures/chaewon_case_map.csv를 사용한다.
실행 결과·사전 상태·검색 출처·응답·최종 상태와 수정 후 재시험을 분리해 저장했다. 한 번의 성공이 향후 모든 모델 응답을 보장하지 않는다.

## 프롬프트와 데이터 수정

- 최종 응대: prompts/system.txt (프롬프트팀 원안)
- 통합 재작성/분류: prompts/router.md
- 실행 출력 계약: prompts/runtime_schema.json
- 팀의 원래 전달 제안은 prompts/team_reference에 보존했다. 원안의 함수명을 그대로 노출하지 않고 실제 구현으로 연결했다.
- 데이터 변경 뒤 검사와 인덱스 갱신을 함께 한다. 저장 인덱스를 오래된 데이터와 섞지 않는다.

기존 팀 담당: 데이터 류성환·오승재 / 프롬프트 안나량·이주연 / 개발 박채원·신기훈.
이 수정본과 PR은 팀 검토용이며 운영 배포·팀 채택·과제 제출은 별도 상태다.
