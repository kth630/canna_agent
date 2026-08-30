# 이 실행은 판정에 사용하지 않는다

이 verification 실행은 시작된 뒤에 harness 결함이 발견돼 폐기했다.

- 결함: detail slot 어휘에 집계 함수(`aggregation`)가 없었고, `limit` 기대값이
  metric ref를 함께 적는 표현을 허용하지 않았다. 두 경우 모두 모델의 의미 판단이 아니라
  채점 어휘의 공백 때문에 실패로 집계된다.
- 조치: `aggregation` slot과 `optional_details`, wildcard ref 매칭을 추가한 뒤
  세 split을 모두 다시 실행했다.
- 이 디렉터리의 transcript와 summary는 읽지 않았고 계약·prompt·fixture 수정의 근거로
  사용하지 않았다. 따라서 재실행한 verification split은 여전히 처음 보는 질문이다.
- 기록 보존 원칙에 따라 삭제하지 않고 그대로 둔다.
