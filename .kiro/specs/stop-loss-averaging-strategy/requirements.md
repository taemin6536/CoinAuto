# 손절-물타기 스캘핑 전략 요구사항 문서

## 소개

업비트 거래봇에 손절과 물타기를 결합한 스캘핑 전략을 구현합니다. 이 전략은 -3% 손절선과 -1% 물타기 매수를 통해 리스크를 관리하면서, 수수료를 고려한 수익을 확보하는 것을 목표로 합니다. 짧은 주기로 시장을 모니터링하여 빠른 매매 결정을 내립니다.

## 용어 정의

- **Stop_Loss_Averaging_Strategy**: 손절과 물타기를 결합한 스캘핑 전략 클래스
- **Initial_Position**: 최초 매수 포지션
- **Averaging_Down**: 가격 하락 시 추가 매수하는 물타기 전략
- **Stop_Loss_Level**: 강제 손절 수준 (-3%)
- **Averaging_Trigger**: 물타기 매수 트리거 수준 (-1%)
- **Fee_Adjusted_Profit**: 수수료를 고려한 실제 수익
- **Position_Manager**: 포지션 상태 및 평균 단가 관리 컴포넌트
- **Market_Monitor**: 짧은 주기 시장 모니터링 시스템

## 요구사항

### 요구사항 1

**사용자 스토리:** 트레이더로서 손실을 제한하면서도 일시적인 하락에서 회복할 기회를 얻기 위해 손절과 물타기를 결합한 전략을 사용하고 싶습니다.

#### 승인 기준

1. WHEN 최초 매수 후 가격이 -1% 하락하면 THE Stop_Loss_Averaging_Strategy SHALL 동일한 금액으로 추가 매수를 실행한다
2. WHEN 포지션의 평균 손실이 -3%에 도달하면 THE Stop_Loss_Averaging_Strategy SHALL 모든 포지션을 즉시 손절 매도한다
3. WHEN 포지션이 수수료를 포함한 손익분기점을 넘어서면 THE Stop_Loss_Averaging_Strategy SHALL 매도 신호를 생성한다
4. WHEN 물타기 후 추가 하락이 발생하면 THE Stop_Loss_Averaging_Strategy SHALL 더 이상 추가 매수를 하지 않는다
5. WHEN 매도 완료 후 THE Stop_Loss_Averaging_Strategy SHALL 새로운 매수 기회를 탐색한다

### 요구사항 2

**사용자 스토리:** 시스템 관리자로서 수수료를 고려한 실제 수익을 확보하고 과도한 손실을 방지하고 싶습니다.

#### 승인 기준

1. WHEN 매도 신호를 생성할 때 THE Stop_Loss_Averaging_Strategy SHALL 업비트 수수료(0.05%)를 포함한 손익을 계산한다
2. WHEN 수익률을 계산할 때 THE Stop_Loss_Averaging_Strategy SHALL 매수 수수료와 매도 수수료를 모두 반영한다
3. WHEN 일일 누적 손실이 설정된 한도를 초과하면 THE Stop_Loss_Averaging_Strategy SHALL 당일 거래를 중단한다
4. WHEN 연속으로 3회 손절이 발생하면 THE Stop_Loss_Averaging_Strategy SHALL 전략 실행을 일시 중단한다
5. WHEN 계좌 잔고가 최소 거래 금액 미만이면 THE Stop_Loss_Averaging_Strategy SHALL 거래를 중단한다

### 요구사항 3

**사용자 스토리:** 개발자로서 짧은 주기로 시장을 모니터링하여 빠른 매매 결정을 내릴 수 있는 시스템을 구축하고 싶습니다.

#### 승인 기준

1. WHEN 시장 모니터링이 시작되면 THE Market_Monitor SHALL 10초마다 현재 가격을 확인한다
2. WHEN 가격 변동이 감지되면 THE Market_Monitor SHALL 1초 이내에 포지션 상태를 업데이트한다
3. WHEN 매수/매도 조건이 충족되면 THE Market_Monitor SHALL 즉시 주문을 실행한다
4. WHEN 네트워크 오류가 발생하면 THE Market_Monitor SHALL 3회까지 재시도한다
5. WHEN API 호출 한도에 근접하면 THE Market_Monitor SHALL 모니터링 주기를 자동 조정한다

### 요구사항 4

**사용자 스토리:** 트레이더로서 포지션 상태와 평균 단가를 정확하게 추적하여 올바른 매매 결정을 내리고 싶습니다.

#### 승인 기준

1. WHEN 최초 매수가 체결되면 THE Position_Manager SHALL 매수 가격과 수량을 기록한다
2. WHEN 물타기 매수가 체결되면 THE Position_Manager SHALL 평균 단가를 재계산한다
3. WHEN 부분 매도가 발생하면 THE Position_Manager SHALL 남은 포지션 수량을 업데이트한다
4. WHEN 모든 포지션이 청산되면 THE Position_Manager SHALL 포지션 상태를 초기화한다
5. WHEN 포지션 정보가 요청되면 THE Position_Manager SHALL 현재 평균 단가와 총 수량을 반환한다

### 요구사항 5

