import asyncio
from kis import KISApi
from datetime import datetime
import json

# 모니터링할 채권 종목 리스트
SYMBOLS = [
    "KR6103161EB6",  
]

def load_config():
    """설정 파일 로드"""
    try:
        config = {}
        with open('shv_alarm/.env', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    if '#' in value:
                        value = value.split('#')[0]
                    config[key.strip()] = value.strip()
        return config
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {e}")
        return {}

async def get_bond_quote(api, symbol):
    """채권 호가 조회"""
    try:
        # 발행정보 조회로 종목명 가져오기
        info_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/issue-info"
        info_params = {
            "PDNO": symbol,                 # 채권종목코드
            "PRDT_TYPE_CD": "302"          # 상품유형코드 (302: 채권)
        }
        info_headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "CTPF1101R",  # 채권 발행정보 조회
            "custtype": "P"        # 개인
        }
        info_result = await api.request("get", info_url, params=info_params, headers=info_headers)
        bond_name = info_result.get("output", {}).get("prdt_name", "-")
        
        # 호가 조회
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-asking-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
            "FID_INPUT_ISCD": symbol,        # 종목코드
        }
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "FHKBJ773401C0",  # 채권 호가 조회
            "custtype": "P"            # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output = result.get("output", {})
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n=== {bond_name} 채권 호가 ===")
        print(f"조회시각: {current_time}")

        # 매도호가와 매수호가를 리스트로 정리
        ask_prices = [
            (float(output.get('bond_askp1', '0')), int(output.get('askp_rsqn1', '0'))),
            (float(output.get('bond_askp2', '0')), int(output.get('askp_rsqn2', '0'))),
            (float(output.get('bond_askp3', '0')), int(output.get('askp_rsqn3', '0'))),
            (float(output.get('bond_askp4', '0')), int(output.get('askp_rsqn4', '0'))),
            (float(output.get('bond_askp5', '0')), int(output.get('askp_rsqn5', '0')))
        ]
        
        bid_prices = [
            (float(output.get('bond_bidp1', '0')), int(output.get('bidp_rsqn1', '0'))),
            (float(output.get('bond_bidp2', '0')), int(output.get('bidp_rsqn2', '0'))),
            (float(output.get('bond_bidp3', '0')), int(output.get('bidp_rsqn3', '0'))),
            (float(output.get('bond_bidp4', '0')), int(output.get('bidp_rsqn4', '0'))),
            (float(output.get('bond_bidp5', '0')), int(output.get('bidp_rsqn5', '0')))
        ]

        # 가격 내림차순 정렬
        ask_prices.sort(reverse=True, key=lambda x: x[0])
        bid_prices.sort(reverse=True, key=lambda x: x[0])

        # API 응답의 총잔량 필드 사용
        total_ask_volume = int(output.get('total_askp_rsqn', '0'))
        total_bid_volume = int(output.get('total_bidp_rsqn', '0'))

        print("\n  매도호가")
        print("-" * 50)

        # 매도호가 출력
        for (ask_price, ask_volume) in ask_prices:
            print(f"  {ask_price:9,.1f} {ask_volume:7,}")
        print(f"\n  총매도잔량: {total_ask_volume:,}")

        print("\n  매수호가")
        print("-" * 50)

        # 매수호가 출력
        for (bid_price, bid_volume) in bid_prices:
            print(f"  {bid_price:9,.1f} {bid_volume:7,}")
        print(f"\n  총매수잔량: {total_bid_volume:,}")

        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"채권 호가 조회 실패 ({symbol}): {e}")
        return False

async def main():
    """메인 함수"""
    config = load_config()
    if not config:
        print("설정 파일을 찾을 수 없습니다.")
        return
    
    api = KISApi(
        api_key=config.get("KIS_API_KEY"),
        api_secret=config.get("KIS_API_SECRET"),
        account_number=config.get("KIS_ACCOUNT_NUMBER"),
        is_paper_trading=config.get("IS_PAPER_TRADING", "True").lower() == "true"
    )
    
    try:
        if not await api.check_connection():
            print("\nAPI 연결에 실패했습니다.")
            return
            
        print("\nAPI 연결이 정상입니다.")
        print("\n=== 채권 호가 조회 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print("-" * 50)
        
        # 채권 호가 조회
        for symbol in SYMBOLS:
            await get_bond_quote(api, symbol)
            await asyncio.sleep(1)  # API 호출 간격 조절
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
