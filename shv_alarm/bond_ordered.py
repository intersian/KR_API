import asyncio
from kis import KISApi
from datetime import datetime

# 모니터링할 채권 종목 리스트
TARGET_SYMBOL = "KR6150351D99"  # 취소할 채권 종목코드

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

async def cancel_bond_order(api, order_no):
    """채권 주문 취소"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/order-rvsecncl"
        
        body = {
            "CANO": api.account_number[:8],           # 종합계좌번호
            "ACNT_PRDT_CD": api.account_number[8:],  # 계좌상품코드
            "PDNO": TARGET_SYMBOL,         # 종목코드
            "ORGN_ODNO": order_no,        # 원주문번호
            "ORD_QTY2": "0",              # 주문수량2 (취소 시 0)
            "BOND_ORD_UNPR": "0",         # 채권주문단가 (취소 시 0)
            "QTY_ALL_ORD_YN": "Y",        # 주문수량전체여부
            "RVSE_CNCL_DVSN_CD": "02",    # 정정취소구분코드 (02: 취소)
            "MGCO_APTM_ODNO": "",         # 운용사지정주문번호
            "ORD_SVR_DVSN_CD": "0",       # 주문서버구분코드
            "CTAC_TLNO": "",              # 연락전화번호
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "TTTC0953U",         # 채권 주문 취소
            "custtype": "P"               # 개인
        }
        
        result = await api.request("post", url, data=body, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"취소 실패: {result.get('msg1')}")
            
        print(f"\n주문번호 {order_no} 취소 완료")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"주문 취소 실패: {e}")
        return False

async def modify_bond_order(api, order_no, symbol, current_price):
    """채권 주문 정정"""
    try:
        # 호가 조회로 매수1호가 확인
        quote_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-asking-price"
        quote_params = {
            "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
            "FID_INPUT_ISCD": symbol,        # 종목코드
        }
        quote_headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "FHKBJ773401C0",  # 채권 호가 조회
            "custtype": "P"            # 개인
        }
        
        quote_result = await api.request("get", quote_url, params=quote_params, headers=quote_headers)
        
        if quote_result.get("rt_cd") != "0":
            raise Exception(f"호가 조회 실패: {quote_result.get('msg1')}")
            
        output = quote_result.get("output", {})
        bid_price = float(output.get('bond_bidp1', '0'))  # 매수1호가
        
        # 현재 주문가격이 매수1호가와 같으면 정정하지 않음
        if current_price == bid_price:
            print(f"\n주문번호 {order_no}는 이미 매수1호가({bid_price:,.1f})와 동일합니다.")
            print("-" * 50)
            return True
            
        new_price = bid_price + 1  # 매수1호가 + 1원
        
        # 정정 주문
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/order-rvsecncl"
        
        body = {
            "CANO": api.account_number[:8],           # 종합계좌번호
            "ACNT_PRDT_CD": api.account_number[8:],  # 계좌상품코드
            "PDNO": symbol,              # 종목코드
            "ORGN_ODNO": order_no,       # 원주문번호
            "RVSE_CNCL_DVSN_CD": "01",   # 정정취소구분코드 (01: 정정)
            "ORD_QTY2": "0",             # 주문수량2 (0: 전량)
            "BOND_ORD_UNPR": str(new_price),  # 채권주문단가 (매수1호가 + 1)
            "QTY_ALL_ORD_YN": "Y",       # 주문수량전체여부
            "MGCO_APTM_ODNO": "",        # 운용사지정주문번호
            "ORD_SVR_DVSN_CD": "0",      # 주문서버구분코드
            "CTAC_TLNO": "",             # 연락전화번호
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "TTTC0953U",         # 채권 주문 정정
            "custtype": "P"               # 개인
        }
        
        result = await api.request("post", url, data=body, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"정정 실패: {result.get('msg1')}")
            
        print(f"\n주문번호 {order_no} 정정 완료")
        print(f"기존 매수1호가: {bid_price:,.1f}")
        print(f"정정 주문가격: {new_price:,.1f}")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"주문 정정 실패: {e}")
        return False

async def get_bond_orders(api):
    """정정취소가능한 채권 주문 조회"""
    try:
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl"
        
        params = {
            "CANO": api.account_number[:8],           # 종합계좌번호
            "ACNT_PRDT_CD": api.account_number[8:],  # 계좌상품코드
            "ORD_DT": "",
            "ODNO": "",
            "CTX_AREA_FK200": "",         # 연속조회검색조건200
            "CTX_AREA_NK200": ""          # 연속조회키200
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "CTSC8035R",         # 채권 주문 조회
            "custtype": "P"               # 개인
        }
        
        result = await api.request("get", url, params=params, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"조회 실패: {result.get('msg1')}")
            
        output_list = result.get("output", [])
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n=== 채권 주문 내역 조회 ({current_time}) ===")
        print("-" * 50)
        
        if not output_list:
            print("정정/취소 가능한 주문이 없습니다.")
            print("-" * 50)
            return True
            
        for order in output_list:
            # 주문시각 포맷팅 (HHMMSS -> HH:MM:SS)
            ord_time = order.get('ord_tmd', '-')
            if ord_time != '-':
                ord_time = f"{ord_time[:2]}:{ord_time[2:4]}:{ord_time[4:]}"
            
            order_no = order.get('odno', '-')
            symbol = order.get('pdno', '-')
            current_price = float(order.get('bond_ord_unpr', '0'))
            
            print(f"주문번호: {order_no}")
            print(f"종목코드: {symbol}")
            print(f"주문수량: {int(order.get('ord_qty', '0')):,}")
            print(f"주문단가: {current_price:,.1f}")
            print(f"주문시각: {ord_time}")
            print(f"총체결수량: {int(order.get('tot_ccld_qty', '0')):,}")
            print(f"정정가능수량: {int(order.get('ord_psbl_qty', '0')):,}")
            print("-" * 50)
            
            # 미체결 수량이 있고 특정 종목인 경우 정정 주문
            if (int(order.get('ord_psbl_qty', '0')) > 0 and 
                symbol == TARGET_SYMBOL):  # 상단에 정의된 종목코드 사용
                print(f"미체결 주문 발견 - 정정 검토")
                await modify_bond_order(api, order_no, symbol, current_price)
        
        return True
        
    except Exception as e:
        print(f"주문 조회 실패: {e}")
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
        # 채권 주문 조회 및 취소
        await get_bond_orders(api)
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
