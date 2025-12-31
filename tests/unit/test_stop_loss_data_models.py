"""
Unit tests for stop-loss averaging strategy data models.

Tests Position, PositionEntry, MarketConditions, StopLossAveragingSignal validation and serialization.
Requirements: 5.1, 5.5
"""

import pytest
import json
from datetime import datetime, timedelta
from typing import Dict, Any

from upbit_trading_bot.data.models import (
    PositionEntry, StopLossPosition, MarketConditions,
    StopLossAveragingSignal, StrategyState
)


class TestPositionEntry:
    """PositionEntry 모델 테스트"""
    
    def test_valid_position_entry_creation(self):
        """유효한 포지션 진입 정보 생성 테스트"""
        timestamp = datetime.now()
        entry = PositionEntry(
            price=50000.0,
            quantity=0.1,
            cost=5000.0,
            order_type='initial',
            timestamp=timestamp
        )
        
        assert entry.price == 50000.0
        assert entry.quantity == 0.1
        assert entry.cost == 5000.0
        assert entry.order_type == 'initial'
        assert entry.timestamp == timestamp
        assert entry.validate() == True
    
    def test_position_entry_cost_validation(self):
        """포지션 진입 정보의 비용 계산 검증 테스트"""
        timestamp = datetime.now()
        
        # 올바른 비용 계산
        entry = PositionEntry(
            price=50000.0,
            quantity=0.1,
            cost=5000.0,  # 50000 * 0.1 = 5000
            order_type='initial',
            timestamp=timestamp
        )
        assert entry.validate() == True
        
        # 잘못된 비용 계산 (큰 차이)
        entry_invalid = PositionEntry(
            price=50000.0,
            quantity=0.1,
            cost=6000.0,  # 실제 비용과 1000원 차이
            order_type='initial',
            timestamp=timestamp
        )
        assert entry_invalid.validate() == False
    
    def test_position_entry_invalid_order_type(self):
        """잘못된 주문 타입 테스트"""
        timestamp = datetime.now()
        entry = PositionEntry(
            price=50000.0,
            quantity=0.1,
            cost=5000.0,
            order_type='invalid_type',
            timestamp=timestamp
        )
        assert entry.validate() == False
    
    def test_position_entry_serialization(self):
        """포지션 진입 정보 직렬화/역직렬화 테스트"""
        timestamp = datetime.now()
        original_entry = PositionEntry(
            price=50000.0,
            quantity=0.1,
            cost=5000.0,
            order_type='averaging',
            timestamp=timestamp
        )
        
        # 딕셔너리 변환
        entry_dict = original_entry.to_dict()
        assert entry_dict['price'] == 50000.0
        assert entry_dict['quantity'] == 0.1
        assert entry_dict['cost'] == 5000.0
        assert entry_dict['order_type'] == 'averaging'
        assert entry_dict['timestamp'] == timestamp.isoformat()
        
        # 딕셔너리에서 복원
        restored_entry = PositionEntry.from_dict(entry_dict)
        assert restored_entry.price == original_entry.price
        assert restored_entry.quantity == original_entry.quantity
        assert restored_entry.cost == original_entry.cost
        assert restored_entry.order_type == original_entry.order_type
        assert restored_entry.timestamp == original_entry.timestamp
        
        # JSON 직렬화/역직렬화
        json_str = original_entry.to_json()
        restored_from_json = PositionEntry.from_json(json_str)
        assert restored_from_json.price == original_entry.price
        assert restored_from_json.quantity == original_entry.quantity


