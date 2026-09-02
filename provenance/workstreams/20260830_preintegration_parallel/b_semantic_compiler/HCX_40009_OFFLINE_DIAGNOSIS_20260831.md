# `40009` offline 진단 — 2026-08-31

상태: **진단 단계. 외부 호출 0회.** production 코드·Ontology·Registry·DB·
`IMPLEMENTATION_PLAN.md` 변경 없음. B는 `provisional / correction required` 유지.

## 1. 방법

`httpx.MockTransport`를 `ChatClovaX(http_client=...)`에 주입해 실제 adapter가 만드는 HTTP
body를 프로세스 안에서 캡처했다. API key는 테스트가 placeholder로 덮어쓴다. **header는
읽지도 저장하지도 않았고** URL과 JSON body만 기록했다. 네트워크로 나간 바이트는 없다.

SDK 버전: `langchain-naver 0.1.1`, `langchain-openai 1.6.0`, `openai 3.6.0`,
`langchain-core 1.6.1`, `httpx 0.28.1`.

## 2. 직렬화 경로 (코드 근거)

`.venv/Lib/site-packages/langchain_naver/chat_models.py`

| 사실 | 근거 |
|---|---|
| `ChatClovaX`는 `BaseChatOpenAI`를 상속하고 `openai.OpenAI` 클라이언트를 만든다 | `class ChatClovaX(BaseChatOpenAI)`, `validate_environment`의 `openai.OpenAI(**client_params)` |
| 기본 base URL은 OpenAI 호환 경로다 | `naver_api_base` 기본값 `https://clovastudio.stream.ntruss.com/v1/openai` |
| `max_completion_tokens`는 **필드 alias**다 | `max_tokens: Optional[int] = Field(default=None, alias="max_completion_tokens")` |
| 전송 시 이름이 하나로 정규화된다 | `_default_params`: `if "max_tokens" in params: params["max_completion_tokens"] = params.pop("max_tokens")` |
| `thinking={"effort": x}`는 **`reasoning_effort`로 변환된다** | `validate_environment`: `if self.thinking is not None and "effort" in self.thinking: self.reasoning_effort = self.thinking["effort"]` |
| body는 `messages + _default_params + kwargs`로 만들어 `chat.completions.create`에 전달된다 | `_get_request_payload`, `_generate` |
| 요청 ID는 header로만 붙는다 | `_generate`의 `extra_headers={"X-NCP-CLOVASTUDIO-REQUEST-ID": ...}` |

즉 `thinking.effort`와 `reasoning_effort`는 **같은 wire field로 수렴**하며, 둘을 동시에
보내거나 서로 충돌시키는 경로가 없다.

## 3. 실제 전송 body (민감정보 제거)

URL `POST https://clovastudio.stream.ntruss.com/v1/openai/chat/completions` (query 없음)

```json
{
  "model": "HCX-007",
  "max_completion_tokens": 8192,
  "reasoning_effort": "none",
  "stream": false,
  "tool_choice": {"type": "function", "function": {"name": "submit_semantic_query"}},
  "tools": [{"type": "function",
             "function": {"name": "...", "description": "...", "parameters": {...}}}],
  "messages": [ ... ]
}
```

`messages`와 `tools[0].function.parameters` 본문은 생략했다. header, API key, request ID는
캡처하지 않았다.

## 4. 확인 항목별 결과

"기대 형식" 열은 사용자가 제시한 점검 항목과 adapter가 구현한 OpenAI 호환 관례를 적은
것이다. 이번 세션에서 NCP 공식 문서를 조회해 대조하지는 않았다.

| 항목 | 기대 형식 | 실제 전송 | 판정 |
|---|---|---|---|
| endpoint | Tool 지원 OpenAI 호환 Chat Completions | `/v1/openai/chat/completions`, POST, query 없음 | **일치** |
| model | `HCX-007` | `"model": "HCX-007"` | **일치** |
| `max_completion_tokens=8192` 실제 전송 | 전송돼야 함 | `"max_completion_tokens": 8192` | **일치** |
| `max_tokens`와 동시 전송 금지 | 하나만 | `max_tokens` 키 **부재** | **일치** |
| `thinking.effort=none` 등가 전송 | thinking 비활성 지시 | `"reasoning_effort": "none"` (adapter가 `thinking.effort`를 이 필드로 변환) | **등가**. `thinking={"effort":"none"}`으로 만들어도 body가 동일함을 테스트로 확인 |
| `tools` 형식 | OpenAI function envelope | `[{"type":"function","function":{name,description,parameters}}]` | **일치** |
| 강제 `tool_choice` | 특정 function 강제 | `{"type":"function","function":{"name":"submit_semantic_query"}}`, `tools[0]`의 이름과 동일 | **일치** |

## 5. 0-A 선언과의 재직렬화 비교

0-A에서 provider failure 0/93이었던 `grouped_flat` **선언**을 현재 설치된 SDK로 다시
직렬화해 비교했다.

