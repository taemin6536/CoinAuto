# 단순 이동평균 교차 전략 (SMA Crossover Strategy)

## 개요

단순 이동평균 교차 전략은 가장 기본적이고 널리 사용되는 기술적 분석 전략 중 하나입니다. 이 전략은 단기 이동평균선과 장기 이동평균선의 교차점을 이용하여 매수/매도 신호를 생성합니다.

## 전략 원리

### 매수 신호 (Golden Cross)
- 단기 이동평균선이 장기 이동평균선을 상향 돌파할 때
- 상승 추세의 시작을 의미
- 확인 기간(confirmation_periods) 동안 지속되어야 신호 생성

### 매도 신호 (Death Cross)
- 단기 이동평균선이 장기 이동평균선을 하향 돌파할 때
- 하락 추세의 시작을 의미
- 확인 기간 동안 지속되어야 신호 생성

## 설정 매개변수

### 기본 매개변수
```yaml
parameters:
  short_period: 10        # 단기 이동평균 기간 (기본: 10)
  long_period: 30         # 장기 이동평균 기간 (기본: 30)
  signal_threshold: 0.8   # 최소 신호 신뢰도 (기본: 0.8)
```

### 신호 확인
```yaml
buy_signal:
  confirmation_periods: 2  # 매수 신호 확인 기간
sell_signal:
  confirmation_periods: 2  # 매도 신호 확인 기간
```

### 리스크 관리
```yaml
risk:
  max_position_size: 0.15  # 최대 포지션 크기 (포트폴리오의 15%)
  stop_loss: 0.03         # 손절매 (3%)
  take_profit: 0.06       # 익절 (6%)
```

### 시장 조건
```yaml
markets:
  - "KRW-BTC"
  - "KRW-ETH"
  
evaluation_frequency: 300     # 평가 주기 (5분)
min_volume_threshold: 1000000 # 최소 거래량 (KRW)
```

## 신뢰도 계산

전략의 신뢰도는 다음 요소들을 고려하여 계산됩니다:

1. **이동평균선 분리도**: 단기/장기 이동평균선 간의 거리
2. **거래량 확인**: 최소 거래량 조건 충족 시 가산점
3. **추세 강도**: 최근 가격 움직임의 방향성

## 사용 예제

### 기본 설정으로 시작
```yaml
# config/strategies/sma_crossover.yaml
strategy:
  name: "sma_crossover"
  enabled: true

parameters:
  short_period: 10
  long_period: 30
  signal_threshold: 0.8
  
  markets:
    - "KRW-BTC"
```

### 보수적 설정 (장기 투자)
```yaml
parameters:
  short_period: 20
  long_period: 50
  signal_threshold: 0.9
  
  buy_signal:
    confirmation_periods: 3
  
  risk:
    max_position_size: 0.1
    stop_loss: 0.02
```

### 적극적 설정 (단기 투자)
```yaml
parameters:
  short_period: 5
  long_period: 15
  signal_threshold: 0.7
  
  buy_signal:
    confirmation_periods: 1
  
  risk:
    max_position_size: 0.2
    stop_loss: 0.05
```

## 장단점

### 장점
- 이해하기 쉽고 구현이 간단
- 강한 추세에서 효과적
- 잘못된 신호를 줄이는 확인 메커니즘

### 단점
- 횡보장에서 많은 거짓 신호 발생
- 지연된 신호 (추세 확인 후 진입)
- 급격한 시장 변화에 늦은 반응

## 최적화 팁

1. **시장 특성에 맞는 기간 설정**: 변동성이 높은 시장에서는 짧은 기간 사용
2. **거래량 조건 활용**: 거래량이 많을 때만 신호 생성하도록 설정
3. **다른 전략과 조합**: RSI 등 다른 지표와 함께 사용하여 신뢰도 향상
4. **백테스팅**: 과거 데이터로 매개변수 최적화

## 주의사항

- 이동평균 계산에 충분한 과거 데이터 필요
- 급격한 시장 변화 시 큰 손실 가능
- 수수료를 고려한 수익성 검토 필요
- 정기적인 성과 모니터링 및 매개변수 조정 권장