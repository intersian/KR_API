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

    # 주식현재가 시세 TR
    price_info_map = korea_invest_api.get_overseas_current_price(exchange_code="NAS", stock_no="AAPL")
    print(price_info_map)

    # 2초 멈춤
    time.sleep(2)

    # 주식 잔고 조회 TR
    account_balance, details_df = korea_invest_api.get_overseas_acct_balance()  # 계좌 정보 조회
    print(f"계좌 평가 잔고: {account_balance} USD")
    print("---------종목별 잔고---------")
    print(details_df)


if __name__ == "__main__":
    main()
