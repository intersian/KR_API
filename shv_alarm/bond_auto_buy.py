import asyncio
from kis import KISApi
from datetime import datetime
import signal

# API 설정
API_KEY = "PSOuaQp3WA0klz1bE0kECtUpz3R8TTRqqgt8"
API_SECRET = "Of/V65xsBs9ehwdZRaqf4z4HHx5zP93WbNYUp0827+FpgNkMZzVEtIvLk0tWzqKTIvxapMktmJy9fSpsakpdoXUTikETIRL5VOBVOWDi84yCxRrLbiobmKHjgiThi4ERDVqFk5og/pKfKxTDT2jLsHmg+oUPwO9vs9csBkTSftmbHWcQdMQ="
ACCOUNT_NUMBER = "4680572501"
IS_PAPER_TRADING = False

# 모니터링 설정
INTERVAL = 30  # 조회 간격 (초)

# 목표 설정
TARGET_BOND = {
    "symbol": "KR6150351D99",  # 목표 종목코드
    "target_quantity": 10,     # 목표 보유수량
    "order_quantity": 1,       # 1회 매수수량
    "min_price": 10380.0,      # 최소 매수가격
    "max_price": 10410.0       # 최대 매수가격
}

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
            
        # 목표 종목의 보유수량 확인
        current_quantity = 0
        
        # 보유 채권 목록 출력
        for bond in output:
            # 요약 정보 출력
            print(f"종목명: {bond.get('prdt_name', '-')}")                       # 상품명
            print(f"매수일자: {bond.get('buy_dt', '-')}")                        # 매수일자
            print(f"잔고수량: {int(bond.get('cblc_qty', '0')):,}")              # 잔고수량
            print(f"주문가능수량: {int(bond.get('ord_psbl_qty', '0')):,}")      # 주문가능수량
            print("-" * 50)
            
            # 목표 종목이면 수량 합산
            if bond.get('pdno') == TARGET_BOND["symbol"]:
                current_quantity += int(bond.get('cblc_qty', '0'))
        
        # 목표 수량 달성 확인 (TARGET_BOND의 target_quantity 사용)
        if current_quantity >= TARGET_BOND["target_quantity"]:
            print("\n=== 자동 매수 완료 ===")
            print(f"목표 종목의 보유수량({current_quantity:,})이 목표수량({TARGET_BOND['target_quantity']:,})에 도달했습니다.")
            print("프로그램을 종료합니다.")
            print("-" * 50)
            raise SystemExit  # 프로그램 종료
        
        return True
        
    except SystemExit:
        raise  # 시스템 종료 예외는 상위로 전달
    except Exception as e:
        print(f"잔고 조회 실패: {e}")
        return False

async def get_bond_name(api, symbol):
    """채권 종목명 조회"""
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
        return result.get("output", {}).get("prdt_name", "-")
        
    except Exception:
        return "-"

async def place_bond_order(api, symbol, quantity, price):
    """채권 매수 주문"""
    try:
        # 호가 조회로 매수1호가, 매도1호가 확인
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
        ask_price = float(output.get('bond_askp1', '0'))  # 매도1호가
        
        # 주문가격 결정
        order_price = price  # 기본적으로 전달받은 가격 사용
        price_msg = ""
        
        if order_price >= ask_price:  # 주문가격이 매도1호가 이상이면
            order_price = bid_price   # 매수1호가로 주문
            price_msg = "(매도1호가 이상으로 매수1호가로 조정)"
        
        # 매수 주문
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/buy"
        
        body = {
            "CANO": api.account_number[:8],           # 종합계좌번호
            "ACNT_PRDT_CD": api.account_number[8:],  # 계좌상품코드
            "PDNO": symbol,                 # 종목코드
            "ORD_QTY2": str(quantity),      # 주문수량2
            "BOND_ORD_UNPR": str(order_price),  # 채권주문단가
            "SAMT_MKET_PTCI_YN": "N",       # 소액시장접근여부
            "BOND_RTL_MKET_YN": "N",        # 채권소매시장여부
            "IDCR_STFNO": "",               # 유치자직원번호
            "MGCO_APTM_ODNO": "",           # 운용사지정주문번호
            "ORD_SVR_DVSN_CD": "0",         # 주문서버구분코드
            "CTAC_TLNO": ""                 # 연락전화번호
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "TTTC0952U",  # 채권 매수 주문
            "custtype": "P"        # 개인
        }
        
        result = await api.request("post", url, data=body, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"주문 실패: {result.get('msg1')}")
            
        print(f"\n매수 주문 완료")
        print(f"종목코드: {symbol}")
        print(f"매수1호가: {bid_price:,.1f}")
        print(f"매도1호가: {ask_price:,.1f}")
        print(f"주문가격: {order_price:,.1f} {price_msg}")
        print(f"주문수량: {quantity:,}")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"매수 주문 실패: {e}")
        return False

