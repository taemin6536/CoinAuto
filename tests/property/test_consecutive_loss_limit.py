"""
연속 손절 제한 속성 테스트.

**Feature: stop-loss-averaging-strategy, Property 9: 연속 손절 제한**
**검증: 요구사항 2.4**

모든 거래 시퀀스에서, 연속으로 3회 손절 발생 시 전략 실행이 일시 중단되어야 한다.
"""

import pytest
from hypothesis import given, strategies as st, assume
from datetime import datetime, timedelta
from typing import List

from upbit_trading_bot.strategy.risk_controller import RiskController, Trade


@st.composite
def trade_sequence_strategy(draw):
    """거래 시퀀스 생성 전략"""
    consecutive_loss_limit = draw(st.integers(min_value=1, max_value=10))
    
    # 거래 시퀀스 길이
    sequence_length = draw(st.integers(min_value=1, max_value=20))
    
    trades = []
    base_time = datetime.now() - timedelta(hours=sequence_length)
    
    for i in range(sequence_length):
        trade_time = base_time + timedelta(minutes=i * 10)
        
        # 손절 여부 결정
        is_stop_loss = draw(st.booleans())
        
        # PnL 생성 (손절이면 음수, 아니면 양수 또는 음수)
        if is_stop_loss:
            pnl = draw(st.floats(min_value=-10000.0, max_value=-100.0))
        else:
            pnl = draw(st.floats(min_value=-5000.0, max_value=10000.0))
        
        trade = Trade(
            market=draw(st.sampled_from(['KRW-BTC', 'KRW-ETH', 'KRW-ADA'])),
            side=draw(st.sampled_from(['buy', 'sell'])),
            price=draw(st.floats(min_value=1000.0, max_value=100000000.0)),
            quantity=draw(st.floats(min_value=0.001, max_value=10.0)),
            timestamp=trade_time,
            is_stop_loss=is_stop_loss,
            pnl=pnl
        )
        trades.append(trade)
    
    return {
        'consecutive_loss_limit': consecutive_loss_limit,
        'trades': trades
    }


@st.composite
def consecutive_loss_scenario_strategy(draw):
    """연속 손절 시나리오 생성 전략"""
    consecutive_loss_limit = draw(st.integers(min_value=2, max_value=5))
    
    # 시나리오 타입: 한도 내, 한도와 같음, 한도 초과
    scenario_type = draw(st.sampled_from(['within_limit', 'at_limit', 'exceeds_limit']))
    
    trades = []
    base_time = datetime.now() - timedelta(hours=10)
    
    if scenario_type == 'within_limit':
        # 연속 손절이 한도보다 적게
        consecutive_losses = draw(st.integers(min_value=0, max_value=consecutive_loss_limit - 1))
        
        # 연속 손절 생성
        for i in range(consecutive_losses):
            trade = Trade(
                market='KRW-BTC',
                side='sell',
                price=50000000.0,
                quantity=0.001,
                timestamp=base_time + timedelta(minutes=i * 10),
                is_stop_loss=True,
                pnl=-1000.0
            )
            trades.append(trade)
        
        # 마지막에 성공 거래 추가 (연속성 끊기)
        if consecutive_losses > 0:
            success_trade = Trade(
                market='KRW-BTC',
                side='sell',
                price=51000000.0,
                quantity=0.001,
                timestamp=base_time + timedelta(minutes=consecutive_losses * 10),
                is_stop_loss=False,
                pnl=500.0
            )
            trades.append(success_trade)
    
    elif scenario_type == 'at_limit':
        # 정확히 한도만큼 연속 손절
        for i in range(consecutive_loss_limit):
            trade = Trade(
                market='KRW-BTC',
                side='sell',
                price=50000000.0,
                quantity=0.001,
                timestamp=base_time + timedelta(minutes=i * 10),
                is_stop_loss=True,
                pnl=-1000.0
            )
            trades.append(trade)
    
    else:  # exceeds_limit
        # 한도를 초과하는 연속 손절
        consecutive_losses = consecutive_loss_limit + draw(st.integers(min_value=1, max_value=3))
        for i in range(consecutive_losses):
            trade = Trade(
                market='KRW-BTC',
                side='sell',
                price=50000000.0,
                quantity=0.001,
                timestamp=base_time + timedelta(minutes=i * 10),
                is_stop_loss=True,
                pnl=-1000.0
            )
            trades.append(trade)
    
    return {
        'consecutive_loss_limit': consecutive_loss_limit,
        'trades': trades,
        'scenario_type': scenario_type,
        'expected_result': scenario_type == 'within_limit'  # Only within_limit should return True
    }


