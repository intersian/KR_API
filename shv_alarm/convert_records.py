import json
import csv
from pathlib import Path
import os
import sys

def convert_json_to_csv():
    """JSON 거래 기록을 CSV 파일로 변환"""
    try:
        # 실행 파일 또는 스크립트 위치 확인
        if getattr(sys, 'frozen', False):
            base_path = Path(os.path.dirname(sys.executable))
        else:
            base_path = Path(os.path.dirname(os.path.abspath(__file__)))
        
        # JSON 파일 경로
        json_file = base_path / 'shv_daily' / 'trade_records_20250225.json'
        csv_file = json_file.with_suffix('.csv')
        
        # JSON 파일 읽기
        with open(json_file, 'r', encoding='utf-8') as f:
            records = json.load(f)
        
        # CSV 파일 작성
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # 헤더 작성
            writer.writerow(['매매가격', '유지시간(초)', '시작시각', '종료시각'])
            
            # 데이터 작성 (지속시간 기준 내림차순 정렬)
            sorted_records = sorted(records, key=lambda x: x['duration'], reverse=True)
            for record in sorted_records:
                writer.writerow([
                    f"${record['price']:.4f}",
                    f"{record['duration']:.1f}",
                    record['start_time'],
                    record['end_time']
                ])
        
        print(f"\n변환 완료: {csv_file}")
        
    except FileNotFoundError:
        print(f"\n파일을 찾을 수 없습니다: {json_file}")
    except Exception as e:
        print(f"\n변환 실패: {e}")

if __name__ == "__main__":
    convert_json_to_csv() 