**사용자 스토리:** 시스템 아키텍트로서 기존 거래봇 시스템과 호환되면서도 독립적으로 작동하는 전략을 구현하고 싶습니다.

#### 승인 기준

1. WHEN 전략이 초기화되면 THE Stop_Loss_Averaging_Strategy SHALL 기존 TradingStrategy 인터페이스를 구현한다
2. WHEN 다른 전략과 동시 실행되면 THE Stop_Loss_Averaging_Strategy SHALL 독립적인 포지션을 관리한다
3. WHEN 시스템 설정이 변경되면 THE Stop_Loss_Averaging_Strategy SHALL 설정을 동적으로 적용한다
4. WHEN 전략이 중단되면 THE Stop_Loss_Averaging_Strategy SHALL 현재 포지션 상태를 안전하게 저장한다
5. WHEN 전략이 재시작되면 THE Stop_Loss_Averaging_Strategy SHALL 이전 포지션 상태를 복원한다

### 요구사항 6

**사용자 스토리:** 데이터 분석가로서 전략의 성과와 모든 거래 내역을 추적하고 분석할 수 있기를 원합니다.

#### 승인 기준

1. WHEN 매수 주문이 실행되면 THE Stop_Loss_Averaging_Strategy SHALL 주문 유형(최초/물타기)과 가격을 로깅한다
2. WHEN 매도 주문이 실행되면 THE Stop_Loss_Averaging_Strategy SHALL 매도 사유(수익실현/손절)와 수익률을 기록한다
3. WHEN 포지션 상태가 변경되면 THE Stop_Loss_Averaging_Strategy SHALL 변경 시점과 평균 단가를 저장한다
4. WHEN 일일 거래가 완료되면 THE Stop_Loss_Averaging_Strategy SHALL 일일 성과 보고서를 생성한다
5. WHEN 전략 실행 중 오류가 발생하면 THE Stop_Loss_Averaging_Strategy SHALL 오류 상세 정보를 로깅한다

### 요구사항 7

**사용자 스토리:** 트레이더로서 시장 상황에 따라 전략 파라미터를 조정할 수 있는 유연성을 원합니다.

#### 승인 기준

1. WHEN 손절 수준이 설정되면 THE Stop_Loss_Averaging_Strategy SHALL -1%에서 -5% 범위 내에서 손절선을 적용한다
2. WHEN 물타기 트리거가 설정되면 THE Stop_Loss_Averaging_Strategy SHALL -0.5%에서 -2% 범위 내에서 추가 매수를 실행한다
3. WHEN 목표 수익률이 설정되면 THE Stop_Loss_Averaging_Strategy SHALL 수수료 포함 0.2%에서 2% 범위의 수익을 목표로 한다
4. WHEN 모니터링 주기가 설정되면 THE Stop_Loss_Averaging_Strategy SHALL 5초에서 60초 범위에서 시장을 모니터링한다
5. WHEN 최대 물타기 횟수가 설정되면 THE Stop_Loss_Averaging_Strategy SHALL 1회에서 3회 범위에서 추가 매수를 제한한다

### 요구사항 8

**사용자 스토리:** 트레이더로서 변동성이 높은 코인에서 더 나은 수익 기회를 얻고, 안전한 진입 조건을 확보하고 싶습니다.

#### 승인 기준

1. WHEN 코인의 24시간 변동률이 5% 이상이면 THE Stop_Loss_Averaging_Strategy SHALL 해당 코인을 우선 거래 대상으로 선정한다
2. WHEN 거래량이 평균 거래량의 1.5배 이상이면 THE Stop_Loss_Averaging_Strategy SHALL 매수 신호 생성을 허용한다
3. WHEN 가격이 급락(-2% 이상)하고 있으면 THE Stop_Loss_Averaging_Strategy SHALL 매수 신호 생성을 일시 중단한다
4. WHEN RSI가 30 이하(과매도)이면 THE Stop_Loss_Averaging_Strategy SHALL 매수 신호의 신뢰도를 높인다
5. WHEN 시장 전체가 하락 추세(-3% 이상)이면 THE Stop_Loss_Averaging_Strategy SHALL 전략 실행을 일시 중단한다

### 요구사항 9

**사용자 스토리:** 트레이더로서 트레일링 스톱과 부분 매도를 통해 수익을 극대화하고 리스크를 최소화하고 싶습니다.

#### 승인 기준

1. WHEN 포지션이 목표 수익률의 50%에 도달하면 THE Stop_Loss_Averaging_Strategy SHALL 포지션의 30%를 부분 매도한다
2. WHEN 포지션이 목표 수익률에 도달하면 THE Stop_Loss_Averaging_Strategy SHALL 포지션의 50%를 추가 매도한다
3. WHEN 포지션이 목표 수익률의 150%에 도달하면 THE Stop_Loss_Averaging_Strategy SHALL 트레일링 스톱을 활성화한다
4. WHEN 트레일링 스톱이 활성화되면 THE Stop_Loss_Averaging_Strategy SHALL 최고점 대비 -1% 하락 시 남은 포지션을 매도한다
5. WHEN 부분 매도가 완료되면 THE Stop_Loss_Averaging_Strategy SHALL 남은 포지션의 손절선을 손익분기점으로 조정한다