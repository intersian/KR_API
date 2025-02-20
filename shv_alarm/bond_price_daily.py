import asyncio
from kis import KISApi
from datetime import datetime, timedelta
import json

# 모니터링할 채권 종목 리스트
SYMBOLS = [
    "KR6103161EB6",  # 국고채권03125-2409
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

async def get_bond_daily(api, symbol):
    """채권 일봉 데이터 조회"""
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
        
        # 일봉 데이터 조회
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-daily-price"
        
        # 조회 기간 설정 (최근 5일)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)
        
        params = {
            "FID_COND_MRKT_DIV_CODE": symbol,  # 종목코드
            "FID_INPUT_ISCD": symbol,          # 종목코드
            "FID_INPUT_DATE_1": start_date.strftime('%Y%m%d'),  # 시작일
            "FID_INPUT_DATE_2": end_date.strftime('%Y%m%d'),    # 종료일
            "FID_PERIOD_DIV_CODE": "D"         # 기간구분: D(일)
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "FHKBJ77330100",  # 채권 일별시세 조회
            "custtype": "P"            # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output_list = result.get("output", [])
        
        print(f"\n=== {bond_name} 채권 일별시세 ===")
        print("-" * 50)
        print("  일자      시가    고가    저가    종가    거래량")
        print("-" * 50)
        
        for data in output_list:
            date = data.get('stck_bsop_date', '-')
            open_price = float(data.get('stck_oprc', '0'))
            high_price = float(data.get('stck_hgpr', '0'))
            low_price = float(data.get('stck_lwpr', '0'))
            close_price = float(data.get('stck_clpr', '0'))
            volume = int(data.get('acml_vol', '0'))
            
            print(f"  {date} {open_price:7,.1f} {high_price:7,.1f} {low_price:7,.1f} {close_price:7,.1f} {volume:8,}")
            
        print("-" * 50)
        return True
        
    except Exception as e:
        print(f"채권 일봉 조회 실패 ({symbol}): {e}")
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
        print("\n=== 채권 일봉 조회 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print("-" * 50)
        
        # 채권 일봉 조회
        for symbol in SYMBOLS:
            await get_bond_daily(api, symbol)
            await asyncio.sleep(1)  # API 호출 간격 조절
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 