**중요한 전제.** 0-A 당시의 raw HTTP body는 보존돼 있지 않다. 따라서 이 표는 오늘의
adapter가 만든 두 객체를 비교한 것이며, 0-A 당시의 SDK 버전·클라이언트 설정·서비스 상태가
지금과 같았음을 보이지 않는다. 여기서 발견된 차이는 우리가 만든 차이지만, 차이가 없다는
사실이 당시 요청이 동일했다는 증거는 아니다.

| | 0-A 선언 재직렬화 | 1–3회차 거부 | 4회차 거부 |
|---|---|---|---|
| URL | `/v1/openai/chat/completions` | 동일 | 동일 |
| top-level key | `messages, model, reasoning_effort, stream, tool_choice, tools` | **완전 동일** | +`max_completion_tokens` |
| `model` | HCX-007 | HCX-007 | HCX-007 |
| `reasoning_effort` | `none` | `none` | `none` |
| `stream` | `false` | `false` | `false` |
| tool envelope | `type` + `function{name,description,parameters}` | 동일 | 동일 |
| `parameters` JSON Schema keyword 집합 | — | **0-A와 완전 동일 (차집합 양방향 0)** | 동일 |
| `parameters` byte | 2,186 | 3,975 | 3,975 |
| description 개수 / 총 byte | 3 / 576 | 19 / 2,167 | 19 / 2,167 |
| 최장 단일 description byte | 477 | 393 | 393 |
| property slot / distinct 이름 | 16 / 13 | 17 / 14 | 17 / 14 |
| 최대 object 깊이 | 2 | 2 | 2 |
| enum 수 | 4 | 4 | 4 |

**현재 SDK로 재구성하면 1–3회차 요청과 0-A 선언 요청은 top-level·envelope·JSON Schema
keyword가 같다.** `max_completion_tokens`는 4회차에만 있었고 1–3회차도 거부됐으므로 4회차
거부의 원인은 아니다.

## 6. 세 범주 판정

### (a) adapter 직렬화 문제 — **현재 SDK 재구성에서 차이 미발견**

배제가 아니다. 확인된 것은 다음이다. 현재 설치된 SDK(`langchain-naver 0.1.1`,
`langchain-openai 1.6.0`, `openai 3.6.0`)로 두 요청을 재구성했을 때 endpoint와 envelope의
차이가 발견되지 않았고, endpoint·model·tool envelope·강제 tool_choice·thinking 등가 전송·
토큰 한도 중복 없음이 모두 기대 형식과 일치했다.

확인되지 않은 것은 다음이다. 0-A 당시의 raw HTTP body가 보존되지 않았으므로, 당시의 SDK
버전·클라이언트 설정·서비스 상태까지 지금과 동일했다고 증명하지 못한다. adapter 직렬화
결함을 **지지하는 관측이 현재 없다**는 것이 이 절의 정확한 결론이다.

### (b) endpoint/API 종류 문제 — **지지 관측 없음**

같은 base URL·경로·method 표기로 0-A에서 tool call이 정상 emit된 기록이 있다. 경로가 tool
미지원 API 종류였다면 그때 emit이 불가능했을 것이다. 다만 (a)와 같은 이유로 당시 요청이
지금과 동일했다는 증명은 아니며, 서비스 측 라우팅이나 지원 범위가 그 뒤 달라졌을 가능성은
이 관측이 배제하지 못한다.

### (c) 남는 두 가설 — 현재 증거로 **분리 불가**

1. **Tool 선언 내용 가설.** 두 선언은 JSON Schema keyword 집합만 같을 뿐 그 밖의 거의 모든
   것이 다르다. 최소한 다음이 모두 다르다.
   - function name (`submit_semantic_query` vs `record_question_semantics`)
   - parameters byte(3,975 vs 2,186)와 description 총량(19개 2,167 byte vs 3개 576 byte)
   - property 이름과 개수(17 slot / 14 distinct vs 16 / 13)
   - enum 값(요구 종류·상태·role·detail_kind vs 요구 종류·상태·slot·operator)
   - 각 object의 `required` 배열
   - 각 description의 실제 내용
   - schema 내부 조합(어떤 property가 어느 object에 어떤 조건으로 묶이는가)

   따라서 "남은 차이는 크기뿐"이라고 말할 수 없다. 단순 크기 임계값 가설은 아래 근거로
   약화되지만, **특정 이름·특정 property·특정 enum 값·특정 description·특정 조합**은 어느
   것도 배제되지 않았다.
2. **provider/서비스 앱의 HCX-007 Tool 지원 가설.** 0-A 기록 자체가 2026-08-30 `nested`
   93회 중 24회 `40009`라는 **과거 일부 거부 기록**을 남겼다. 2026-08-31에는 서로 다른 선언
   4개에 대해 **현재 4/4 거부 관측**이 있다. 표본 4회이며 같은 선언의 반복 관측은 없다.

두 가설은 지금까지의 관측만으로 분리되지 않는다. 어느 쪽도 단독으로 확정하지 않는다.

