import os
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import sys
import datetime

from urllib.request import urlopen
from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5 import uic


form_class = uic.loadUiType("main.ui")[0]


class MainWindow(QMainWindow, form_class):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.reqDartPushButton.clicked.connect(self.request_crawling)

    def request_crawling(self):
        start_date = datetime.datetime.now().strftime("%Y%m%d")
        for i in range(1, 100):
            url = f"http://opendart.fss.or.kr/api/list.xml?" \
                  f"crtfc_key={self.dartAPIKEYLineEdit.text()}&bgn_de={start_date}&page_count=8&page_no={i}"
            resultXML = urlopen(url)
            result = resultXML.read()
            xmlsoup = BeautifulSoup(result, 'xml')
            for t in xmlsoup.findAll("list"):
                rcept_no = t.rcept_no.string
                stock_code = t.stock_code.string
                corp_name = t.corp_name.string
                report_nm = t.report_nm.string
                self.resultTextEdit.append(
                    f"공시번호: {rcept_no}, 종목코드: {stock_code}, "
                    f"종목명: {corp_name}, 공시제목: {report_nm}"
                )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())
