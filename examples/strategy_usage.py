#!/usr/bin/env python3
"""
트레이딩 전략 사용 예제

이 스크립트는 업비트 자동매매 봇의 트레이딩 전략들을 어떻게 사용하는지 보여줍니다.
실제 거래 없이 전략의 동작을 테스트하고 이해할 수 있습니다.
"""

import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import random

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from upbit_trading_bot.strategy.sma_crossover import SMAStrategy
from upbit_trading_bot.strategy.rsi_momentum import RSIStrategy
from upbit_trading_bot.strategy.base import MarketData
from upbit_trading_bot.data.models import Ticker


def generate_sample_market_data(base_price: float = 50000000, periods: int = 100) -> MarketData:
    """
    샘플 시장 데이터 생성 (테스트용)
    
    Args:
        base_price: 기준 가격 (원)
        periods: 생성할 데이터 포인트 수
        
    Returns:
        MarketData 객체
    """
    prices = []
    volumes = []
    timestamps = []
    
    current_price = base_price
    current_time = datetime.now() - timedelta(minutes=periods)
    
    # 가격 트렌드 시뮬레이션
    trend = random.choice([-1, 0, 1])  # -1: 하락, 0: 횡보, 1: 상승
    
    for i in range(periods):
        # 가격 변화 (트렌드 + 랜덤 노이즈)
        trend_change = trend * 0.001  # 0.1% 트렌드
        random_change = random.uniform(-0.02, 0.02)  # ±2% 랜덤 변화
        price_change = trend_change + random_change
        
        current_price *= (1 + price_change)
        current_price = max(current_price, base_price * 0.5)  # 최소 50% 가격 유지
        
        # 거래량 생성 (가격 변화와 반비례 관계)
        volume_base = 100
        volume_multiplier = 1 + abs(price_change) * 10  # 변동성이 클수록 거래량 증가
        volume = volume_base * volume_multiplier * random.uniform(0.5, 2.0)
        
        prices.append(current_price)
        volumes.append(volume)
        timestamps.append(current_time)
        
        current_time += timedelta(minutes=1)
        
        # 가끔 트렌드 변경
        if random.random() < 0.05:  # 5% 확률로 트렌드 변경
            trend = random.choice([-1, 0, 1])
    
    # 현재 티커 생성
    current_ticker = Ticker(
        market="KRW-BTC",
        trade_price=current_price,
        trade_volume=volumes[-1],
        timestamp=timestamps[-1],
        change_rate=(current_price - base_price) / base_price
    )
    
    return MarketData(
        current_ticker=current_ticker,
        price_history=prices,
        volume_history=volumes,
        timestamps=timestamps
    )


def test_sma_strategy():
    """SMA 교차 전략 테스트"""
    print("=" * 60)
    print("SMA 교차 전략 테스트")
    print("=" * 60)
    
    # 전략 설정
    config = {
        'enabled': True,
        'markets': ['KRW-BTC'],
        'parameters': {
            'short_period': 10,
            'long_period': 30,
            'signal_threshold': 0.7,
            'buy_signal': {
                'confirmation_periods': 2
            },
            'risk': {
                'max_position_size': 0.15,
                'stop_loss': 0.03,
                'take_profit': 0.06
            },
            'evaluation_frequency': 300,
            'min_volume_threshold': 1000000
        }
    }
    
    # 전략 인스턴스 생성
    strategy = SMAStrategy("sma_test", config)
    
    print(f"전략 정보: {strategy.get_strategy_info()}")
    print(f"필요한 히스토리 길이: {strategy.get_required_history_length()}")
    
    # 여러 시나리오 테스트
    scenarios = [
        ("상승 추세", 45000000),
        ("하락 추세", 55000000),
        ("횡보", 50000000)
    ]
    
    for scenario_name, base_price in scenarios:
        print(f"\n--- {scenario_name} 시나리오 ---")
        
        # 시장 데이터 생성
        market_data = generate_sample_market_data(base_price, 60)
        
        # 전략 평가
        if strategy.can_evaluate(market_data):
            signal = strategy.evaluate(market_data)
            if signal:
                print(f"신호 생성: {signal.action.upper()}")
                print(f"  - 시장: {signal.market}")
                print(f"  - 가격: {signal.price:,.0f} KRW")
                print(f"  - 신뢰도: {signal.confidence:.2f}")
                print(f"  - 시간: {signal.timestamp}")
            else:
                print("신호 없음")
        else:
            print("평가 불가 (조건 미충족)")