다만 0-A 자체 데이터가 (1)의 **단순 크기 형태**를 약화시킨다. 같은 93회 실행에서 **더
작은** `nested`(parameters 2,012 byte)는 24회 거부됐고 **더 큰** `grouped_flat`(2,186 byte)은
0회 거부됐다. 크기 순서가 거부 여부를 예측하지 못한다. 이는 크기 축만 약화시킬 뿐, 위에
열거한 다른 축(이름·property·enum·required·description 내용·조합)에는 아무 말도 하지 않는다.

## 7. 현재 원인 순위 미결정

**두 가설 중 어느 쪽이 더 유력한지 현재 증거로 순위를 정할 수 없다.** (1) Tool 선언 내용
문제와 (2) provider/서비스 상태 문제는 지금까지의 관측으로 우열을 가릴 수 없으며, 이 문서는
어느 쪽도 "가장 가능성 높은 원인"으로 지목하지 않는다.

각 가설과 관련해 확인된 사실만 적는다.

| 관측 | (1) 선언 내용 가설에 대해 | (2) 서비스 상태 가설에 대해 |
|---|---|---|
| 서로 다른 4개 선언(keyword·이름·encoding이 각각 다름)이 모두 tool emit 이전에 같은 code로 거부 | 네 선언이 공유하는 다른 속성이 원인일 수 있으므로 반증이 아니다 | 선언과 무관한 원인과 양립한다 |
| 0-A 기록에 `40009`가 93회 중 24회 있었고(과거 일부 거부 기록), 2026-08-31에는 4회 관측이 모두 거부(현재 4/4 거부 관측) | 과거 일부 거부는 선언 내용만으로 설명되지 않는다 | 양립하지만, 표본 4회로는 현재 상태를 특정할 수 없다 |
| 0-A 안에서 더 작은 `nested`(2,012 byte)가 24회, 더 큰 `grouped_flat`(2,186 byte)이 0회 거부 | 선언 **크기** 축을 약화시킨다. 다른 축은 시험되지 않았다 | 같은 시점에 선언별로 결과가 갈렸다는 사실은 서비스 단독 설명과도 긴장 관계다 |

표본 크기가 작다는 점을 함께 기록한다. 2026-08-31 관측은 4회이며, 각 회차는 선언이 서로
다르므로 같은 선언의 반복 관측이 하나도 없다. 어느 가설도 배제되지 않았고 어느 가설도
확정되지 않았으며, 어느 한 번의 추가 호출로도 확정되지 않는다. 8절 참조.

## 8. 다음 외부 호출 1회 제안 (승인 전 실행 금지)

**control 호출**을 권고한다. 0-A에서 수용 기록이 있는 최소 선언을 현재 시점에 한 번
보내 보는 것이다.

### 해석 규칙 — 어느 결과도 확정하지 못한다

0-A에도 `40009`의 **과거 일부 거부 기록**(93회 중 24회)이 있다. 같은 선언이 어떤 때는
수용되고 어떤 때는 거부된 기록이 있으므로, 단일 관측은 다음까지만 말한다.

- **control 수용** → 현재 시점에 최소 선언이 **한 번 수용됐다**는 증거. 서비스가 정상이라는
  증명도, 우리 선언이 원인이라는 증명도 아니다.
- **control 거부** → 현재 시점에 최소 선언도 **거부됐다**는 증거. 서비스 문제라는 증명도,
  우리 선언이 무관하다는 증명도 아니다.

같은 선언이 회차에 따라 다른 결과를 낸 기록이 있는 이상 결국 반복 관측이 필요하며, 반복
호출 횟수는 사용자 승인 사항이다.
이 문서는 그것을 자동으로 승인하지 않는다.

### probe 준비 방식 — 기존 `HcxSemanticProvider.call` 경로를 쓰지 않는다

0-A probe 경로는 자체 prompt·payload·retry·view 빌더를 함께 들고 오므로 그것을 그대로 쓰면
tool 선언 외의 변수가 동시에 움직인다. 대신 현재 live harness를 기준으로 다음을 **모두
고정**하는 격리 probe를 offline으로 먼저 준비해야 한다.

- endpoint, model `HCX-007`, system/human message, `reasoning_effort="none"`,
  `max_completion_tokens=8192`, `max_retries=0`

바꾸는 것은 **`tools` 선언과 그에 종속된 `tool_choice` 이름 하나**뿐이며, 0-A grouped-flat
선언(`record_question_semantics`)으로 교체한다.

probe 구현과 live 호출 모두 **승인 전에는 하지 않는다.** 이번 작업에서는 준비도 하지 않았다.

### 그 뒤

control 결과가 무엇이든 서버 검증 계약, grouped-flat schema, parser, Runtime View는 바꾸지
않는다. 모델을 `HCX-005`로 바꾸는 것은 다른 변수이므로 같은 호출에 섞지 않으며 승인 없이
수행하지 않는다.

## 9. 이번 진단이 바꾸지 않은 것

grouped-flat schema, `parse_grouped_flat`, `SUBMISSION_SCHEMA`, parser, validator,
Runtime View, Registry, Ontology, DB, `IMPLEMENTATION_PLAN.md`. 미커밋 상태인
`max_completion_tokens=8192` 한 줄도 그대로 두었다.