async def check_and_order(api):
    """잔고 확인 및 매수 주문"""
    try:
        # 호가 조회로 매수1호가 확인
        quote_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/quotations/inquire-asking-price"
        quote_params = {
            "FID_COND_MRKT_DIV_CODE": "B",  # 시장구분: B(채권)
            "FID_INPUT_ISCD": TARGET_BOND["symbol"],  # 종목코드
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
        order_price = bid_price + 1  # 매수1호가 + 1원
        
        # 주문 가격이 허용 범위 내인지 확인
        if not (TARGET_BOND["min_price"] <= order_price <= TARGET_BOND["max_price"]):
            print(f"\n주문 가격({order_price:,.1f})이 허용 범위를 벗어났습니다.")
            print(f"허용 범위: {TARGET_BOND['min_price']:,.1f} ~ {TARGET_BOND['max_price']:,.1f}")
            print("-" * 50)
            return False
        
        # 매수 주문 실행
        await place_bond_order(
            api,
            TARGET_BOND["symbol"],
            TARGET_BOND["order_quantity"],
            order_price
        )
        
        return True
        
    except Exception as e:
        print(f"주문 처리 실패: {e}")
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
            "CTX_AREA_FK200": "",         # 연속조회검색조건
            "CTX_AREA_NK200": ""          # 연속조회키
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
            
            # 잔고 확인 후 필요시 매수 주문
            balance_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-balance"
            balance_params = {
                "CANO": api.account_number[:8],
                "ACNT_PRDT_CD": api.account_number[8:],
                "INQR_CNDT": "00",
                "PDNO": "",
                "BUY_DT": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            balance_headers = {  # 잔고 조회용 헤더 추가
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": "CTSC8407R",  # 채권 잔고 조회
                "custtype": "P"        # 개인
            }
            
            balance_result = await api.request("get", balance_url, params=balance_params, headers=balance_headers)
            
            if balance_result.get("rt_cd") == "0":
                current_quantity = 0
                for bond in balance_result.get("output", []):
                    if bond.get("pdno") == TARGET_BOND["symbol"]:
                        current_quantity = int(bond.get("cblc_qty", "0"))
                        break
                
                if current_quantity < TARGET_BOND["target_quantity"]:
                    print(f"\n현재 보유수량({current_quantity:,})이 목표수량({TARGET_BOND['target_quantity']:,})보다 적습니다.")
                    print("매수 주문을 시도합니다.")
                    await check_and_order(api)
            
            return True
            
        for order in output_list:
            # 주문시각 포맷팅 (HHMMSS -> HH:MM:SS)
            ord_time = order.get('ord_tmd', '-')
            if ord_time != '-':
                ord_time = f"{ord_time[:2]}:{ord_time[2:4]}:{ord_time[4:]}"
            
            order_no = order.get('odno', '-')
            symbol = order.get('pdno', '-')
            current_price = float(order.get('bond_ord_unpr', '0'))
            
            # 종목명 조회
            bond_name = await get_bond_name(api, symbol)
            
            print(f"종목명: {bond_name}")
            print(f"주문번호: {order_no}")
            print(f"주문수량: {int(order.get('ord_qty', '0')):,}")
            print(f"주문단가: {current_price:,.1f}")
            print(f"주문시각: {ord_time}")
            print(f"총체결수량: {int(order.get('tot_ccld_qty', '0')):,}")
            print(f"정정가능수량: {int(order.get('ord_psbl_qty', '0')):,}")
            
            # 목표 종목의 미체결 주문이면 정정 검토
            if (symbol == TARGET_BOND["symbol"] and 
                int(order.get('ord_psbl_qty', '0')) > 0):
                print(f"목표 종목 미체결 주문 발견 - 정정 검토")
                await modify_bond_order(api, order_no, symbol, current_price)
            
            print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"주문 조회 실패: {e}")
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

async def monitor_and_order(api):
    """잔고 확인 및 주문 처리 통합 프로세스"""
    try:
        while True:
            # 1. 잔고 조회
            balance_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-balance"
            balance_params = {
                "CANO": api.account_number[:8],
                "ACNT_PRDT_CD": api.account_number[8:],
                "INQR_CNDT": "00",
                "PDNO": "",
                "BUY_DT": "",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": ""
            }
            
            headers = {
                "content-type": "application/json; charset=utf-8",
                "authorization": f"Bearer {await api._get_access_token()}",
                "appkey": api.api_key,
                "appsecret": api.api_secret,
                "tr_id": "CTSC0343R",
                "custtype": "P"
            }
            
            balance_result = await api.request("get", balance_url, params=balance_params, headers=headers)
            
            if balance_result.get("rt_cd") != "0":
                raise Exception(f"잔고 조회 실패: {balance_result.get('msg1')}")
            
            # 2. 현재 보유수량 확인
            current_quantity = 0
            for bond in balance_result.get("output", []):
                if bond.get("pdno") == TARGET_BOND["symbol"]:
                    current_quantity = int(bond.get("cblc_qty", "0"))
                    break
            
            current_time = datetime.now().strftime('%H:%M:%S')
            print(f"\n=== 채권 잔고 확인 ({current_time}) ===")
            print(f"현재 보유수량: {current_quantity:,}")
            print(f"목표 보유수량: {TARGET_BOND['target_quantity']:,}")
            print("-" * 50)
            
            # 3. 목표 수량 달성 확인
            if current_quantity >= TARGET_BOND["target_quantity"]:
                print(f"\n목표 수량 달성! 모니터링을 종료합니다.")
                return True
            
            # 4. 미달성 시 주문 처리
            # 4-1. 정정 가능한 주문 조회
            orders_url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/inquire-psbl-rvsecncl"
            orders_result = await api.request("get", orders_url, params=params, headers=headers)
            
            if orders_result.get("rt_cd") != "0":
                raise Exception(f"주문 조회 실패: {orders_result.get('msg1')}")
            
            output_list = orders_result.get("output", [])
            
            # 4-2. 주문 처리 로직
            if not output_list:
                print("정정/취소 가능한 주문이 없습니다. 신규 매수를 시도합니다.")
                await check_and_order(api)
            else:
                for order in output_list:
                    if (order.get('pdno') == TARGET_BOND["symbol"] and 
                        int(order.get('ord_psbl_qty', '0')) > 0):
                        print("미체결 주문 발견 - 정정 검토")
                        order_no = order.get('odno', '-')
                        current_price = float(order.get('bond_ord_unpr', '0'))
                        await modify_bond_order(api, order_no, TARGET_BOND["symbol"], current_price)
            
            # 5. 대기
            await asyncio.sleep(INTERVAL)
            
    except Exception as e:
        print(f"모니터링 오류: {e}")
        return False

# 메인 함수 수정
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
        result = await monitor_and_order(api)
        if result:
            print("\n=== 프로그램이 정상 종료되었습니다 ===")
    except KeyboardInterrupt:
        print("\n\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 