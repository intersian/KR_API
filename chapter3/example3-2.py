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

    # 삼성전자 8만원에 1주 지정가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=80000, order_type="00")
    print(f"주문접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 1주 시장가 매수 주문
    res = korea_invest_api.do_buy("005930", order_qty=1, order_price=0, order_type="01")
    print(f"주문접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 7만원에 1주 지정가 매도 주문
    res = korea_invest_api.do_sell("005930", order_qty=1, order_price=70000, order_type="00")
    print(f"주문접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # 삼성전자 1주 시장가 매도 주문
    res = korea_invest_api.do_sell("005930", order_qty=1, order_price=0, order_type="01")
    print(f"주문접수 결과: {res.get_body()}")


if __name__ == "__main__":
    main()
