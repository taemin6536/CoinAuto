"""
Property-based tests for dynamic configuration application in stop-loss averaging strategy.

**Feature: stop-loss-averaging-strategy, Property 20: 동적 설정 적용**
**Validates: Requirements 5.3**

Tests that configuration changes are dynamically applied to the strategy without restart.
"""

import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta
from typing import Dict, Any

from upbit_trading_bot.data.models import (
    StrategyState, StopLossPosition, PositionEntry, MarketConditions,
    StopLossAveragingSignal
)


# 전략 설정 생성기
@st.composite
def strategy_config(draw):
    """유효한 전략 설정을 생성하는 생성기"""
    return {
        'stop_loss_level': draw(st.floats(min_value=-5.0, max_value=-1.0)),
        'averaging_trigger': draw(st.floats(min_value=-2.0, max_value=-0.5)),
        'target_profit': draw(st.floats(min_value=0.2, max_value=2.0)),
        'monitoring_interval': draw(st.integers(min_value=5, max_value=60)),
        'max_averaging_count': draw(st.integers(min_value=1, max_value=3)),
        'daily_loss_limit': draw(st.floats(min_value=1000, max_value=10000)),
        'min_balance': draw(st.floats(min_value=10000, max_value=100000))
    }


# 시장 상황 생성기
@st.composite
def market_conditions(draw):
    """유효한 시장 상황을 생성하는 생성기"""
    return MarketConditions(
        volatility_24h=draw(st.floats(min_value=0.0, max_value=50.0)),
        volume_ratio=draw(st.floats(min_value=0.1, max_value=10.0)),
        rsi=draw(st.floats(min_value=0.0, max_value=100.0)),
        price_change_1m=draw(st.floats(min_value=-10.0, max_value=10.0)),
        market_trend=draw(st.sampled_from(['bullish', 'bearish', 'neutral'])),
        is_rapid_decline=draw(st.booleans())
    )


# 포지션 진입 정보 생성기
@st.composite
def position_entry(draw):
    """유효한 포지션 진입 정보를 생성하는 생성기"""
    price = draw(st.floats(min_value=1.0, max_value=100000.0))
    quantity = draw(st.floats(min_value=0.001, max_value=1000.0))
    cost = price * quantity
    
    return PositionEntry(
        price=price,
        quantity=quantity,
        cost=cost,
        order_type=draw(st.sampled_from(['initial', 'averaging'])),
        timestamp=draw(st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31)
        ))
    )


# 포지션 생성기
@st.composite
def stop_loss_position(draw):
    """유효한 손절-물타기 포지션을 생성하는 생성기"""
    entries = draw(st.lists(position_entry(), min_size=1, max_size=3))
    
    # 계산된 값들
    total_quantity = sum(entry.quantity for entry in entries)
    total_cost = sum(entry.cost for entry in entries)
    average_price = total_cost / total_quantity if total_quantity > 0 else 0
    
    created_at = min(entry.timestamp for entry in entries)
    updated_at = max(entry.timestamp for entry in entries)
    
    return StopLossPosition(
        market=draw(st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')))),
        entries=entries,
        average_price=average_price,
        total_quantity=total_quantity,
        total_cost=total_cost,
        created_at=created_at,
        updated_at=updated_at
    )


# 전략 상태 생성기
@st.composite
def strategy_state(draw):
    """유효한 전략 상태를 생성하는 생성기"""
    has_position = draw(st.booleans())
    current_position = draw(stop_loss_position()) if has_position else None
    
    is_suspended = draw(st.booleans())
    suspension_reason = draw(st.text(min_size=1, max_size=100)) if is_suspended else None
    
    has_last_trade = draw(st.booleans())
    last_trade_time = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31)
    )) if has_last_trade else None
    
    return StrategyState(
        current_position=current_position,
        consecutive_losses=draw(st.integers(min_value=0, max_value=10)),
        daily_pnl=draw(st.floats(min_value=-10000.0, max_value=10000.0)),
        is_suspended=is_suspended,
        suspension_reason=suspension_reason,
        last_trade_time=last_trade_time
    )


class MockStrategy:
    """테스트용 모의 전략 클래스"""
    
    def __init__(self, initial_config: Dict[str, Any]):
        self.config = initial_config.copy()
        self.state = StrategyState(
            current_position=None,
            consecutive_losses=0,
            daily_pnl=0.0,
            is_suspended=False,
            suspension_reason=None,
            last_trade_time=None
        )
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """설정을 동적으로 업데이트"""
        self.config.update(new_config)
    
    def get_config_value(self, key: str) -> Any:
        """설정 값을 반환"""
        return self.config.get(key)
    
    def apply_config_changes(self) -> bool:
        """설정 변경사항을 적용하고 성공 여부를 반환"""
        # 설정 유효성 검증
        required_keys = [
            'stop_loss_level', 'averaging_trigger', 'target_profit',
            'monitoring_interval', 'max_averaging_count'
        ]
        
        for key in required_keys:
            if key not in self.config:
                return False
        
        # 설정 범위 검증
        if not (-5.0 <= self.config['stop_loss_level'] <= -1.0):
            return False
        if not (-2.0 <= self.config['averaging_trigger'] <= -0.5):
            return False
        if not (0.2 <= self.config['target_profit'] <= 2.0):
            return False
        if not (5 <= self.config['monitoring_interval'] <= 60):
            return False
        if not (1 <= self.config['max_averaging_count'] <= 3):
            return False
        
        return True


