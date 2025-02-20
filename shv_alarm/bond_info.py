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
                # 빈 줄이나 주석 무시
                if not line or line.startswith('#'):
                    continue
                # key=value 형식만 처리
                if '=' in line:
                    key, value = line.split('=', 1)
                    # 주석이 있는 경우 주석 제거
                    if '#' in value:
                        value = value.split('#')[0]
                    config[key.strip()] = value.strip()
        return config
    except Exception as e:
        print(f"설정 파일 로드 중 오류 발생: {e}")
        return {}

async def get_bond_price(api, symbol):
    """채권 현재가 조회"""
    try:
        # 채권 현재가 조회
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-price"
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 시장구분: J(채권), B(주식관련사채)
            "FID_INPUT_ISCD": symbol,        # 종목코드
            "FID_DIV_CLS_CODE": "00"        # 권리유형코드: 00(보통)
        }
        
        headers = {
            "tr_id": "FHKST03010100",  # 채권 현재가 조회
            "custtype": "P"            # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        print("\n=== API 응답 원본 데이터 ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("-" * 50)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output = result.get("output", {})
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n=== {symbol} 채권 시세 정보 ===")
        print(f"조회시각: {current_time}")
        print(f"종목명: {output.get('prdt_name', '-')}")
        print(f"현재가: {float(output.get('last', '0')):,.3f}")
        print(f"전일대비: {float(output.get('diff', '0')):+,.3f}")
        print(f"매수호가: {float(output.get('bid', '0')):,.3f}")
        print(f"매도호가: {float(output.get('ask', '0')):,.3f}")
        print(f"거래량: {int(output.get('acml_vol', '0')):,}")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"채권 시세 조회 실패 ({symbol}): {e}")
        return False

async def get_bond_info(api, symbol):
    """채권 발행정보 조회"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/issue-info"
        
        params = {
            "PDNO": symbol,                 # 채권종목코드
            "PRDT_TYPE_CD": "302"          # 상품유형코드 (302: 채권)
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "CTPF1101R",  # 채권 발행정보 조회
            "custtype": "P"        # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output = result.get("output", {})
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n=== {symbol} 채권 발행정보 ===")
        print(f"조회시각: {current_time}")
        print(f"종목코드: {output.get('pdno', '-')}")
        print(f"종목명: {output.get('prdt_name', '-')}")
        print(f"발행금액: {int(output.get('issu_amt', '0')):,}원")
        print(f"이표채: {output.get('int_dfrm_mcnt', '-')}개월")
        print(f"표면금리: {float(output.get('srfc_inrt', '0')):,.3f}%")
        print(f"발행일: {output.get('issu_dt', '-')}")
        print(f"상장일: {output.get('lstg_dt', '-')}")
        print(f"만기일: {output.get('expd_dt', '-')}")
        print(f"직전이자지급일: {output.get('rgbf_int_dfrm_dt', '-')}")
        print(f"차기이자지급일: {output.get('nxtm_int_dfrm_dt', '-')}")
        print(f"콜만기: {output.get('sq1_clop_ecis_opng_dt', '-')}")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"채권 발행정보 조회 실패 ({symbol}): {e}")
        return False

async def main():
    """메인 함수"""
    # 설정 로드
    config = load_config()
    if not config:
        print("설정 파일을 찾을 수 없습니다.")
        return
    
    # API 연결
    api = KISApi(
        api_key=config.get("KIS_API_KEY"),
        api_secret=config.get("KIS_API_SECRET"),
        account_number=config.get("KIS_ACCOUNT_NUMBER"),
        is_paper_trading=config.get("IS_PAPER_TRADING", "True").lower() == "true"
    )
    
    # API 연결 확인
    try:
        if not await api.check_connection():
            print("\nAPI 연결에 실패했습니다.")
            return
            
        print("\nAPI 연결이 정상입니다.")
        print("\n=== 채권 발행정보 조회 시작 ===")
        print(f"대상 종목: {', '.join(SYMBOLS)}")
        print("-" * 50)
        
        # 채권 발행정보 조회
        for symbol in SYMBOLS:
            await get_bond_info(api, symbol)
            await asyncio.sleep(1)  # API 호출 간격 조절
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