class TestStopLossPosition:
    """StopLossPosition 모델 테스트"""
    
    def test_valid_position_creation(self):
        """유효한 포지션 생성 테스트"""
        timestamp = datetime.now()
        entries = [
            PositionEntry(50000.0, 0.1, 5000.0, 'initial', timestamp),
            PositionEntry(49000.0, 0.1, 4900.0, 'averaging', timestamp + timedelta(minutes=1))
        ]
        
        position = StopLossPosition(
            market='KRW-BTC',
            entries=entries,
            average_price=49500.0,  # (5000 + 4900) / (0.1 + 0.1) = 49500
            total_quantity=0.2,
            total_cost=9900.0,
            created_at=timestamp,
            updated_at=timestamp + timedelta(minutes=1)
        )
        
        assert position.validate() == True
        assert position.market == 'KRW-BTC'
        assert len(position.entries) == 2
        assert position.average_price == 49500.0
        assert position.total_quantity == 0.2
        assert position.total_cost == 9900.0
    
    def test_position_calculation_consistency(self):
        """포지션 계산 일관성 검증 테스트"""
        timestamp = datetime.now()
        entries = [
            PositionEntry(50000.0, 0.1, 5000.0, 'initial', timestamp),
            PositionEntry(48000.0, 0.05, 2400.0, 'averaging', timestamp + timedelta(minutes=1))
        ]
        
        # 잘못된 계산 값으로 포지션 생성
        position = StopLossPosition(
            market='KRW-BTC',
            entries=entries,
            average_price=50000.0,  # 잘못된 평균 가격
            total_quantity=0.2,     # 잘못된 총 수량
            total_cost=8000.0,      # 잘못된 총 비용
            created_at=timestamp,
            updated_at=timestamp + timedelta(minutes=1)
        )
        
        assert position.validate() == False
    
    def test_position_serialization(self):
        """포지션 직렬화/역직렬화 테스트"""
        timestamp = datetime.now()
        entries = [
            PositionEntry(50000.0, 0.1, 5000.0, 'initial', timestamp)
        ]
        
        original_position = StopLossPosition(
            market='KRW-BTC',
            entries=entries,
            average_price=50000.0,
            total_quantity=0.1,
            total_cost=5000.0,
            created_at=timestamp,
            updated_at=timestamp
        )
        
        # 딕셔너리 변환
        position_dict = original_position.to_dict()
        assert position_dict['market'] == 'KRW-BTC'
        assert len(position_dict['entries']) == 1
        assert position_dict['average_price'] == 50000.0
        
        # 딕셔너리에서 복원
        restored_position = StopLossPosition.from_dict(position_dict)
        assert restored_position.market == original_position.market
        assert len(restored_position.entries) == len(original_position.entries)
        assert restored_position.average_price == original_position.average_price
        assert restored_position.total_quantity == original_position.total_quantity
        
        # JSON 직렬화/역직렬화
        json_str = original_position.to_json()
        restored_from_json = StopLossPosition.from_json(json_str)
        assert restored_from_json.market == original_position.market
        assert restored_from_json.average_price == original_position.average_price


