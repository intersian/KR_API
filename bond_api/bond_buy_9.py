import asyncio
from datetime import datetime
from bond_api import BondApi, TokenManager, get_bond_name

# API 설정
API_KEY = "PSOuaQp3WA0klz1bE0kECtUpz3R8TTRqqgt8"
API_SECRET = "Of/V65xsBs9ehwdZRaqf4z4HHx5zP93WbNYUp0827+FpgNkMZzVEtIvLk0tWzqKTIvxapMktmJy9fSpsakpdoXUTikETIRL5VOBVOWDi84yCxRrLbiobmKHjgiThi4ERDVqFk5og/pKfKxTDT2jLsHmg+oUPwO9vs9csBkTSftmbHWcQdMQ="
ACCOUNT = "4680572501"
IS_PAPER = False

# 모니터링 설정
TARGET_SYMBOL = "KR6003492E24"  # 대한항공106-2
TARGET_BALANCE = 1  # 목표 보유수량
INTERVAL = 5  # 조회 간격 (초)
IS_RUNNING = True  # 실행 상태

# 매수 설정
ORDER_QUANTITY = 1  # 1회 매수 수량
MIN_PRICE = 10000.00  # 최소 매수가격
MAX_PRICE = 10290.00  # 최대 매수가격

async def check_orders_and_quote(api):
    """정정취소가능 주문 조회 및 호가 확인"""
    try:
        # 1. 미체결 주문 조회
        orders = await api.get_bond_orders()
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n[{current_time}] 미체결 주문 조회:")
        
        # 목표 종목 주문 필터링
        target_orders = []
        if orders:
            for order in orders:
                if order.get('pdno') == TARGET_SYMBOL:
                    target_orders.append(order)
        
        # 2. 주문이 있는 경우 호가 확인
        if target_orders:
            # 호가 조회
            quote = await api.get_bond_quote(TARGET_SYMBOL)
            bid_price = float(quote.get('bond_bidp1', '0'))  # 매수1호가
            suggested_price = bid_price + 1  # 매수1호가 + 1원
            
            # 주문 정보 출력 및 호가 비교
            for order in target_orders:
                order_no = order.get('odno', '-')
                order_qty = int(order.get('ord_qty', '0'))
                filled_qty = int(order.get('tot_ccld_qty', '0'))
                remain_qty = int(order.get('ord_psbl_qty', '0'))
                order_price = float(order.get('bond_ord_unpr', '0'))
                
                print(f"주문번호: {order_no}")
                print(f"주문수량: {order_qty:,}")
                print(f"체결수량: {filled_qty:,}")
                print(f"미체결수량: {remain_qty:,}")
                print(f"주문단가: {order_price:,.2f}")
                print(f"매수1호가: {bid_price:,.2f}")
                print(f"제안 매수가격: {suggested_price:,.2f}")
                
                # 호가 비교 - 정확한 가격 일치 확인
                price_diff = abs(order_price - bid_price)
                if price_diff == 0:  # 가격이 정확히 일치하는 경우
                    print("주문가격이 매수1호가와 정확히 일치합니다. 정정이 필요하지 않습니다.")
                else:
                    print(f"주문가격과 매수1호가의 차이가 {price_diff:,.2f}원입니다.")
                    # 주문가격이 최대 매수가격과 같은지 확인
                    if order_price == MAX_PRICE:  # 정확히 일치하는 경우
                        print(f"주문가격이 최대 매수가격({MAX_PRICE:,.2f})과 정확히 일치합니다.")
                        print("정정을 보류하고 현재 주문을 유지합니다.")
                    else:
                        # 주문가격보다 높은 매수호가들의 잔량 합계 계산
                        higher_bids_qty = 0
                        for i in range(1, 6):  # 매수1~5호가 확인
                            bid_price_key = f'bond_bidp{i}'  # bond_bidp1 ~ bond_bidp5
                            bid_qty_key = f'bidp_rsqn{i}'    # bidp_rsqn1 ~ bidp_rsqn5
                            current_bid = float(quote.get(bid_price_key, '0'))
                            if current_bid > order_price:  # 주문가격보다 높은 호가만
                                higher_bids_qty += int(quote.get(bid_qty_key, '0'))
                        
                        print(f"주문가격보다 높은 매수호가들의 잔량 합계: {higher_bids_qty:,}")
                        
                        if higher_bids_qty <= 1000:
                            print("높은 매수호가들의 잔량이 1000 이하입니다.")
                            print("정정을 보류하고 현재 주문을 유지합니다.")
                        else:
                            print("정정이 필요합니다.")
                            # 매수1호가 + 1원이 매수범위를 초과하는지 확인
                            if suggested_price > MAX_PRICE:
                                print(f"제안 매수가격이 최대 매수가격({MAX_PRICE:,.2f})을 초과합니다.")
                                print(f"최대 매수가격으로 정정을 시도합니다.")
                                # 정정 주문 요청
                                try:
                                    modify_result = await api.modify_bond_order(
                                        order_no=order_no,
                                        price=MAX_PRICE,
                                        quantity=remain_qty
                                    )
                                    print(f"정정 주문 결과: {modify_result}")
                                except Exception as e:
                                    print(f"정정 주문 실패: {str(e)}")
                            else:
                                print(f"제안 매수가격이 매수 범위 내에 있습니다.")
                                print(f"매수1호가+1원으로 정정을 시도합니다.")
                                # 정정 주문 요청
                                try:
                                    modify_result = await api.modify_bond_order(
                                        order_no=order_no,
                                        price=suggested_price,
                                        quantity=remain_qty
                                    )
                                    print(f"정정 주문 결과: {modify_result}")
                                except Exception as e:
                                    print(f"정정 주문 실패: {str(e)}")
                print("-" * 30)
        else:
            print(f"목표 종목({TARGET_SYMBOL})의 미체결 주문이 없습니다.")
            
            # 호가 조회 및 매수 시도
            quote = await api.get_bond_quote(TARGET_SYMBOL)
            bid_price = float(quote.get('bond_bidp1', '0'))  # 매수1호가
            ask_price = float(quote.get('bond_askp1', '0'))  # 매도1호가
            suggested_price = bid_price + 1  # 매수1호가 + 1원
            
            print(f"매수1호가: {bid_price:,.2f}")
            print(f"매도1호가: {ask_price:,.2f}")
            print(f"제안 매수가격: {suggested_price:,.2f}")
            
            # 매수 가격 결정 로직
            if suggested_price > MAX_PRICE:
                print(f"제안 매수가격이 최대 매수가격({MAX_PRICE:,.2f})을 초과합니다.")
                print(f"최대 매수가격으로 주문을 시도합니다.")
                order_price = MAX_PRICE
            elif suggested_price >= ask_price:
                print(f"제안 매수가격({suggested_price:,.2f})이 매도1호가({ask_price:,.2f}) 이상입니다.")
                print(f"매수1호가로 주문을 시도합니다.")
                order_price = bid_price
            elif MIN_PRICE <= suggested_price <= MAX_PRICE and suggested_price < ask_price:
                print(f"제안 매수가격이 매수 범위 내에 있고 매도1호가 미만입니다.")
                print(f"매수1호가+1원으로 주문을 시도합니다.")
                order_price = suggested_price
            else:
                print(f"주문 조건에 맞지 않아 주문을 보류합니다.")
                return
            
            # 매수 주문 요청
            try:
                order_result = await api.place_bond_order(
                    symbol=TARGET_SYMBOL,
                    price=order_price,
                    quantity=ORDER_QUANTITY,
                )
                print(f"주문 결과: {order_result}")
            except Exception as e:
                print(f"주문 실패: {str(e)}")
            
    except Exception as e:
        print(f"주문 조회 실패: {str(e)}")

