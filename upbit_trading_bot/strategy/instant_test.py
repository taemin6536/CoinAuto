"""
즉시 테스트 전략 - 바로 매매 테스트용
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .base import TradingStrategy
from ..data.models import TradingSignal
from ..data.market_data import MarketData

logger = logging.getLogger(__name__)


class InstantTestStrategy(TradingStrategy):
    """
    즉시 테스트 전략
    - 첫 번째 실행에서 바로 매수 신호 생성
    - 두 번째 실행에서 바로 매도 신호 생성
    """
    
    def __init__(self, strategy_id: str, config: Dict[str, Any]):
        super().__init__(strategy_id, config)
        self.execution_count = 0
        self.last_action = None
        self.api_client = None  # API 클라이언트는 나중에 설정됨
        
        # 수익률 기준 설정 (기본값: 1%)
        self.profit_threshold = config.get('profit_threshold', 1.0)  # 1% 수익률
        
        logger.info(f"InstantTestStrategy 초기화: 즉시 매매 테스트 (수익률 기준: {self.profit_threshold}%)")
    
    def set_api_client(self, api_client):
        """API 클라이언트 설정"""
        self.api_client = api_client
    
    def evaluate(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        시장 데이터를 평가하여 거래 신호 생성 - 매수와 매도 모두 수행
        """
        try:
            if not market_data or not market_data.ticker:
                return None
            
            ticker = market_data.ticker
            current_price = ticker.trade_price
            self.execution_count += 1
            
            logger.info(f"InstantTestStrategy 실행 #{self.execution_count}: {ticker.market} 현재가 {current_price:,.0f}")
            
            # 매수 신호 (홀수 번째 실행)
            if self.execution_count % 2 == 1:
                logger.info(f"매수 신호 생성: {ticker.market}")
                self.last_action = 'buy'
                return TradingSignal(
                    market=ticker.market,
                    action='buy',
                    confidence=0.9,
                    price=current_price,
                    volume=5000,  # 시장가 매수: 5,000원으로 변경 (최소 주문 금액)
                    strategy_id=self.strategy_id,
                    timestamp=datetime.now()
                )
            
            # 매도 신호 (짝수 번째 실행) - 보유 코인이 있고 수익이 날 때만
            else:
                # 보유 코인 확인
                if self.api_client:
                    try:
                        accounts = self.api_client.get_accounts()
                        market_currency = ticker.market.split('-')[1]  # KRW-BTC -> BTC
                        coin_account = next((acc for acc in accounts if acc.market == market_currency), None)
                        
                        if coin_account and coin_account.balance > 0.00001:  # 최소 보유량 확인
                            available_balance = coin_account.balance - coin_account.locked
                            if available_balance > 0.00001:
                                # 수익률 계산
                                avg_buy_price = coin_account.avg_buy_price  # 평균 매수가
                                current_price = ticker.trade_price  # 현재가
                                profit_rate = (current_price - avg_buy_price) / avg_buy_price * 100
                                
                                logger.info(f"{ticker.market} 수익률: {profit_rate:.2f}% "
                                          f"(평균매수가: {avg_buy_price:,.0f}, 현재가: {current_price:,.0f})")
                                
                                # 수익률이 설정된 기준 이상일 때만 매도
                                if profit_rate >= self.profit_threshold:
                                    logger.info(f"매도 신호 생성: {ticker.market} 수익률 {profit_rate:.2f}% "
                                              f"(보유량: {available_balance:.8f})")
                                    self.last_action = 'sell'
                                    return TradingSignal(
                                        market=ticker.market,
                                        action='sell',
                                        confidence=0.9,
                                        price=current_price,
                                        volume=available_balance * 0.99,  # 보유량의 99% 매도 (수수료 고려)
                                        strategy_id=self.strategy_id,
                                        timestamp=datetime.now()
                                    )
                                else:
                                    logger.debug(f"매도 대기: {ticker.market} 수익률 {profit_rate:.2f}% < {self.profit_threshold}%")
                            else:
                                logger.debug(f"매도 불가: {market_currency} 사용 가능한 잔고 없음")
                        else:
                            logger.debug(f"매도 불가: {market_currency} 보유량 없음")
                    except Exception as e:
                        logger.error(f"보유량 확인 중 오류: {e}")
                else:
                    logger.debug("API 클라이언트가 설정되지 않음")
            
            return None
            
        except Exception as e:
            logger.error(f"InstantTestStrategy 평가 중 오류: {e}")
            return None
    
    def get_required_history_length(self) -> int:
        """필요한 히스토리 길이 반환"""
        return 1  # 최소한의 데이터만 필요