class TestMarketConditions:
    """MarketConditions 모델 테스트"""
    
    def test_valid_market_conditions_creation(self):
        """유효한 시장 상황 생성 테스트"""
        conditions = MarketConditions(
            volatility_24h=5.2,
            volume_ratio=1.8,
            rsi=35.5,
            price_change_1m=-0.5,
            market_trend='bearish',
            is_rapid_decline=False
        )
        
        assert conditions.validate() == True
        assert conditions.volatility_24h == 5.2
        assert conditions.volume_ratio == 1.8
        assert conditions.rsi == 35.5
        assert conditions.price_change_1m == -0.5
        assert conditions.market_trend == 'bearish'
        assert conditions.is_rapid_decline == False
    
    def test_market_conditions_rsi_validation(self):
        """RSI 범위 검증 테스트"""
        # 유효한 RSI 값
        conditions_valid = MarketConditions(
            volatility_24h=5.0,
            volume_ratio=1.5,
            rsi=50.0,
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        assert conditions_valid.validate() == True
        
        # 잘못된 RSI 값 (범위 초과)
        conditions_invalid = MarketConditions(
            volatility_24h=5.0,
            volume_ratio=1.5,
            rsi=150.0,  # RSI는 0-100 범위
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        assert conditions_invalid.validate() == False
    
    def test_market_conditions_trend_validation(self):
        """시장 트렌드 검증 테스트"""
        # 유효한 트렌드
        for trend in ['bullish', 'bearish', 'neutral']:
            conditions = MarketConditions(
                volatility_24h=5.0,
                volume_ratio=1.5,
                rsi=50.0,
                price_change_1m=0.0,
                market_trend=trend,
                is_rapid_decline=False
            )
            assert conditions.validate() == True
        
        # 잘못된 트렌드
        conditions_invalid = MarketConditions(
            volatility_24h=5.0,
            volume_ratio=1.5,
            rsi=50.0,
            price_change_1m=0.0,
            market_trend='invalid_trend',
            is_rapid_decline=False
        )
        assert conditions_invalid.validate() == False
    
    def test_market_conditions_serialization(self):
        """시장 상황 직렬화/역직렬화 테스트"""
        original_conditions = MarketConditions(
            volatility_24h=7.5,
            volume_ratio=2.3,
            rsi=25.8,
            price_change_1m=-1.2,
            market_trend='bearish',
            is_rapid_decline=True
        )
        
        # 딕셔너리 변환
        conditions_dict = original_conditions.to_dict()
        assert conditions_dict['volatility_24h'] == 7.5
        assert conditions_dict['volume_ratio'] == 2.3
        assert conditions_dict['rsi'] == 25.8
        assert conditions_dict['market_trend'] == 'bearish'
        assert conditions_dict['is_rapid_decline'] == True
        
        # 딕셔너리에서 복원
        restored_conditions = MarketConditions.from_dict(conditions_dict)
        assert restored_conditions.volatility_24h == original_conditions.volatility_24h
        assert restored_conditions.volume_ratio == original_conditions.volume_ratio
        assert restored_conditions.rsi == original_conditions.rsi
        assert restored_conditions.market_trend == original_conditions.market_trend
        assert restored_conditions.is_rapid_decline == original_conditions.is_rapid_decline


class TestStopLossAveragingSignal:
    """StopLossAveragingSignal 모델 테스트"""
    
    def test_valid_signal_creation(self):
        """유효한 손절-물타기 신호 생성 테스트"""
        timestamp = datetime.now()
        market_conditions = MarketConditions(
            volatility_24h=5.0,
            volume_ratio=1.5,
            rsi=30.0,
            price_change_1m=-0.8,
            market_trend='bearish',
            is_rapid_decline=False
        )
        
        signal = StopLossAveragingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.8,
            price=50000.0,
            volume=0.1,
            strategy_id='stop_loss_averaging',
            timestamp=timestamp,
            signal_reason='initial_buy',
            position_info=None,
            market_conditions=market_conditions,
            expected_pnl=None
        )
        
        assert signal.validate() == True
        assert signal.signal_reason == 'initial_buy'
        assert signal.market_conditions.rsi == 30.0
        assert signal.expected_pnl is None
    
    def test_signal_reason_validation(self):
        """신호 이유 검증 테스트"""
        timestamp = datetime.now()
        market_conditions = MarketConditions(
            volatility_24h=5.0,
            volume_ratio=1.5,
            rsi=50.0,
            price_change_1m=0.0,
            market_trend='neutral',
            is_rapid_decline=False
        )
        
        # 유효한 신호 이유들
        valid_reasons = ['initial_buy', 'averaging', 'partial_sell', 'stop_loss', 'trailing_stop']
        for reason in valid_reasons:
            signal = StopLossAveragingSignal(
                market='KRW-BTC',
                action='buy',
                confidence=0.7,
                price=50000.0,
                volume=0.1,
                strategy_id='stop_loss_averaging',
                timestamp=timestamp,
                signal_reason=reason,
                position_info=None,
                market_conditions=market_conditions,
                expected_pnl=None
            )
            assert signal.validate() == True
        
        # 잘못된 신호 이유
        signal_invalid = StopLossAveragingSignal(
            market='KRW-BTC',
            action='buy',
            confidence=0.7,
            price=50000.0,
            volume=0.1,
            strategy_id='stop_loss_averaging',
            timestamp=timestamp,
            signal_reason='invalid_reason',
            position_info=None,
            market_conditions=market_conditions,
            expected_pnl=None
        )
        assert signal_invalid.validate() == False
    
    def test_signal_serialization(self):
        """손절-물타기 신호 직렬화/역직렬화 테스트"""
        timestamp = datetime.now()
        market_conditions = MarketConditions(
            volatility_24h=8.2,
            volume_ratio=2.1,
            rsi=25.0,
            price_change_1m=-1.5,
            market_trend='bearish',
            is_rapid_decline=True
        )
        
        original_signal = StopLossAveragingSignal(
            market='KRW-ETH',
            action='sell',
            confidence=0.9,
            price=3000000.0,
            volume=0.5,
            strategy_id='stop_loss_averaging',
            timestamp=timestamp,
            signal_reason='stop_loss',
            position_info={'avg_price': 3100000.0, 'quantity': 0.5},
            market_conditions=market_conditions,
            expected_pnl=-50000.0
        )
        
        # 딕셔너리 변환
        signal_dict = original_signal.to_dict()
        assert signal_dict['signal_reason'] == 'stop_loss'
        assert signal_dict['position_info']['avg_price'] == 3100000.0
        assert signal_dict['market_conditions']['rsi'] == 25.0
        assert signal_dict['expected_pnl'] == -50000.0
        
        # 딕셔너리에서 복원
        restored_signal = StopLossAveragingSignal.from_dict(signal_dict)
        assert restored_signal.signal_reason == original_signal.signal_reason
        assert restored_signal.position_info == original_signal.position_info
        assert restored_signal.market_conditions.rsi == original_signal.market_conditions.rsi
        assert restored_signal.expected_pnl == original_signal.expected_pnl


class TestStrategyState:
    """StrategyState 모델 테스트"""
    
    def test_valid_strategy_state_creation(self):
        """유효한 전략 상태 생성 테스트"""
        timestamp = datetime.now()
        entry = PositionEntry(50000.0, 0.1, 5000.0, 'initial', timestamp)
        position = StopLossPosition(
            market='KRW-BTC',
            entries=[entry],
            average_price=50000.0,
            total_quantity=0.1,
            total_cost=5000.0,
            created_at=timestamp,
            updated_at=timestamp
        )
        
        state = StrategyState(
            current_position=position,
            consecutive_losses=2,
            daily_pnl=-1500.0,
            is_suspended=False,
            suspension_reason=None,
            last_trade_time=timestamp
        )
        
        assert state.validate() == True
        assert state.current_position is not None
        assert state.consecutive_losses == 2
        assert state.daily_pnl == -1500.0
        assert state.is_suspended == False
        assert state.suspension_reason is None
        assert state.last_trade_time == timestamp
    
    def test_strategy_state_without_position(self):
        """포지션이 없는 전략 상태 테스트"""
        state = StrategyState(
            current_position=None,
            consecutive_losses=0,
            daily_pnl=0.0,
            is_suspended=False,
            suspension_reason=None,
            last_trade_time=None
        )
        
        assert state.validate() == True
        assert state.current_position is None
        assert state.consecutive_losses == 0
        assert state.daily_pnl == 0.0
    
    def test_strategy_state_suspended(self):
        """중단된 전략 상태 테스트"""
        state = StrategyState(
            current_position=None,
            consecutive_losses=3,
            daily_pnl=-5000.0,
            is_suspended=True,
            suspension_reason='연속 손절 한도 초과',
            last_trade_time=datetime.now()
        )
        
        assert state.validate() == True
        assert state.is_suspended == True
        assert state.suspension_reason == '연속 손절 한도 초과'
        assert state.consecutive_losses == 3
    
    def test_strategy_state_serialization(self):
        """전략 상태 직렬화/역직렬화 테스트"""
        timestamp = datetime.now()
        
        original_state = StrategyState(
            current_position=None,
            consecutive_losses=1,
            daily_pnl=2500.0,
            is_suspended=False,
            suspension_reason=None,
            last_trade_time=timestamp
        )
        
        # 딕셔너리 변환
        state_dict = original_state.to_dict()
        assert state_dict['current_position'] is None
        assert state_dict['consecutive_losses'] == 1
        assert state_dict['daily_pnl'] == 2500.0
        assert state_dict['is_suspended'] == False
        assert state_dict['last_trade_time'] == timestamp.isoformat()
        
        # 딕셔너리에서 복원
        restored_state = StrategyState.from_dict(state_dict)
        assert restored_state.current_position == original_state.current_position
        assert restored_state.consecutive_losses == original_state.consecutive_losses
        assert restored_state.daily_pnl == original_state.daily_pnl
        assert restored_state.is_suspended == original_state.is_suspended
        assert restored_state.last_trade_time == original_state.last_trade_time


if __name__ == "__main__":
    # 간단한 테스트 실행
    print("PositionEntry 테스트...")
    test_entry = TestPositionEntry()
    test_entry.test_valid_position_entry_creation()
    test_entry.test_position_entry_serialization()
    print("✓ PositionEntry 테스트 통과")
    
    print("MarketConditions 테스트...")
    test_conditions = TestMarketConditions()
    test_conditions.test_valid_market_conditions_creation()
    test_conditions.test_market_conditions_serialization()
    print("✓ MarketConditions 테스트 통과")
    
    print("StrategyState 테스트...")
    test_state = TestStrategyState()
    test_state.test_valid_strategy_state_creation()
    test_state.test_strategy_state_serialization()
    print("✓ StrategyState 테스트 통과")
    
    print("모든 데이터 모델 테스트 완료!")