async def monitor_balance():
    """잔고 모니터링 메인 함수"""
    try:
        # 토큰 매니저 초기화
        token_manager = TokenManager()
        
        # API 객체 생성
        api = BondApi(
            api_key=API_KEY,
            api_secret=API_SECRET,
            account_number=ACCOUNT,
            is_paper=IS_PAPER
        )
        
        # 저장된 토큰 확인
        saved_token = token_manager.load_token(API_KEY)
        if saved_token:
            print("\n저장된 토큰을 재사용합니다.")
        else:
            # 새로운 토큰 발급 및 저장
            token = await api._get_access_token()
            token_manager.save_token(API_KEY, token)
            print("\n새로운 토큰이 발급되었습니다.")
        
        # 목표 종목명 조회
        target_name = await get_bond_name(api, TARGET_SYMBOL)
        print("\n=== 채권 잔고 모니터링 시작 ===")
        print(f"대상 종목: {target_name} ({TARGET_SYMBOL})")
        print(f"목표 수량: {TARGET_BALANCE:,}")
        print(f"1회 매수수량: {ORDER_QUANTITY:,}")
        print(f"매수가격 범위: {MIN_PRICE:,.2f} ~ {MAX_PRICE:,.2f}")
        print(f"조회 간격: {INTERVAL}초")
        print("-" * 50)
        
        global IS_RUNNING
        while IS_RUNNING:
            try:
                # 잔고 조회
                balance = await api.get_bond_balance()
                current_time = datetime.now().strftime('%H:%M:%S')
                
                print(f"\n[{current_time}] 잔고 조회 결과:")
                
                # 목표 종목 잔고 필터링
                target_balance = None
                if balance:
                    for bond in balance:
                        if bond.get('pdno') == TARGET_SYMBOL:
                            target_balance = bond
                            break
                
                # 결과 출력 및 목표 달성 확인
                if target_balance:
                    current_quantity = int(target_balance.get('cblc_qty', '0'))
                    print(f"종목명: {target_balance.get('prdt_name', '-')}")
                    print(f"보유수량: {current_quantity:,}")
                    print("-" * 30)
                    
                    # 목표 수량 달성 확인
                    if current_quantity >= TARGET_BALANCE:
                        print(f"\n목표 수량 달성! (보유: {current_quantity:,} / 목표: {TARGET_BALANCE:,})")
                        return True
                else:
                    print(f"목표 종목({TARGET_SYMBOL})의 보유 잔고가 없습니다.")
                
                # 미체결 주문 조회 및 호가 확인 (목표 미달성 시)
                await check_orders_and_quote(api)
                
                # 대기
                await asyncio.sleep(INTERVAL)
                
            except Exception as e:
                print(f"\n잔고 조회 중 오류 발생: {str(e)}")
                await asyncio.sleep(INTERVAL)
            
    except Exception as e:
        print(f"\n모니터링 오류: {e}")
        return False
    finally:
        print("\n=== 모니터링이 종료되었습니다 ===")

async def main():
    """메인 함수"""
    try:
        result = await monitor_balance()
        if result:
            print("\n=== 목표 달성으로 프로그램이 종료되었습니다 ===")
        else:
            print("\n=== 오류로 인해 프로그램이 종료되었습니다 ===")
    except KeyboardInterrupt:
        global IS_RUNNING
        IS_RUNNING = False
        print("\n\n사용자에 의해 프로그램이 종료되었습니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 