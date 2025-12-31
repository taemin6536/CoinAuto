# RSI 모멘텀 전략 (RSI Momentum Strategy)

## 개요

RSI(Relative Strength Index) 모멘텀 전략은 상대강도지수를 이용하여 과매수/과매도 구간을 식별하고, 이를 바탕으로 매수/매도 신호를 생성하는 전략입니다. RSI는 0-100 사이의 값을 가지며, 일반적으로 30 이하는 과매도, 70 이상은 과매수로 판단합니다.

## 전략 원리

### RSI 계산
RSI = 100 - (100 / (1 + RS))
- RS = 평균 상승폭 / 평균 하락폭
- 일정 기간(기본 14일) 동안의 가격 변화를 분석

### 매수 신호
- RSI < 과매도 임계값 (기본: 30)
- 추가 필터 조건:
  - 거래량이 평균의 1.5배 이상
  - 가격이 급격히 하락하지 않음 (-2% 이상)

### 매도 신호
- RSI > 과매수 임계값 (기본: 70)
- 추가 필터 조건:
  - 거래량이 평균의 1.2배 이상

## 설정 매개변수

### 기본 매개변수
```yaml
parameters:
  rsi_period: 14              # RSI 계산 기간
  oversold_threshold: 30      # 과매도 임계값
  overbought_threshold: 70    # 과매수 임계값
  signal_threshold: 0.75      # 최소 신호 신뢰도
```

### 신호 조건
```yaml
buy_signal:
  condition: "rsi < oversold_threshold"
  additional_filters:
    - "volume > avg_volume * 1.5"  # 거래량 확인
    - "price_change > -0.02"       # 급락 방지

sell_signal:
  condition: "rsi > overbought_threshold"
  additional_filters:
    - "volume > avg_volume * 1.2"
```

### 리스크 관리
```yaml
risk:
  max_position_size: 0.1      # 최대 포지션 크기 (10%)
  stop_loss: 0.04            # 손절매 (4%)
  take_profit: 0.08          # 익절 (8%)
  trailing_stop: true        # 트레일링 스톱 사용
  trailing_stop_percentage: 0.02  # 트레일링 스톱 비율 (2%)
```

### 기술적 지표
```yaml
indicators:
  volume_sma_period: 20      # 거래량 이동평균 기간
  price_sma_period: 50       # 가격 이동평균 기간
```

## 신뢰도 계산

전략의 신뢰도는 다음 요소들을 고려하여 계산됩니다:

1. **RSI 극값 정도**: 더 극단적인 RSI 값일수록 높은 신뢰도
2. **거래량 확인**: 평균 거래량 대비 현재 거래량 비율
3. **가격 변화 확인**: 매수 신호 시 급락 여부 확인

## 사용 예제

### 기본 설정
```yaml
# config/strategies/rsi_momentum.yaml
strategy:
  name: "rsi_momentum"
  enabled: true

parameters:
  rsi_period: 14
  oversold_threshold: 30
  overbought_threshold: 70
  signal_threshold: 0.75
  
  markets:
    - "KRW-BTC"
    - "KRW-ETH"
```

### 보수적 설정 (안전 중심)
```yaml
parameters:
  rsi_period: 21
  oversold_threshold: 25      # 더 극단적인 과매도
  overbought_threshold: 75    # 더 극단적인 과매수
  signal_threshold: 0.85      # 높은 신뢰도 요구
  
  risk:
    max_position_size: 0.05   # 작은 포지션
    stop_loss: 0.03          # 타이트한 손절매
```

### 적극적 설정 (수익 중심)
```yaml
parameters:
  rsi_period: 10
  oversold_threshold: 35      # 덜 극단적인 조건
  overbought_threshold: 65
  signal_threshold: 0.65      # 낮은 신뢰도 허용
  
  risk:
    max_position_size: 0.15   # 큰 포지션
    take_profit: 0.12        # 높은 익절 목표
```

### 단기 트레이딩 설정
```yaml
parameters:
  rsi_period: 7
  evaluation_frequency: 60    # 1분마다 평가
  
  buy_signal:
    additional_filters:
      - "volume > avg_volume * 2.0"  # 더 높은 거래량 요구
      
  risk:
    trailing_stop: true
    trailing_stop_percentage: 0.015  # 1.5% 트레일링
```

## 장단점

### 장점
- 과매수/과매도 구간에서 효과적인 역추세 전략
- 명확한 진입/청산 신호
- 다양한 시장 조건에서 활용 가능
- 트레일링 스톱으로 수익 보호

### 단점
- 강한 추세 시장에서 조기 진입/청산
- 횡보장에서 많은 거짓 신호
- 단독 사용 시 한계, 다른 지표와 조합 필요

## 최적화 팁

1. **RSI 기간 조정**: 
   - 짧은 기간(7-10): 민감한 신호, 단기 트레이딩
   - 긴 기간(21-28): 안정적인 신호, 장기 투자

2. **임계값 조정**:
   - 변동성 높은 시장: 25/75 (더 극단적)
   - 변동성 낮은 시장: 35/65 (덜 극단적)

3. **추가 필터 활용**:
   - 거래량 조건으로 신호 품질 향상
   - 가격 변화율로 급등락 구간 회피

4. **다른 전략과 조합**:
   - SMA와 함께 사용하여 추세 확인
   - 볼린저 밴드로 변동성 고려

## 백테스팅 가이드

### 성과 지표
- 승률 (Win Rate)
- 평균 수익률
- 최대 손실 (Maximum Drawdown)
- 샤프 비율 (Sharpe Ratio)

### 최적화 매개변수
```python
# 백테스팅용 매개변수 범위
rsi_periods = [7, 10, 14, 21, 28]
oversold_levels = [20, 25, 30, 35]
overbought_levels = [65, 70, 75, 80]
signal_thresholds = [0.6, 0.7, 0.75, 0.8, 0.85]
```

## 주의사항

- RSI는 지연 지표이므로 급격한 시장 변화에 늦은 반응
- 강한 추세 시장에서는 오랫동안 극값 유지 가능
- 거래량과 함께 분석하여 신호의 신뢰성 확인 필요
- 정기적인 매개변수 재조정 권장
- 수수료와 슬리피지를 고려한 실제 수익성 검토 필수