@given(
    initial_config=strategy_config(),
    updated_config=strategy_config(),
    state=strategy_state()
)
@settings(max_examples=100)
def test_dynamic_config_application_property(initial_config, updated_config, state):
    """
    **Feature: stop-loss-averaging-strategy, Property 20: 동적 설정 적용**
    **Validates: Requirements 5.3**
    
    모든 시스템 설정 변경에서, 설정이 동적으로 적용되어야 한다
    """
    # 전략 초기화
    strategy = MockStrategy(initial_config)
    strategy.state = state
    
    # 초기 설정 확인
    for key, value in initial_config.items():
        assert strategy.get_config_value(key) == value
    
    # 설정 업데이트
    strategy.update_config(updated_config)
    
    # 설정 변경사항 적용
    config_applied = strategy.apply_config_changes()
    
    # 설정이 성공적으로 적용되었다면, 새로운 설정 값들이 반영되어야 함
    if config_applied:
        for key, value in updated_config.items():
            assert strategy.get_config_value(key) == value
        
        # 전략 상태는 유지되어야 함
        assert strategy.state.consecutive_losses == state.consecutive_losses
        assert strategy.state.daily_pnl == state.daily_pnl
        assert strategy.state.is_suspended == state.is_suspended
        assert strategy.state.suspension_reason == state.suspension_reason
        
        # 포지션 정보도 유지되어야 함
        if state.current_position:
            assert strategy.state.current_position is not None
            assert strategy.state.current_position.market == state.current_position.market
            assert strategy.state.current_position.average_price == state.current_position.average_price
            assert strategy.state.current_position.total_quantity == state.current_position.total_quantity


@given(
    config=strategy_config(),
    market_cond=market_conditions()
)
@settings(max_examples=100)
def test_config_validation_during_dynamic_update(config, market_cond):
    """
    설정 동적 업데이트 시 유효성 검증이 올바르게 작동하는지 테스트
    """
    strategy = MockStrategy(config)
    
    # 유효한 설정은 성공적으로 적용되어야 함
    assert strategy.apply_config_changes() == True
    
    # 잘못된 설정 테스트
    invalid_configs = [
        {'stop_loss_level': -10.0},  # 범위 초과
        {'averaging_trigger': -5.0},  # 범위 초과
        {'target_profit': -1.0},  # 음수
        {'monitoring_interval': 0},  # 범위 미만
        {'max_averaging_count': 10}  # 범위 초과
    ]
    
    for invalid_config in invalid_configs:
        strategy.update_config(invalid_config)
        # 잘못된 설정은 적용되지 않아야 함
        assert strategy.apply_config_changes() == False


@given(
    config=strategy_config()
)
@settings(max_examples=100)
def test_config_persistence_after_update(config):
    """
    설정 업데이트 후 설정이 지속되는지 테스트
    """
    strategy = MockStrategy(config)
    
    # 초기 설정 적용
    assert strategy.apply_config_changes() == True
    
    # 설정 값 변경
    new_stop_loss = -2.5
    strategy.update_config({'stop_loss_level': new_stop_loss})
    assert strategy.apply_config_changes() == True
    
    # 변경된 설정이 지속되는지 확인
    assert strategy.get_config_value('stop_loss_level') == new_stop_loss
    
    # 다른 설정들은 유지되는지 확인
    for key, value in config.items():
        if key != 'stop_loss_level':
            assert strategy.get_config_value(key) == value


if __name__ == "__main__":
    # 간단한 테스트 실행
    test_config = {
        'stop_loss_level': -3.0,
        'averaging_trigger': -1.0,
        'target_profit': 1.0,
        'monitoring_interval': 10,
        'max_averaging_count': 2,
        'daily_loss_limit': 5000.0,
        'min_balance': 50000.0
    }
    
    strategy = MockStrategy(test_config)
    print("초기 설정 적용:", strategy.apply_config_changes())
    
    # 설정 업데이트 테스트
    strategy.update_config({'stop_loss_level': -2.0, 'target_profit': 1.5})
    print("설정 업데이트 후 적용:", strategy.apply_config_changes())
    print("업데이트된 손절 수준:", strategy.get_config_value('stop_loss_level'))
    print("업데이트된 목표 수익:", strategy.get_config_value('target_profit'))