def test_rsi_strategy():
    """RSI 모멘텀 전략 테스트"""
    print("\n" + "=" * 60)
    print("RSI 모멘텀 전략 테스트")
    print("=" * 60)
    
    # 전략 설정
    config = {
        'enabled': True,
        'markets': ['KRW-BTC'],
        'parameters': {
            'rsi_period': 14,
            'oversold_threshold': 30,
            'overbought_threshold': 70,
            'signal_threshold': 0.75,
            'risk': {
                'max_position_size': 0.1,
                'stop_loss': 0.04,
                'take_profit': 0.08,
                'trailing_stop': True,
                'trailing_stop_percentage': 0.02
            },
            'evaluation_frequency': 180,
            'min_volume_threshold': 500000,
            'indicators': {
                'volume_sma_period': 20,
                'price_sma_period': 50
            }
        }
    }
    
    # 전략 인스턴스 생성
    strategy = RSIStrategy("rsi_test", config)
    
    print(f"전략 정보: {strategy.get_strategy_info()}")
    print(f"필요한 히스토리 길이: {strategy.get_required_history_length()}")
    
    # 과매도/과매수 시나리오 테스트
    scenarios = [
        ("과매도 상황", 48000000),  # 하락 후 반등 기대
        ("과매수 상황", 52000000),  # 상승 후 조정 기대
        ("중립 상황", 50000000)     # 일반적인 상황
    ]
    
    for scenario_name, base_price in scenarios:
        print(f"\n--- {scenario_name} 시나리오 ---")
        
        # 시장 데이터 생성 (더 긴 히스토리 필요)
        market_data = generate_sample_market_data(base_price, 80)
        
        # 전략 평가
        if strategy.can_evaluate(market_data):
            signal = strategy.evaluate(market_data)
            if signal:
                print(f"신호 생성: {signal.action.upper()}")
                print(f"  - 시장: {signal.market}")
                print(f"  - 가격: {signal.price:,.0f} KRW")
                print(f"  - 신뢰도: {signal.confidence:.2f}")
                print(f"  - 시간: {signal.timestamp}")
            else:
                print("신호 없음")
        else:
            print("평가 불가 (조건 미충족)")


def compare_strategies():
    """두 전략 비교 테스트"""
    print("\n" + "=" * 60)
    print("전략 비교 테스트")
    print("=" * 60)
    
    # 동일한 시장 데이터로 두 전략 테스트
    market_data = generate_sample_market_data(50000000, 100)
    
    # SMA 전략
    sma_config = {
        'enabled': True,
        'markets': ['KRW-BTC'],
        'parameters': {
            'short_period': 10,
            'long_period': 30,
            'signal_threshold': 0.7,
            'buy_signal': {'confirmation_periods': 1},
            'risk': {'max_position_size': 0.15}
        }
    }
    sma_strategy = SMAStrategy("sma_compare", sma_config)
    
    # RSI 전략
    rsi_config = {
        'enabled': True,
        'markets': ['KRW-BTC'],
        'parameters': {
            'rsi_period': 14,
            'oversold_threshold': 30,
            'overbought_threshold': 70,
            'signal_threshold': 0.7,
            'risk': {'max_position_size': 0.1},
            'indicators': {'volume_sma_period': 20, 'price_sma_period': 50}
        }
    }
    rsi_strategy = RSIStrategy("rsi_compare", rsi_config)
    
    print(f"현재 가격: {market_data.current_ticker.trade_price:,.0f} KRW")
    print(f"가격 변화율: {market_data.current_ticker.change_rate:.2%}")
    
    # 두 전략 평가
    strategies = [
        ("SMA 교차", sma_strategy),
        ("RSI 모멘텀", rsi_strategy)
    ]
    
    for name, strategy in strategies:
        print(f"\n--- {name} 전략 결과 ---")
        if strategy.can_evaluate(market_data):
            signal = strategy.evaluate(market_data)
            if signal:
                print(f"신호: {signal.action.upper()}")
                print(f"신뢰도: {signal.confidence:.2f}")
            else:
                print("신호 없음")
        else:
            print("평가 불가")


def demonstrate_config_changes():
    """설정 변경 데모"""
    print("\n" + "=" * 60)
    print("설정 변경 데모 (핫 리로드)")
    print("=" * 60)
    
    # 초기 설정
    initial_config = {
        'enabled': True,
        'markets': ['KRW-BTC'],
        'parameters': {
            'short_period': 10,
            'long_period': 30,
            'signal_threshold': 0.8
        }
    }
    
    strategy = SMAStrategy("config_demo", initial_config)
    print("초기 설정:")
    print(f"  - 단기 기간: {strategy.short_period}")
    print(f"  - 장기 기간: {strategy.long_period}")
    print(f"  - 신호 임계값: {strategy.signal_threshold}")
    
    # 설정 변경 (핫 리로드 시뮬레이션)
    new_config = {
        'parameters': {
            'short_period': 5,
            'long_period': 20,
            'signal_threshold': 0.7
        }
    }
    
    strategy.update_config(new_config)
    # 변경된 매개변수를 다시 설정
    strategy.short_period = strategy.config['parameters']['short_period']
    strategy.long_period = strategy.config['parameters']['long_period']
    strategy.signal_threshold = strategy.config['parameters']['signal_threshold']
    print("\n설정 변경 후:")
    print(f"  - 단기 기간: {strategy.short_period}")
    print(f"  - 장기 기간: {strategy.long_period}")
    print(f"  - 신호 임계값: {strategy.signal_threshold}")


def main():
    """메인 실행 함수"""
    print("업비트 자동매매 봇 - 트레이딩 전략 사용 예제")
    print("이 예제는 실제 거래를 수행하지 않습니다.")
    
    try:
        # 각 전략 개별 테스트
        test_sma_strategy()
        test_rsi_strategy()
        
        # 전략 비교
        compare_strategies()
        
        # 설정 변경 데모
        demonstrate_config_changes()
        
        print("\n" + "=" * 60)
        print("테스트 완료!")
        print("=" * 60)
        print("\n실제 사용 시:")
        print("1. config/strategies/ 디렉토리의 YAML 파일을 수정하세요")
        print("2. 봇을 시작하거나 핫 리로드를 사용하세요")
        print("3. 로그를 통해 전략 동작을 모니터링하세요")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()