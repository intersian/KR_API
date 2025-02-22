#1 채권 목표 종목 잔고 모니터링 기능
#2 목표 잔고 도달 시 자동 종료 기능
#3 묙포 잔고 미도달 시 미체결 주문 조회 기능 추가

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

async def check_orders(api):
    """정정취소가능 주문 조회"""
    try:
        orders = await api.get_bond_orders()
        current_time = datetime.now().strftime('%H:%M:%S')
        
        print(f"\n[{current_time}] 미체결 주문 조회:")
        
        # 목표 종목 주문 필터링
        target_orders = []
        if orders:
            for order in orders:
                if order.get('pdno') == TARGET_SYMBOL:
                    target_orders.append(order)
        
        # 결과 출력
        if target_orders:
            for order in target_orders:
                print(f"주문번호: {order.get('odno', '-')}")
                print(f"주문수량: {int(order.get('ord_qty', '0')):,}")
                print(f"체결수량: {int(order.get('tot_ccld_qty', '0')):,}")
                print(f"미체결수량: {int(order.get('ord_psbl_qty', '0')):,}")
                print(f"주문단가: {float(order.get('bond_ord_unpr', '0')):,.2f}")
                print("-" * 30)
        else:
            print(f"목표 종목({TARGET_SYMBOL})의 미체결 주문이 없습니다.")
            
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
                
                # 미체결 주문 조회 (목표 미달성 시)
                await check_orders(api)
                
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