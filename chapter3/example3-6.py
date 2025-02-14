import yaml
import time

from utils import KoreaInvestEnv, KoreaInvestAPI


def main():
    with open("./config.yaml", encoding='UTF-8') as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    env_cls = KoreaInvestEnv(cfg)
    base_headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)

    # TQQQ 60달러에 1주 지정가 매수 주문
    res = korea_invest_api.overseas_do_buy(stock_code="TQQQ", exchange_code="NASD", order_qty=1, order_price=60, order_type="00")
    print(f"매수 주문 접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # 취소 주문
    res = korea_invest_api.overseas_do_cancel(stock_code="TQQQ", order_no=order_num, order_qty=1, order_branch="NASD")
    print(f"취소 주문 접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # TQQQ 60달러에 1주 지정가 매수 주문
    res = korea_invest_api.overseas_do_buy(stock_code="TQQQ", exchange_code="NASD", order_qty=1, order_price=60, order_type="00")
    print(f"매수 주문 접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # 80 달러로 정정 주문
    res = korea_invest_api.overseas_do_revise(stock_code="TQQQ", order_no=order_num, order_qty=1, order_price=80, order_branch="NASD")
    print(f"정정 주문 접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # TQQQ 60달러에 1주 지정가 매수 주문
    res = korea_invest_api.overseas_do_buy(stock_code="TQQQ", exchange_code="NASD", order_qty=1, order_price=60, order_type="00")
    print(f"매수 주문 접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # TQQQ 55달러에 1주 지정가 매수 주문
    res = korea_invest_api.overseas_do_buy(stock_code="TQQQ", exchange_code="NASD", order_qty=1, order_price=60, order_type="00")
    print(f"매수 주문 접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # 현재 계좌의 미체결 내역 조회
    unfinished_orders_df = korea_invest_api.get_overseas_orders()
    print("---------미체결 내역---------")
    print(unfinished_orders_df)

    # 2초 멈춤
    time.sleep(2)

    # 현재 계좌에 있는 모든 미체결 취소
    korea_invest_api.overseas_do_cancel_all()

    # 2초 멈춤
    time.sleep(2)

    # 다시 현재 계좌의 미체결 내역 조회
    unfinished_orders_df = korea_invest_api.get_overseas_orders()
    print("---------미체결 내역---------")
    print(unfinished_orders_df)


if __name__ == "__main__":
    main()
