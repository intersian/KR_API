import yaml

from utils import KoreaInvestEnv, KoreaInvestAPI


def main():
    with open("./config.yaml", encoding='UTF-8') as f:
        cfg = yaml.load(f, Loader=yaml.FullLoader)
    env_cls = KoreaInvestEnv(cfg)
    base_headers = env_cls.get_base_headers()
    cfg = env_cls.get_full_config()
    korea_invest_api = KoreaInvestAPI(cfg, base_headers=base_headers)
    df = korea_invest_api.list_conditions()
    print(df)
    targe_group_name = "테스트"
    target_condition_name = "코스피200"
    try:
        seq_num = df[(df["그룹명"] == targe_group_name) & (df["조건명"] == target_condition_name)]["조건키값"].iloc[0]
    except IndexError:
        print("그룹명과 조건식명을 확인하세요!")
        return
    df1 = korea_invest_api.list_condition_matching_stocks(seq_num)
    print(df1)

    targe_group_name = "테스트2"
    target_condition_name = "샘플조건1"
    try:
        seq_num = df[(df["그룹명"] == targe_group_name) & (df["조건명"] == target_condition_name)]["조건키값"].iloc[0]
    except IndexError:
        print("그룹명과 조건식명을 확인하세요!")
        return
    df2 = korea_invest_api.list_condition_matching_stocks(seq_num)
    print(df2)


if __name__ == "__main__":
    main()
