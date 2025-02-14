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
    df = korea_invest_api.list_overseas_condition_matching_stocks(exchange_code="NAS")
    print(df)

    df = korea_invest_api.list_overseas_condition_matching_stocks(exchange_code="AMS")  # 아멕스
    print(df)


if __name__ == "__main__":
    main()
