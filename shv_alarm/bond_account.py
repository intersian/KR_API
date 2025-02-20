import asyncio
from kis import KISApi
from datetime import datetime

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

async def get_bond_balance(api):
    """채권 잔고 조회"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-balance"
        
        params = {
            "CANO": api.account_number[:8],           # 종합계좌번호
            "ACNT_PRDT_CD": api.account_number[8:],  # 계좌상품코드
            "INQR_CNDT": "00",
            "PDNO": "",
            "BUY_DT": "",
            "CTX_AREA_FK200": "",         # 연속조회검색조건
            "CTX_AREA_NK200": ""          # 연속조회키
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "CTSC8407R",         # 채권 잔고 조회
            "custtype": "P"               # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output = result.get("output", [])  # 채권 잔고 목록
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n=== 채권 잔고 현황 ({current_time}) ===")
        print("-" * 50)
        
        if not output:
            print("보유중인 채권이 없습니다.")
            print("-" * 50)
            return True
            
        # 보유 채권 목록 출력
        for bond in output:
            # 요약 정보 출력
            print(f"종목명: {bond.get('prdt_name', '-')}")                       # 상품명
            print(f"매수일자: {bond.get('buy_dt', '-')}")                        # 매수일자
            print(f"잔고수량: {int(bond.get('cblc_qty', '0')):,}")              # 잔고수량
            print(f"주문가능수량: {int(bond.get('ord_psbl_qty', '0')):,}")      # 주문가능수량
        
        return True
        
    except Exception as e:
        print(f"잔고 조회 실패: {e}")
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
    
    try:
        # 채권 잔고 조회
        await get_bond_balance(api)
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 