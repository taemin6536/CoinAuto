#!/usr/bin/env python3
"""
공개 API 테스트 (인증 불필요)
"""

import requests
import json

def test_public_api():
    print("🔍 업비트 공개 API 테스트")
    print("=" * 30)
    
    try:
        # 마켓 코드 조회 (인증 불필요)
        print("📊 마켓 정보 조회 중...")
        response = requests.get("https://api.upbit.com/v1/market/all")
        
        if response.status_code == 200:
            markets = response.json()
            krw_markets = [m for m in markets if m['market'].startswith('KRW-')]
            print(f"✅ 공개 API 연결 성공! KRW 마켓 {len(krw_markets)}개")
            
            # 현재가 조회
            print("\n💰 주요 코인 현재가:")
            major_coins = ['KRW-BTC', 'KRW-ETH', 'KRW-XRP', 'KRW-DOGE']
            
            ticker_url = "https://api.upbit.com/v1/ticker"
            params = {'markets': ','.join(major_coins)}
            
            ticker_response = requests.get(ticker_url, params=params)
            if ticker_response.status_code == 200:
                tickers = ticker_response.json()
                for ticker in tickers:
                    market = ticker['market']
                    price = ticker['trade_price']
                    change_rate = ticker['change_rate'] * 100
                    coin = market.split('-')[1]
                    print(f"   {coin:>4}: {price:>12,.0f}원 ({change_rate:+6.2f}%)")
            
            print("\n✅ 업비트 API 서버는 정상 작동 중입니다!")
            print("❗ 이제 IP 제한 설정만 해결하면 실제 거래가 가능합니다.")
            
        else:
            print(f"❌ API 연결 실패: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    test_public_api()