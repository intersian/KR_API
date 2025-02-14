import datetime

from urllib.request import urlopen
from bs4 import BeautifulSoup


dart_api_key = ''


def main():
    start_date = datetime.datetime.now().strftime("%Y%m%d")
    url = f"http://opendart.fss.or.kr/api/list.xml?crtfc_key={dart_api_key}&bgn_de={start_date}&page_count=8&page_no=1"
    resultXML = urlopen(url)
    result = resultXML.read()
    xmlsoup = BeautifulSoup(result, 'xml')
    for t in xmlsoup.findAll("list"):
        rcept_no = t.rcept_no.string
        stock_code = t.stock_code.string
        corp_name = t.corp_name.string
        report_nm = t.report_nm.string
        print(f"공시번호: {rcept_no}, 종목코드: {stock_code}, 종목명: {corp_name}, 공시제목: {report_nm}")


if __name__ == '__main__':
    main()
