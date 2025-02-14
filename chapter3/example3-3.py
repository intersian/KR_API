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

    # 삼성전자 7만원에 1주 지정가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=70000, order_type="00")
    print(f"지정가 매수 주문접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # 취소 주문
    res = korea_invest_api.do_cancel(order_no=order_num, order_qty=1)
    print(f"취소 주문 접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 7만원에 1주 지정가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=70000, order_type="00")
    print(f"지정가 매수 주문접수 결과: {res.get_body()}")
    order_num = res.get_body().output['ODNO']

    # 2초 멈춤
    time.sleep(2)

    # 8만원으로 정정 주문
    res = korea_invest_api.do_revise(order_no=order_num, order_qty=1, order_price=80000)
    print(f"정정 주문 접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 7만원에 1주 지정가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=70000, order_type="00")
    print(f"지정가 매수 주문접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 6만원 5천원에 1주 지정가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=65000, order_type="00")
    print(f"지정가 매수 주문접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 현재 계좌의 미체결 내역 조회
    unfinished_orders_df = korea_invest_api.get_orders()
    print("---------미체결 내역---------")
    print(unfinished_orders_df)

    # 2초 멈춤
    time.sleep(2)

    # 현재 계좌에 있는 모든 미체결 취소
    korea_invest_api.do_cancel_all()

    # 2초 멈춤
    time.sleep(2)

    # 다시 현재 계좌의 미체결 내역 조회
    unfinished_orders_df = korea_invest_api.get_orders()
    print("---------미체결 내역---------")
    print(unfinished_orders_df)


if __name__ == "__main__":
    main()
