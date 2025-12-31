"""
포트폴리오 관리 및 성과 추적 모듈.

잔고 및 포지션 추적, 거래 기록, 성과 지표 계산, 보고서 생성을 담당합니다.
"""

import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal, ROUND_HALF_UP
import statistics
import math

from upbit_trading_bot.data.database import DatabaseManager, get_db_manager
from upbit_trading_bot.data.models import Position, Account, Order, OrderResult, TradingSignal

logger = logging.getLogger(__name__)


class PortfolioManager:
    """포트폴리오 관리 및 성과 추적을 담당하는 클래스."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        포트폴리오 매니저 초기화.
        
        Args:
            db_manager: 데이터베이스 매니저 인스턴스 (선택사항)
        """
        self.db = db_manager or get_db_manager()
        self._positions: Dict[str, Position] = {}
        self._accounts: Dict[str, Account] = {}
        self._total_krw_value = 0.0
        self._total_btc_value = 0.0
        self._last_update = datetime.now(timezone.utc)
        
        logger.info("포트폴리오 매니저 초기화 완료")
    
    def update_positions(self, accounts: List[Account]) -> bool:
        """
        계정 정보를 기반으로 포지션을 업데이트합니다.
        
        Args:
            accounts: 업비트 API에서 받은 계정 정보 리스트
            
        Returns:
            bool: 업데이트 성공 여부
        """
        try:
            # 기존 포지션 및 계정 정보 초기화
            self._positions.clear()
            self._accounts.clear()
            
            total_krw = 0.0
            total_btc = 0.0
            
            for account in accounts:
                if not account.validate():
                    logger.warning(f"유효하지 않은 계정 정보: {account}")
                    continue
                
                # 계정 정보 저장
                self._accounts[account.currency] = account
                
                # KRW 잔고 계산
                if account.currency == 'KRW':
                    total_krw += account.balance
                    continue
                
                # 암호화폐 포지션 생성
                if account.balance > 0 or account.locked > 0:
                    market = f"KRW-{account.currency}"
                    position = Position(
                        market=market,
                        avg_buy_price=account.avg_buy_price,
                        balance=account.balance,
                        locked=account.locked,
                        unit_currency=account.unit_currency
                    )
                    
                    if position.validate():
                        self._positions[market] = position
                        
                        # BTC 기준 가치 계산 (간단한 추정)
                        if account.currency == 'BTC':
                            total_btc += account.balance
                        else:
                            # 다른 암호화폐는 KRW 가치로 계산 후 BTC로 변환 (추정)
                            krw_value = account.balance * account.avg_buy_price
                            total_krw += krw_value
                    else:
                        logger.warning(f"유효하지 않은 포지션: {position}")
            
            self._total_krw_value = total_krw
            self._total_btc_value = total_btc
            self._last_update = datetime.now(timezone.utc)
            
            # 포트폴리오 스냅샷 저장
            self._save_portfolio_snapshot()
            
            logger.info(f"포트폴리오 업데이트 완료: {len(self._positions)}개 포지션, "
                       f"총 KRW 가치: {total_krw:,.0f}원")
            return True
            
        except Exception as e:
            logger.error(f"포트폴리오 업데이트 실패: {e}")
            return False
    
    def record_trade(self, order_result: OrderResult, strategy_id: Optional[str] = None) -> bool:
        """
        거래 기록을 저장합니다.
        
        Args:
            order_result: 주문 실행 결과
            strategy_id: 전략 ID (선택사항)
            
        Returns:
            bool: 기록 성공 여부
        """
        try:
            if not order_result.validate():
                logger.error(f"유효하지 않은 주문 결과: {order_result}")
                return False
            
            # 실제로 체결된 거래만 기록
            if order_result.executed_volume <= 0:
                logger.info(f"체결되지 않은 주문은 기록하지 않음: {order_result.order_id}")
                return True
            
            # 거래 데이터 준비
            trade_data = {
                'market': order_result.market,
                'side': order_result.side,
                'price': order_result.price or 0.0,  # 시장가 주문의 경우 0으로 설정
                'volume': order_result.executed_volume,
                'fee': order_result.paid_fee,
                'timestamp': datetime.now(timezone.utc),
                'strategy_id': strategy_id
            }
            
            # 데이터베이스에 저장
            success = self.db.insert_trade(trade_data)
            
            if success:
                logger.info(f"거래 기록 저장 완료: {order_result.market} "
                           f"{order_result.side} {order_result.executed_volume}")
            else:
                logger.error(f"거래 기록 저장 실패: {order_result.order_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"거래 기록 중 오류 발생: {e}")
            return False
    
    def get_positions(self) -> Dict[str, Position]:
        """
        현재 포지션 정보를 반환합니다.
        
        Returns:
            Dict[str, Position]: 마켓별 포지션 정보
        """
        return self._positions.copy()
    
    def get_position(self, market: str) -> Optional[Position]:
        """
        특정 마켓의 포지션 정보를 반환합니다.
        
        Args:
            market: 마켓 코드 (예: KRW-BTC)
            
        Returns:
            Optional[Position]: 포지션 정보 (없으면 None)
        """
        return self._positions.get(market)
    
    def get_accounts(self) -> Dict[str, Account]:
        """
        현재 계정 정보를 반환합니다.
        
        Returns:
            Dict[str, Account]: 통화별 계정 정보
        """
        return self._accounts.copy()
    
    def get_account(self, currency: str) -> Optional[Account]:
        """
        특정 통화의 계정 정보를 반환합니다.
        
        Args:
            currency: 통화 코드 (예: KRW, BTC)
            
        Returns:
            Optional[Account]: 계정 정보 (없으면 None)
        """
        return self._accounts.get(currency)
    
    def get_total_value(self) -> Tuple[float, float]:
        """
        총 포트폴리오 가치를 반환합니다.
        
        Returns:
            Tuple[float, float]: (KRW 가치, BTC 가치)
        """
        return self._total_krw_value, self._total_btc_value
    
    def calculate_performance_metrics(self, 
                                    start_date: Optional[datetime] = None,
                                    end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        성과 지표를 계산합니다.
        
        Args:
            start_date: 시작 날짜 (선택사항)
            end_date: 종료 날짜 (선택사항)
            
        Returns:
            Dict[str, Any]: 성과 지표 딕셔너리
        """
        try:
            # 기본 날짜 설정
            if end_date is None:
                end_date = datetime.now(timezone.utc)
            if start_date is None:
                start_date = end_date - timedelta(days=30)  # 기본 30일
            
            # 거래 기록 조회
            trades = self.db.get_trades(start_date=start_date, end_date=end_date, limit=10000)
            
            if not trades:
                logger.info("성과 계산을 위한 거래 기록이 없습니다")
                return self._get_empty_performance_metrics()
            
            # 기본 통계
            total_trades = len(trades)
            buy_trades = [t for t in trades if t['side'] == 'bid']
            sell_trades = [t for t in trades if t['side'] == 'ask']
            
            total_buy_volume = sum(float(t['volume']) for t in buy_trades)
            total_sell_volume = sum(float(t['volume']) for t in sell_trades)
            total_fees = sum(float(t['fee']) for t in trades)
            
            # 수익률 계산 (간단한 방식)
            total_buy_value = sum(float(t['price']) * float(t['volume']) for t in buy_trades)
            total_sell_value = sum(float(t['price']) * float(t['volume']) for t in sell_trades)
            
            gross_profit = total_sell_value - total_buy_value
            net_profit = gross_profit - total_fees
            
            # 승률 계산 (매도 거래 기준)
            profitable_sells = 0
            if sell_trades:
                for sell_trade in sell_trades:
                    # 해당 코인의 평균 매수가와 비교
                    market = sell_trade['market']
                    position = self._positions.get(market)
                    if position and float(sell_trade['price']) > position.avg_buy_price:
                        profitable_sells += 1
            
            win_rate = (profitable_sells / len(sell_trades)) if sell_trades else 0.0
            
            # 일일 수익률 계산 (샤프 비율용)
            daily_returns = self._calculate_daily_returns(trades, start_date, end_date)
            
            # 샤프 비율 계산 (무위험 수익률 3% 가정)
            risk_free_rate = 0.03 / 365  # 일일 무위험 수익률
            sharpe_ratio = 0.0
            
            if daily_returns and len(daily_returns) > 1:
                avg_return = statistics.mean(daily_returns)
                return_std = statistics.stdev(daily_returns)
                if return_std > 0:
                    sharpe_ratio = (avg_return - risk_free_rate) / return_std
            
            # 최대 낙폭 계산
            max_drawdown = self._calculate_max_drawdown(trades)
            
            # 성과 지표 반환
            performance_metrics = {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'days': (end_date - start_date).days
                },
                'trading_summary': {
                    'total_trades': total_trades,
                    'buy_trades': len(buy_trades),
                    'sell_trades': len(sell_trades),
                    'total_buy_volume': round(total_buy_volume, 8),
                    'total_sell_volume': round(total_sell_volume, 8),
                    'total_fees': round(total_fees, 2)
                },
                'profitability': {
                    'gross_profit': round(gross_profit, 2),
                    'net_profit': round(net_profit, 2),
                    'total_fees': round(total_fees, 2),
                    'profit_margin': round((net_profit / total_buy_value * 100) if total_buy_value > 0 else 0, 2)
                },
                'performance_ratios': {
                    'win_rate': round(win_rate * 100, 2),
                    'sharpe_ratio': round(sharpe_ratio, 4),
                    'max_drawdown': round(max_drawdown * 100, 2)
                },
                'portfolio_value': {
                    'total_krw': round(self._total_krw_value, 2),
                    'total_btc': round(self._total_btc_value, 8),
                    'positions_count': len(self._positions)
                },
                'calculated_at': datetime.now(timezone.utc).isoformat()
            }
            
            logger.info(f"성과 지표 계산 완료: 순이익 {net_profit:,.0f}원, "
                       f"승률 {win_rate*100:.1f}%, 샤프비율 {sharpe_ratio:.3f}")
            
            return performance_metrics
            
        except Exception as e:
            logger.error(f"성과 지표 계산 중 오류 발생: {e}")
            return self._get_empty_performance_metrics()
    
    def generate_report(self, 
                       start_date: Optional[datetime] = None,
                       end_date: Optional[datetime] = None,
                       include_positions: bool = True,
                       include_trades: bool = True) -> Dict[str, Any]:
        """
        JSON 형식의 거래 보고서를 생성합니다.
        
        Args:
            start_date: 시작 날짜 (선택사항)
            end_date: 종료 날짜 (선택사항)
            include_positions: 포지션 정보 포함 여부
            include_trades: 거래 내역 포함 여부
            
        Returns:
            Dict[str, Any]: JSON 형식의 보고서
        """
        try:
            # 성과 지표 계산
            performance_metrics = self.calculate_performance_metrics(start_date, end_date)
            
            # 보고서 기본 구조
            report = {
                'report_info': {
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'report_type': 'trading_performance',
                    'version': '1.0'
                },
                'performance_metrics': performance_metrics
            }
            
            # 포지션 정보 추가
            if include_positions:
                positions_data = {}
                for market, position in self._positions.items():
                    positions_data[market] = {
                        'avg_buy_price': round(position.avg_buy_price, 2),
                        'balance': round(position.balance, 8),
                        'locked': round(position.locked, 8),
                        'unit_currency': position.unit_currency,
                        'estimated_value_krw': round(position.balance * position.avg_buy_price, 2)
                    }
                
                report['current_positions'] = positions_data
            
            # 거래 내역 추가
            if include_trades:
                trades = self.db.get_trades(
                    start_date=start_date, 
                    end_date=end_date, 
                    limit=1000
                )
                
                trades_data = []
                for trade in trades:
                    trades_data.append({
                        'timestamp': trade['timestamp'],
                        'market': trade['market'],
                        'side': trade['side'],
                        'price': float(trade['price']),
                        'volume': float(trade['volume']),
                        'fee': float(trade['fee']),
                        'strategy_id': trade.get('strategy_id'),
                        'trade_value': float(trade['price']) * float(trade['volume'])
                    })
                
                report['trade_history'] = trades_data
            
            # 계정 정보 추가
            accounts_data = {}
            for currency, account in self._accounts.items():
                accounts_data[currency] = {
                    'balance': round(account.balance, 8),
                    'locked': round(account.locked, 8),
                    'avg_buy_price': round(account.avg_buy_price, 2),
                    'unit_currency': account.unit_currency
                }
            
            report['account_balances'] = accounts_data
            
            logger.info(f"거래 보고서 생성 완료: {len(report)} 섹션")
            return report
            
        except Exception as e:
            logger.error(f"보고서 생성 중 오류 발생: {e}")
            return {
                'error': str(e),
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
    
    def save_report_to_file(self, 
                           report: Dict[str, Any], 
                           filename: Optional[str] = None) -> bool:
        """
        보고서를 JSON 파일로 저장합니다.
        
        Args:
            report: 보고서 데이터
            filename: 파일명 (선택사항)
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"trading_report_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"보고서 파일 저장 완료: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"보고서 파일 저장 실패: {e}")
            return False
    
    def _save_portfolio_snapshot(self) -> bool:
        """포트폴리오 스냅샷을 데이터베이스에 저장합니다."""
        try:
            positions_data = {}
            for market, position in self._positions.items():
                positions_data[market] = position.to_dict()
            
            snapshot_data = {
                'total_krw': self._total_krw_value,
                'total_btc': self._total_btc_value,
                'timestamp': self._last_update,
                'positions': positions_data
            }
            
            return self.db.insert_portfolio_snapshot(snapshot_data)
            
        except Exception as e:
            logger.error(f"포트폴리오 스냅샷 저장 실패: {e}")
            return False
    
    def _calculate_daily_returns(self, 
                               trades: List[Dict[str, Any]], 
                               start_date: datetime, 
                               end_date: datetime) -> List[float]:
        """일일 수익률을 계산합니다."""
        try:
            # 일별 거래 그룹화
            daily_trades = {}
            for trade in trades:
                trade_date = datetime.fromisoformat(trade['timestamp']).date()
                if trade_date not in daily_trades:
                    daily_trades[trade_date] = []
                daily_trades[trade_date].append(trade)
            
            # 일일 수익률 계산
            daily_returns = []
            for date, day_trades in daily_trades.items():
                daily_profit = 0.0
                daily_volume = 0.0
                
                for trade in day_trades:
                    trade_value = float(trade['price']) * float(trade['volume'])
                    if trade['side'] == 'bid':  # 매수
                        daily_profit -= trade_value
                        daily_volume += trade_value
                    else:  # 매도
                        daily_profit += trade_value
                        daily_volume += trade_value
                    
                    daily_profit -= float(trade['fee'])
                
                if daily_volume > 0:
                    daily_return = daily_profit / daily_volume
                    daily_returns.append(daily_return)
            
            return daily_returns
            
        except Exception as e:
            logger.error(f"일일 수익률 계산 실패: {e}")
            return []
    
    def _calculate_max_drawdown(self, trades: List[Dict[str, Any]]) -> float:
        """최대 낙폭을 계산합니다."""
        try:
            if not trades:
                return 0.0
            
            # 누적 수익 계산
            cumulative_profit = 0.0
            max_profit = 0.0
            max_drawdown = 0.0
            
            for trade in sorted(trades, key=lambda x: x['timestamp']):
                trade_value = float(trade['price']) * float(trade['volume'])
                
                if trade['side'] == 'bid':  # 매수
                    cumulative_profit -= trade_value
                else:  # 매도
                    cumulative_profit += trade_value
                
                cumulative_profit -= float(trade['fee'])
                
                # 최고점 업데이트
                if cumulative_profit > max_profit:
                    max_profit = cumulative_profit
                
                # 낙폭 계산
                if max_profit > 0:
                    drawdown = (max_profit - cumulative_profit) / max_profit
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"최대 낙폭 계산 실패: {e}")
            return 0.0
    
    def _get_empty_performance_metrics(self) -> Dict[str, Any]:
        """빈 성과 지표를 반환합니다."""
        return {
            'period': {
                'start_date': datetime.now(timezone.utc).isoformat(),
                'end_date': datetime.now(timezone.utc).isoformat(),
                'days': 0
            },
            'trading_summary': {
                'total_trades': 0,
                'buy_trades': 0,
                'sell_trades': 0,
                'total_buy_volume': 0.0,
                'total_sell_volume': 0.0,
                'total_fees': 0.0
            },
            'profitability': {
                'gross_profit': 0.0,
                'net_profit': 0.0,
                'total_fees': 0.0,
                'profit_margin': 0.0
            },
            'performance_ratios': {
                'win_rate': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0
            },
            'portfolio_value': {
                'total_krw': self._total_krw_value,
                'total_btc': self._total_btc_value,
                'positions_count': len(self._positions)
            },
            'calculated_at': datetime.now(timezone.utc).isoformat()
        }
    
    def get_portfolio_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        포트폴리오 가치 변화 이력을 조회합니다.
        
        Args:
            days: 조회할 일수
            
        Returns:
            List[Dict[str, Any]]: 포트폴리오 스냅샷 리스트
        """
        try:
            # 최근 스냅샷들을 조회하는 SQL (MySQL 버전)
            sql = """
                SELECT * FROM portfolio_snapshots 
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                ORDER BY timestamp DESC
                LIMIT 1000
            """
            
            with self.db.get_cursor() as cursor:
                cursor.execute(sql, (days,))
                snapshots = cursor.fetchall()
                
                # JSON 필드 파싱
                for snapshot in snapshots:
                    if snapshot['positions']:
                        snapshot['positions'] = json.loads(snapshot['positions'])
                
                return snapshots
                
        except Exception as e:
            logger.error(f"포트폴리오 이력 조회 실패: {e}")
            return []
    
    def cleanup_old_data(self, days_to_keep: int = 90) -> bool:
        """
        오래된 데이터를 정리합니다.
        
        Args:
            days_to_keep: 보관할 일수
            
        Returns:
            bool: 정리 성공 여부
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
            
            with self.db.get_cursor() as cursor:
                # 오래된 포트폴리오 스냅샷 삭제
                cursor.execute(
                    "DELETE FROM portfolio_snapshots WHERE timestamp < %s",
                    (cutoff_date,)
                )
                deleted_snapshots = cursor.rowcount
                
                logger.info(f"데이터 정리 완료: {deleted_snapshots}개 스냅샷 삭제")
                return True
                
        except Exception as e:
            logger.error(f"데이터 정리 실패: {e}")
            return False


# 전역 포트폴리오 매니저 인스턴스
_portfolio_manager = None


def get_portfolio_manager() -> PortfolioManager:
    """
    전역 포트폴리오 매니저 인스턴스를 반환합니다.
    
    Returns:
        PortfolioManager: 포트폴리오 매니저 인스턴스
    """
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioManager()
    return _portfolio_manager