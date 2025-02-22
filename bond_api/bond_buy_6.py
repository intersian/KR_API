#1 채권 목표 종목 잔고 모니터링 기능
#2 목표 잔고 도달 시 자동 종료 기능
#3 목표 잔고 미도달 시 미체결 주문 조회 기능 추가
#4 정정 가능 주문이 있을때 주문가가 매수1호가와 같은지 확인하여 같은 경우 패스
#5 주문가격이 매수1호가와 다른 경우 매수1호가 +1원이 목표 가격 범위 내일 때만 정정
#6 매수1호가 +1원이 매도1호가 이상이면 정정하지 않음

import asyncio
from datetime import datetime
from bond_api import BondApi, TokenManager, get_bond_name

# API 설정
API_KEY = "PSOuaQp3WA0klz1bE0kECtUpz3R8TTRqqgt8"
API_SECRET = "Of/V65xsBs9ehwdZRaqf4z4HHx5zP93WbNYUp0827+FpgNkMZzVEtIvLk0tWzqKTIvxapMktmJy9fSpsakpdoXUTikETIRL5VOBVOWDi84yCxRrLbiobmKHjgiThi4ERDVqFk5og/pKfKxTDT2jLsHmg+oUPwO9vs9csBkTSftmbHWcQdMQ="
ACCOUNT = "4680572501"
IS_PAPER = False

# 모니터링 설정
TARGET_SYMBOL = "KR6103161EB6"  # 국고채권03750-2503
TARGET_BALANCE = 1  # 목표 보유수량
INTERVAL = 5  # 조회 간격 (초)
IS_RUNNING = True  # 실행 상태

# 목표 가격 범위 설정
MIN_PRICE = 99.00  # 최소 매수 가격
MAX_PRICE = 100.00  # 최대 매수 가격

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
            bid_price = float(quote.get('bond_bidp1', '0'))  # 채권 매수1호가
            ask_price = float(quote.get('bond_askp1', '0'))  # 채권 매도1호가
            
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
                print(f"매도1호가: {ask_price:,.2f}")
                
                # 호가 비교 및 주문 정정
                if order_price == bid_price:  # 가격이 정확히 일치하는 경우만 패스
                    print("주문가격이 매수1호가와 정확히 일치하여 정정이 필요하지 않습니다.")
                else:
                    new_price = bid_price + 1  # 매수1호가 + 1원
                    
                    # 목표 가격 범위 확인
                    if MIN_PRICE <= new_price <= MAX_PRICE:
                        # 매도1호가 비교
                        if new_price >= ask_price:
                            print("정정 가격이 매도1호가 이상이어서 정정하지 않습니다.")
                            print(f"정정 예정 가격: {new_price:,.2f}")
                            print(f"매도1호가: {ask_price:,.2f}")
                        else:
                            print("주문가격과 매수1호가가 다르고 정정 가격이 적절하여 정정 주문을 실행합니다.")
                            print(f"목표 가격 범위: {MIN_PRICE:,.2f} ~ {MAX_PRICE:,.2f}")
                            
                            try:
                                # 주문 정정 요청
                                result = await api.modify_bond_order(
                                    order_no=order_no,
                                    symbol=TARGET_SYMBOL,
                                    new_price=new_price
                                )
                                print(f"정정 주문 완료 (주문번호: {result.get('odno', '-')})")
                                print(f"기존 주문가격: {order_price:,.2f}")
                                print(f"정정 주문가격: {new_price:,.2f}")
                                
                            except Exception as e:
                                print(f"주문 정정 실패: {str(e)}")
                    else:
                        print("정정 가격이 목표 범위를 벗어나 정정하지 않습니다.")
                        print(f"목표 가격 범위: {MIN_PRICE:,.2f} ~ {MAX_PRICE:,.2f}")
                        print(f"정정 예정 가격: {new_price:,.2f}")
                        
                print("-" * 30)
        else:
            print(f"목표 종목({TARGET_SYMBOL})의 미체결 주문이 없습니다.")
            
    except Exception as e:
        print(f"주문 조회 실패: {str(e)}")

async def monitor_balance():
    """잔고 모니터링"""
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
        
        # 종목명 조회
        bond_name = await get_bond_name(api, TARGET_SYMBOL)
        print(f"\n=== {bond_name} ({TARGET_SYMBOL}) 잔고 모니터링 시작 ===")
        print(f"목표 보유수량: {TARGET_BALANCE:,}")
        
        # 잔고 모니터링 시작
        while IS_RUNNING:
            try:
                # 잔고 조회
                balance = await api.get_bond_balance()
                current_time = datetime.now().strftime('%H:%M:%S')
                
                print(f"\n[{current_time}] 잔고 조회:")
                
                # 목표 종목 잔고 확인
                if balance:
                    current_quantity = 0
                    for item in balance:
                        if item.get('pdno') == TARGET_SYMBOL:
                            current_quantity = int(item.get('hldg_qty', '0'))
                            print(f"보유수량: {current_quantity:,}")
                            break
                    
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