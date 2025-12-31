"""
Stop-Loss Averaging Strategy Implementation

This module implements the StopLossAveragingStrategy class that combines stop-loss
and dollar-cost averaging (DCA) techniques for scalping trading. The strategy uses
-3% stop-loss and -1% averaging triggers to manage risk while capturing profits
from short-term price movements.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from .base import TradingStrategy, MarketData, StrategyEvaluationError
from .market_analyzer import MarketAnalyzer
from .position_manager import PositionManager
from .risk_controller import RiskController, Trade
from .partial_sell_manager import PartialSellManager
from .trailing_stop_manager import TrailingStopManager
from ..data.models import (
    StopLossAveragingSignal, 
    MarketConditions, 
    StrategyState,
    StopLossPosition
)


logger = logging.getLogger(__name__)


class StopLossAveragingStrategy(TradingStrategy):
    """
    손절-물타기 스캘핑 전략 메인 클래스
    
    -3% 손절선과 -1% 물타기 매수를 통해 리스크를 관리하면서
    수수료를 고려한 실질적인 수익을 확보하는 스캘핑 전략입니다.
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        """
        손절-물타기 전략 초기화
        
        Args:
            strategy_id: 전략 고유 식별자
            config: 전략 설정
        """
        super().__init__(strategy_id, config)
        
        # 전략 파라미터 추출
        params = config.get('parameters', {})
        
        # 손절 및 물타기 설정
        self.stop_loss_level = params.get('stop_loss_level', -3.0)  # -3%
        self.averaging_trigger = params.get('averaging_trigger', -1.0)  # -1%
        self.target_profit = params.get('target_profit', 0.5)  # 0.5%
        self.max_averaging_count = params.get('max_averaging_count', 1)  # 최대 1회 물타기
        
        # 수수료 설정
        self.trading_fee = params.get('trading_fee', 0.0005)  # 0.05%
        
        # 모니터링 설정
        self.monitoring_interval = params.get('monitoring_interval', 10)  # 10초
        
        # 컴포넌트 초기화
        self.market_analyzer = MarketAnalyzer(params.get('market_analyzer', {}))
        self.position_manager = PositionManager()
        self.risk_controller = RiskController(params.get('risk_controller', {}))
        self.partial_sell_manager = PartialSellManager(self.target_profit)
        self.trailing_stop_manager = TrailingStopManager(
            activation_profit=self.target_profit * 1.5,  # 목표 수익률의 150%에서 활성화
            trail_percentage=1.0  # 1% 트레일링
        )
        
        # 전략 상태
        self.strategy_state = StrategyState(
            current_position=None,
            consecutive_losses=0,
            daily_pnl=0.0,
            is_suspended=False,
            suspension_reason=None,
            last_trade_time=None
        )
        
        # 설정 검증
        self._validate_config()
        
        logger.info(f"StopLossAveragingStrategy initialized: {strategy_id}")
        logger.info(f"Parameters: stop_loss={self.stop_loss_level}%, "
                   f"averaging_trigger={self.averaging_trigger}%, "
                   f"target_profit={self.target_profit}%")
    
    def _validate_config(self) -> None:
        """전략 설정 검증"""
        if not (-5.0 <= self.stop_loss_level <= -1.0):
            raise StrategyEvaluationError(
                f"Stop loss level ({self.stop_loss_level}) must be between -5% and -1%"
            )
        
        if not (-2.0 <= self.averaging_trigger <= -0.5):
            raise StrategyEvaluationError(
                f"Averaging trigger ({self.averaging_trigger}) must be between -2% and -0.5%"
            )
        
        if not (0.2 <= self.target_profit <= 2.0):
            raise StrategyEvaluationError(
                f"Target profit ({self.target_profit}) must be between 0.2% and 2%"
            )
        
        if not (1 <= self.max_averaging_count <= 3):
            raise StrategyEvaluationError(
                f"Max averaging count ({self.max_averaging_count}) must be between 1 and 3"
            )
        
        if not (5 <= self.monitoring_interval <= 60):
            raise StrategyEvaluationError(
                f"Monitoring interval ({self.monitoring_interval}) must be between 5 and 60 seconds"
            )
    
    def get_required_history_length(self) -> int:
        """필요한 히스토리 길이 반환"""
        return 50  # RSI 계산 및 시장 분석을 위한 충분한 데이터
    
    def evaluate(self, market_data: MarketData) -> Optional[StopLossAveragingSignal]:
        """
        시장 데이터를 평가하고 거래 신호를 생성합니다.
        
        Args:
            market_data: 현재 시장 데이터
            
        Returns:
            Optional[StopLossAveragingSignal]: 거래 신호 (조건 미충족 시 None)
        """
        try:
            self.last_evaluation = datetime.now()
            
            # 기본 평가 조건 확인
            if not self.can_evaluate(market_data):
                return None
            
            # 전략 중단 상태 확인
            if self.strategy_state.is_suspended:
                logger.debug(f"Strategy suspended: {self.strategy_state.suspension_reason}")
                return None
            
            current_price = market_data.current_ticker.trade_price
            market = market_data.current_ticker.market
            
            # 현재 포지션 확인 - 손절은 최우선으로 처리
            current_position = self.position_manager.get_position(market)
            
            if current_position is not None:
                # 포지션이 있는 경우 - 손절 조건을 먼저 확인 (시장 조건과 무관하게)
                pnl_info = self._calculate_position_pnl(current_price, current_position)
                if pnl_info and self._should_stop_loss(pnl_info['pnl_rate']):
                    # 손절 조건 충족 시 즉시 손절 신호 생성 (시장 조건 무시)
                    market_conditions = self.market_analyzer.analyze_market_conditions(market_data)
                    return self._generate_stop_loss_signal(market_data, market_conditions, current_position, pnl_info)
            
            # 시장 상황 분석
            market_conditions = self.market_analyzer.analyze_market_conditions(market_data)
            
            # 전략 중단 조건 확인 (손절이 아닌 경우에만)
            if self.market_analyzer.should_suspend_strategy(market_conditions):
                self._suspend_strategy("Market conditions unfavorable")
                return None
            
            if current_position is None:
                # 포지션이 없는 경우 - 진입 조건 확인
                return self._check_entry_conditions(market_data, market_conditions)
            else:
                # 포지션이 있는 경우 - 매도/물타기 조건 확인 (손절은 이미 위에서 처리됨)
                return self._check_exit_or_averaging_conditions(
                    market_data, market_conditions, current_position, current_price
                )
                
        except Exception as e:
            logger.error(f"Strategy evaluation failed: {str(e)}")
            raise StrategyEvaluationError(f"Strategy evaluation failed: {str(e)}") from e
    
    def _check_entry_conditions(self, market_data: MarketData, 
                               market_conditions: MarketConditions) -> Optional[StopLossAveragingSignal]:
        """진입 조건 확인"""
        # 시장 분석기를 통한 진입 조건 확인
        if not self.market_analyzer.should_allow_buy_signal(market_conditions):
            return None
        
        # 변동성 기반 코인 선정 조건 확인
        if not self.market_analyzer.should_select_high_volatility_coin(market_conditions):
            return None
        
        # 리스크 컨트롤러를 통한 추가 검증
        market_conditions_dict = {
            'daily_loss': self.strategy_state.daily_pnl,
            'balance': 100000.0,  # 실제 구현에서는 계좌 잔고 조회
            'min_order_amount': 5000.0
        }
        
        if self.risk_controller.should_suspend_strategy(market_conditions_dict):
            self._suspend_strategy("Risk limits exceeded")
            return None
        
        # 매수 신호 생성
        current_price = market_data.current_ticker.trade_price
        confidence = self.market_analyzer.get_buy_signal_confidence(market_conditions)
        
        return StopLossAveragingSignal(
            market=market_data.current_ticker.market,
            action='buy',
            confidence=confidence,
            price=current_price,
            volume=0.1,  # 실제 구현에서는 동적 계산
            strategy_id=self.strategy_id,
            timestamp=datetime.now(),
            signal_reason='initial_buy',
            position_info=None,
            market_conditions=market_conditions,
            expected_pnl=None
        )
    
    def _check_exit_or_averaging_conditions(self, market_data: MarketData,
                                          market_conditions: MarketConditions,
                                          position: StopLossPosition,
                                          current_price: float) -> Optional[StopLossAveragingSignal]:
        """매도 또는 물타기 조건 확인 (손절은 이미 상위에서 처리됨)"""
        # 현재 손익 계산 (수수료 포함)
        pnl_info = self._calculate_position_pnl(current_price, position)
        if not pnl_info:
            return None
        
        current_pnl_percent = pnl_info['pnl_rate']
        
        # 1. 트레일링 스톱 확인
        trailing_signal = self._check_trailing_stop(market_data, market_conditions, position, 
                                                   current_price, current_pnl_percent)
        if trailing_signal:
            return trailing_signal
        
        # 2. 부분 매도 조건 확인
        partial_sell_signal = self._check_partial_sell(market_data, market_conditions, position, 
                                                      current_pnl_percent, pnl_info)
        if partial_sell_signal:
            return partial_sell_signal
        
        # 3. 수익 실현 조건 확인
        if self._should_take_profit(current_pnl_percent):
            return self._generate_take_profit_signal(market_data, market_conditions, position, pnl_info)
        
        # 4. 물타기 조건 확인 (마지막)
        if self._should_average_down(current_pnl_percent, position):
            return self._generate_averaging_signal(market_data, market_conditions, position, pnl_info)
        
        return None
    
    def _should_average_down(self, current_pnl_percent: float, position: StopLossPosition) -> bool:
        """물타기 매수 조건 확인"""
        # 물타기 트리거 수준 도달 확인
        if current_pnl_percent > self.averaging_trigger:
            return False
        
        # 최대 물타기 횟수 확인
        averaging_entries = [entry for entry in position.entries if entry.order_type == 'averaging']
        if len(averaging_entries) >= self.max_averaging_count:
            return False
        
        return True
    
    def _should_stop_loss(self, current_pnl_percent: float) -> bool:
        """손절 조건 확인 (부동소수점 오차 허용)"""
        # 부동소수점 오차를 고려하여 0.01% 허용 오차 적용
        tolerance = 0.01
        return current_pnl_percent <= (self.stop_loss_level + tolerance)
    
    def _should_take_profit(self, current_pnl_percent: float) -> bool:
        """수익 실현 조건 확인 (수수료 포함)"""
        # 수수료를 고려한 손익분기점 계산
        breakeven_with_fees = self.trading_fee * 2 * 100  # 매수/매도 수수료 * 100 (백분율)
        target_with_fees = self.target_profit + breakeven_with_fees
        
        return current_pnl_percent >= target_with_fees
    
    def _check_trailing_stop(self, market_data: MarketData, market_conditions: MarketConditions,
                           position: StopLossPosition, current_price: float, 
                           current_pnl_percent: float) -> Optional[StopLossAveragingSignal]:
        """트레일링 스톱 확인"""
        # 트레일링 스톱 활성화 확인
        if self.trailing_stop_manager.should_activate(current_pnl_percent):
            if not self.trailing_stop_manager.is_activated():
                self.trailing_stop_manager.activate(current_price)
            else:
                self.trailing_stop_manager.update_high_price(current_price)
        
        # 트레일링 스톱 실행 확인
        if self.trailing_stop_manager.should_trigger_stop(current_price):
            pnl_info = self.position_manager.get_position_pnl(position.market, current_price)
            return StopLossAveragingSignal(
                market=market_data.current_ticker.market,
                action='sell',
                confidence=1.0,
                price=current_price,
                volume=position.total_quantity,
                strategy_id=self.strategy_id,
                timestamp=datetime.now(),
                signal_reason='trailing_stop',
                position_info=position.to_dict(),
                market_conditions=market_conditions,
                expected_pnl=pnl_info['pnl'] if pnl_info else None
            )
        
        return None
    
    def _check_partial_sell(self, market_data: MarketData, market_conditions: MarketConditions,
                          position: StopLossPosition, current_pnl_percent: float,
                          pnl_info: Dict[str, float]) -> Optional[StopLossAveragingSignal]:
        """부분 매도 확인"""
        sell_ratio = self.partial_sell_manager.should_partial_sell(current_pnl_percent)
        if sell_ratio:
            sell_quantity = self.partial_sell_manager.calculate_sell_quantity(
                position.total_quantity, sell_ratio
            )
            
            return StopLossAveragingSignal(
                market=market_data.current_ticker.market,
                action='sell',
                confidence=0.8,
                price=market_data.current_ticker.trade_price,
                volume=sell_quantity,
                strategy_id=self.strategy_id,
                timestamp=datetime.now(),
                signal_reason='partial_sell',
                position_info=position.to_dict(),
                market_conditions=market_conditions,
                expected_pnl=pnl_info['pnl'] * sell_ratio
            )
        
        return None
    
    def _generate_stop_loss_signal(self, market_data: MarketData, market_conditions: MarketConditions,
                                 position: StopLossPosition, pnl_info: Dict[str, float]) -> StopLossAveragingSignal:
        """손절 신호 생성"""
        return StopLossAveragingSignal(
            market=market_data.current_ticker.market,
            action='sell',
            confidence=1.0,
            price=market_data.current_ticker.trade_price,
            volume=position.total_quantity,
            strategy_id=self.strategy_id,
            timestamp=datetime.now(),
            signal_reason='stop_loss',
            position_info=position.to_dict(),
            market_conditions=market_conditions,
            expected_pnl=pnl_info['pnl']
        )
    
    def _generate_take_profit_signal(self, market_data: MarketData, market_conditions: MarketConditions,
                                   position: StopLossPosition, pnl_info: Dict[str, float]) -> StopLossAveragingSignal:
        """수익 실현 신호 생성"""
        return StopLossAveragingSignal(
            market=market_data.current_ticker.market,
            action='sell',
            confidence=0.9,
            price=market_data.current_ticker.trade_price,
            volume=position.total_quantity,
            strategy_id=self.strategy_id,
            timestamp=datetime.now(),
            signal_reason='take_profit',
            position_info=position.to_dict(),
            market_conditions=market_conditions,
            expected_pnl=pnl_info['pnl']
        )
    
    def _generate_averaging_signal(self, market_data: MarketData, market_conditions: MarketConditions,
                                 position: StopLossPosition, pnl_info: Dict[str, float]) -> StopLossAveragingSignal:
        """물타기 신호 생성"""
        return StopLossAveragingSignal(
            market=market_data.current_ticker.market,
            action='buy',
            confidence=0.7,
            price=market_data.current_ticker.trade_price,
            volume=position.entries[0].quantity,  # 최초 매수와 동일한 수량
            strategy_id=self.strategy_id,
            timestamp=datetime.now(),
            signal_reason='averaging',
            position_info=position.to_dict(),
            market_conditions=market_conditions,
            expected_pnl=None
        )
    
    def _calculate_position_pnl(self, current_price: float, position: StopLossPosition) -> Dict[str, float]:
        """포지션 손익 계산 (수수료 포함)"""
        if not position:
            return {'pnl': 0.0, 'pnl_rate': 0.0}
        
        # 현재 가치 계산
        current_value = current_price * position.total_quantity
        
        # 매수 수수료 계산
        buy_fees = position.total_cost * self.trading_fee
        
        # 매도 수수료 계산 (예상)
        sell_fees = current_value * self.trading_fee
        
        # 순 손익 계산
        net_pnl = current_value - position.total_cost - buy_fees - sell_fees
        net_pnl_rate = (net_pnl / (position.total_cost + buy_fees)) * 100
        
        return {
            'pnl': net_pnl,
            'pnl_rate': net_pnl_rate,
            'current_value': current_value,
            'buy_fees': buy_fees,
            'sell_fees': sell_fees
        }
    
    def _suspend_strategy(self, reason: str) -> None:
        """전략 중단"""
        self.strategy_state.is_suspended = True
        self.strategy_state.suspension_reason = reason
        logger.warning(f"Strategy suspended: {reason}")
    
    def _resume_strategy(self) -> None:
        """전략 재개"""
        self.strategy_state.is_suspended = False
        self.strategy_state.suspension_reason = None
        logger.info("Strategy resumed")
    
    def update_position_after_trade(self, market: str, action: str, price: float, 
                                  quantity: float, order_result: Any = None) -> None:
        """거래 후 포지션 업데이트"""
        try:
            if action == 'buy':
                if self.position_manager.has_position(market):
                    # 물타기 매수
                    self.position_manager.add_averaging_position(market, price, quantity, order_result)
                else:
                    # 최초 매수
                    self.position_manager.add_initial_position(market, price, quantity, order_result)
            
            elif action == 'sell':
                if self.position_manager.has_position(market):
                    # 부분 또는 전체 매도
                    position = self.position_manager.get_position(market)
                    if position and quantity >= position.total_quantity:
                        # 전체 매도 - 포지션 청산
                        self.position_manager.close_position(market)
                        self._reset_managers()
                    else:
                        # 부분 매도
                        self.position_manager.partial_sell(market, quantity, price, order_result)
            
            # 거래 기록
            trade = Trade(
                market=market,
                side=action,
                price=price,
                quantity=quantity,
                timestamp=datetime.now(),
                is_stop_loss=(action == 'sell' and self._should_stop_loss(
                    self.position_manager.get_position_pnl(market, price)['pnl_rate'] if 
                    self.position_manager.has_position(market) else 0
                ))
            )
            self.risk_controller.record_trade(trade)
            
        except Exception as e:
            logger.error(f"Failed to update position after trade: {e}")
    
    def _reset_managers(self) -> None:
        """매니저들 상태 초기화"""
        self.partial_sell_manager.reset()
        self.trailing_stop_manager.reset()
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """전략 정보 반환"""
        base_info = super().get_strategy_info()
        base_info.update({
            'strategy_type': 'stop_loss_averaging',
            'stop_loss_level': self.stop_loss_level,
            'averaging_trigger': self.averaging_trigger,
            'target_profit': self.target_profit,
            'max_averaging_count': self.max_averaging_count,
            'trading_fee': self.trading_fee,
            'monitoring_interval': self.monitoring_interval,
            'strategy_state': self.strategy_state.to_dict(),
            'position_count': self.position_manager.get_position_count(),
            'risk_status': self.risk_controller.get_risk_status()
        })
        return base_info