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

    # TQQQ 70달러에 1주 지정가 매수 주문
    res = korea_invest_api.overseas_do_buy("TQQQ", exchange_code="NASD", order_qty=1, order_price=70, order_type="00")
    print(f"매수 주문 접수 결과: {res.get_body()}")

    # 2초 멈춤
    time.sleep(2)

    # TQQQ 65달러에 1주 지정가 매도 주문
    res = korea_invest_api.overseas_do_sell("TQQQ", exchange_code="NASD", order_qty=1, order_price=65, order_type="00")
    print(f"매도 주문 접수 결과: {res.get_body()}")


if __name__ == "__main__":
    main()
