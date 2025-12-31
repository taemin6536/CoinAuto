"""
간단한 테스트 전략 - 실제 거래 테스트용
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .base import TradingStrategy
from ..data.models import TradingSignal
from ..data.market_data import MarketData

logger = logging.getLogger(__name__)


class SimpleTestStrategy(TradingStrategy):
    """
    공격적인 테스트 전략
    - 1% 이상 하락 시 매수
    - 1% 이상 상승 시 매도
    - 더 빠른 매매를 위해 임계값 낮춤
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        super().__init__(strategy_id, config)
        self.buy_threshold = config.get('buy_threshold', -0.01)  # -1%
        self.sell_threshold = config.get('sell_threshold', 0.01)  # +1%
        self.min_price_history = config.get('min_price_history', 5)  # 더 적은 히스토리로 빠른 반응
        
        logger.info(f"SimpleTestStrategy 초기화: 매수 임계값 {self.buy_threshold*100:.1f}%, "
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
            
            # 최근 평균 가격 계산 (5개 데이터 포인트로 더 빠른 반응)
            recent_prices = market_data.price_history[-5:]
            avg_price = sum(recent_prices) / len(recent_prices)
            
            # 현재 가격과 평균 가격 비교
            price_change = (current_price - avg_price) / avg_price
            
            logger.debug(f"{ticker.market}: 현재가 {current_price:,.0f}, 평균가 {avg_price:,.0f}, "
                        f"변화율 {price_change*100:.2f}%")
            
            # 매수 신호 (가격이 크게 하락했을 때)
            if price_change <= self.buy_threshold:
                logger.info(f"매수 신호 생성: {ticker.market} {price_change*100:.2f}% 하락")
                return TradingSignal(
                    market=ticker.market,
                    action='buy',
                    confidence=min(0.9, abs(price_change) * 10),  # 하락폭에 비례한 신뢰도
                    price=current_price,
                    volume=10000 / current_price,  # 1만원어치로 증가
                    strategy_id=self.strategy_id,
                    timestamp=datetime.now()
                )
            
            # 매도 신호 (가격이 상승했을 때)
            elif price_change >= self.sell_threshold:
                logger.info(f"매도 신호 생성: {ticker.market} {price_change*100:.2f}% 상승")
                return TradingSignal(
                    market=ticker.market,
                    action='sell',
                    confidence=min(0.9, price_change * 10),  # 상승폭에 비례한 신뢰도
                    price=current_price,
                    volume=0.1,  # 임시값, 실제로는 보유량에 따라 결정
                    strategy_id=self.strategy_id,
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"SimpleTestStrategy 평가 중 오류: {e}")
            return None
    
    def get_required_history_length(self) -> int:
        """필요한 히스토리 길이 반환"""
        return self.min_price_history