class TestConsecutiveLossLimit:
    """연속 손절 제한 속성 테스트"""
    
    @given(consecutive_loss_scenario_strategy())
    def test_consecutive_loss_limit_enforcement(self, scenario):
        """
        **Feature: stop-loss-averaging-strategy, Property 9: 연속 손절 제한**
        **검증: 요구사항 2.4**
        
        모든 거래 시퀀스에서, 연속으로 3회 손절 발생 시 전략 실행이 일시 중단되어야 한다.
        """
        # Given: 리스크 컨트롤러와 거래 시퀀스
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': scenario['consecutive_loss_limit'],
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 연속 손절 제한을 확인
        result = risk_controller.check_consecutive_losses(scenario['trades'])
        
        # Then: 예상된 결과와 일치해야 함
        assert result == scenario['expected_result'], (
            f"연속 손절 제한 확인 실패: "
            f"시나리오 {scenario['scenario_type']}, "
            f"한도 {scenario['consecutive_loss_limit']}, "
            f"거래 수 {len(scenario['trades'])}, "
            f"예상 결과 {scenario['expected_result']}, "
            f"실제 결과 {result}"
        )
    
    @given(trade_sequence_strategy())
    def test_consecutive_loss_count_accuracy(self, scenario):
        """
        연속 손절 횟수 계산의 정확성 확인
        """
        # Given: 리스크 컨트롤러와 거래 시퀀스
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': scenario['consecutive_loss_limit'],
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # 거래 기록
        for trade in scenario['trades']:
            risk_controller.record_trade(trade)
        
        # When: 연속 손절 횟수를 계산
        consecutive_count = risk_controller.get_consecutive_loss_count()
        
        # Then: 실제 연속 손절 횟수와 일치해야 함
        expected_count = 0
        for trade in reversed(scenario['trades']):
            if trade.is_stop_loss:
                expected_count += 1
            else:
                break
        
        assert consecutive_count == expected_count, (
            f"연속 손절 횟수 계산 오류: 예상 {expected_count}, 실제 {consecutive_count}"
        )
    
    @given(st.integers(min_value=1, max_value=10))
    def test_empty_trade_history_no_consecutive_losses(self, consecutive_loss_limit):
        """
        거래 기록이 없는 경우 연속 손절이 없어야 함
        """
        # Given: 리스크 컨트롤러 (거래 기록 없음)
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': consecutive_loss_limit,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        # When: 연속 손절 제한을 확인
        result = risk_controller.check_consecutive_losses([])
        
        # Then: 항상 True여야 함
        assert result == True, "거래 기록이 없는 경우 연속 손절 제한에 걸리지 않아야 함"
        
        # And: 연속 손절 횟수는 0이어야 함
        consecutive_count = risk_controller.get_consecutive_loss_count()
        assert consecutive_count == 0, "거래 기록이 없는 경우 연속 손절 횟수는 0이어야 함"
    
    @given(st.integers(min_value=1, max_value=10))
    def test_single_success_trade_no_consecutive_losses(self, consecutive_loss_limit):
        """
        성공 거래만 있는 경우 연속 손절이 없어야 함
        """
        # Given: 리스크 컨트롤러와 성공 거래
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': consecutive_loss_limit,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        success_trade = Trade(
            market='KRW-BTC',
            side='sell',
            price=51000000.0,
            quantity=0.001,
            timestamp=datetime.now(),
            is_stop_loss=False,
            pnl=1000.0
        )
        
        # When: 연속 손절 제한을 확인
        result = risk_controller.check_consecutive_losses([success_trade])
        
        # Then: 항상 True여야 함
        assert result == True, "성공 거래만 있는 경우 연속 손절 제한에 걸리지 않아야 함"
    
    @given(st.integers(min_value=3, max_value=10))
    def test_mixed_trades_with_success_at_end(self, consecutive_loss_limit):
        """
        손절 후 성공 거래가 있는 경우 연속성이 끊어져야 함
        """
        # Given: 리스크 컨트롤러와 혼합 거래 (마지막이 성공)
        config = {
            'daily_loss_limit': 50000.0,
            'consecutive_loss_limit': consecutive_loss_limit,
            'min_balance_threshold': 10000.0
        }
        risk_controller = RiskController(config)
        
        trades = []
        base_time = datetime.now() - timedelta(hours=5)
        
        # 연속 손절 (한도보다 많지만 마지막에 성공 거래로 끊어짐)
        for i in range(consecutive_loss_limit + 1):
            trade = Trade(
                market='KRW-BTC',
                side='sell',
                price=50000000.0,
                quantity=0.001,
                timestamp=base_time + timedelta(minutes=i * 10),
                is_stop_loss=True,
                pnl=-1000.0
            )
            trades.append(trade)
        
        # 마지막에 성공 거래 추가
        success_trade = Trade(
            market='KRW-BTC',
            side='sell',
            price=51000000.0,
            quantity=0.001,
            timestamp=base_time + timedelta(minutes=(consecutive_loss_limit + 1) * 10),
            is_stop_loss=False,
            pnl=1000.0
        )
        trades.append(success_trade)
        
        # When: 연속 손절 제한을 확인
        result = risk_controller.check_consecutive_losses(trades)
        
        # Then: 성공 거래로 인해 연속성이 끊어져 True여야 함
        assert result == True, "마지막 성공 거래로 인해 연속 손절이 끊어져야 함"


if __name__ == "__main__":
    pytest.main([__file__])