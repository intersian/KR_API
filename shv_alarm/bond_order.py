import asyncio
from kis import KISApi
from datetime import datetime

# 주문 설정
ORDER_CONFIG = {
    "symbol": "KR6150351D99",  # 종목코드
    "quantity": 1,             # 주문수량
    "price_min": 10380.0,      # 최소 주문가격
    "price_max": 10410.0       # 최대 주문가격
}

async def place_bond_order(api, symbol, quantity, price_min, price_max):
    """채권 매수 주문"""
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
        order_price = bid_price + 1  # 기본적으로 매수1호가 + 1원
        if order_price >= ask_price:  # 주문가격이 매도1호가 이상이면
            order_price = bid_price   # 매수1호가로 주문
        
        # 가격 범위 확인
        if not (price_min <= order_price <= price_max):
            print(f"\n=== {bond_name} 채권 매수 주문 취소 ===")
            print(f"주문가격이 범위를 벗어났습니다.")
            print(f"매수1호가: {bid_price:,.1f}")
            print(f"매도1호가: {ask_price:,.1f}")
            print(f"주문가격: {order_price:,.1f}")
            print(f"허용범위: {price_min:,.1f} ~ {price_max:,.1f}")
            print("-" * 50)
            return False
        
        # 매수 주문
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-bond/v1/trading/buy"
        
        body = {
            "CANO": "46805725",  # 종합계좌번호
            "ACNT_PRDT_CD": "01",  # 계좌상품코드
            "PDNO": symbol,                 # 상품번호
            "ORD_QTY2": str(quantity),      # 주문수량2
            "BOND_ORD_UNPR": str(order_price),    # 채권주문단가
            "SAMT_MKET_PTCI_YN": "N",       # 소액시장접근여부
            "BOND_RTL_MKET_YN": "N",        # 채권소매시장여부 (Y: 일반시장)
            "IDCR_STFNO": "",         # 유치자직원번호
            "MGCO_APTM_ODNO": "",  # 운용사지정주문번호
            "ORD_SVR_DVSN_CD": "0",         # 주문서버구분코드
            "CTAC_TLNO": ""  # 연락전화번호
        }
        
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await api._get_access_token()}",
            "appkey": api.api_key,
            "appsecret": api.api_secret,
            "tr_id": "TTTC0952U",  # 채권 주문
            "custtype": "P"        # 개인
        }
        
        result = await api.request("post", url, data=body, headers=headers)
        
        if result.get("rt_cd") != "0":
            raise Exception(f"주문 실패: {result.get('msg1')}")
            
        order_no = result.get("output", {}).get("ODNO", "")
        print(f"\n=== {bond_name} 채권 매수 주문 완료 ===")
        print(f"주문번호: {order_no}")
        print(f"매수1호가: {bid_price:,.1f}")
        print(f"매도1호가: {ask_price:,.1f}")
        price_msg = "(매수1호가 + 1)" if order_price > bid_price else "(매수1호가와 동일)"
        print(f"주문가격: {order_price:,.1f} {price_msg}")
        print(f"주문수량: {quantity:,}")
        print(f"허용범위: {price_min:,.1f} ~ {price_max:,.1f}")
        print("-" * 50)
        
        return True
        
    except Exception as e:
        print(f"채권 주문 실패 ({symbol}): {e}")
        return False

async def main():
    """메인 함수"""
    # API 연결
    api = KISApi(
        api_key="PSOuaQp3WA0klz1bE0kECtUpz3R8TTRqqgt8",
        api_secret="Of/V65xsBs9ehwdZRaqf4z4HHx5zP93WbNYUp0827+FpgNkMZzVEtIvLk0tWzqKTIvxapMktmJy9fSpsakpdoXUTikETIRL5VOBVOWDi84yCxRrLbiobmKHjgiThi4ERDVqFk5og/pKfKxTDT2jLsHmg+oUPwO9vs9csBkTSftmbHWcQdMQ=",
        account_number="46805725",
        is_paper_trading=False
    )
    
    try:
        # 채권 매수 주문
        await place_bond_order(
            api,
            ORDER_CONFIG["symbol"],
            ORDER_CONFIG["quantity"],
            ORDER_CONFIG["price_min"],
            ORDER_CONFIG["price_max"]
        )
            
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main())
