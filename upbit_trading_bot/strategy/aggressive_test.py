"""
공격적인 테스트 전략 - 빠른 매매 테스트용
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .base import TradingStrategy
from ..data.models import TradingSignal
from ..data.market_data import MarketData

logger = logging.getLogger(__name__)


class AggressiveTestStrategy(TradingStrategy):
    """
    매우 공격적인 테스트 전략
    - 0.3% 이상 하락 시 매수
    - 0.3% 이상 상승 시 매도
    - 매우 빠른 매매로 테스트
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        super().__init__(strategy_id, config)
        self.buy_threshold = config.get('buy_threshold', -0.001)  # -0.1%
        self.sell_threshold = config.get('sell_threshold', 0.001)  # +0.1%
        self.min_price_history = config.get('min_price_history', 2)
        
        logger.info(f"AggressiveTestStrategy 초기화: 매수 임계값 {self.buy_threshold*100:.1f}%, "
                   f"매도 임계값 {self.sell_threshold*100:.1f}%")
    
    def evaluate(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        시장 데이터를 평가하여 거래 신호 생성
        """
        try:
            if not market_data or not market_data.ticker:
                return None
            
            ticker = market_data.ticker
            current_price = ticker.trade_price
            
            # 가격 히스토리가 충분하지 않으면 대기
            if not market_data.price_history or len(market_data.price_history) < self.min_price_history:
                logger.debug(f"가격 히스토리 부족: {len(market_data.price_history) if market_data.price_history else 0}")
                return None
            
            # 최근 평균 가격 계산 (2개 데이터 포인트로 매우 빠른 반응)
            recent_prices = market_data.price_history[-2:]
            avg_price = sum(recent_prices) / len(recent_prices)
            
            # 현재 가격과 평균 가격 비교
            price_change = (current_price - avg_price) / avg_price
            
            logger.debug(f"{ticker.market}: 현재가 {current_price:,.0f}, 평균가 {avg_price:,.0f}, "
                        f"변화율 {price_change*100:.3f}%")
            
            # 매수 신호만 생성 (매도는 일단 비활성화)
            if price_change <= self.buy_threshold:
                logger.info(f"매수 신호 생성: {ticker.market} {price_change*100:.3f}% 하락")
                return TradingSignal(
                    market=ticker.market,
                    action='buy',
                    confidence=0.8,  # 높은 신뢰도로 빠른 거래
                    price=current_price,
                    volume=10000,  # 시장가 매수: KRW 금액으로 설정 (1만원)
                    strategy_id=self.strategy_id,
                    timestamp=datetime.now()
                )
            
            # 매도 신호는 일단 비활성화 (보유 코인 확인 로직 추가 필요)
            # elif price_change >= self.sell_threshold:
            #     # 실제 보유량 확인 필요 (여기서는 간단히 처리)
            #     logger.info(f"매도 신호 생성: {ticker.market} {price_change*100:.3f}% 상승")
            #     return TradingSignal(
            #         market=ticker.market,
            #         action='sell',
            #         confidence=0.8,  # 높은 신뢰도로 빠른 거래
            #         price=current_price,
            #         volume=0.00001,  # 최소 매도량 (실제로는 보유량 확인 후 설정)
            #         strategy_id=self.strategy_id,
            #         timestamp=datetime.now()
            #     )
            
            return None
            
        except Exception as e:
            logger.error(f"AggressiveTestStrategy 평가 중 오류: {e}")
            return None
    
    def get_required_history_length(self) -> int:
        """필요한 히스토리 길이 반환"""
        return self.min_price_history