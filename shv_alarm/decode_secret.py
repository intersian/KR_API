import base64

def decode_secret():
    # 암호화된 시크릿 키 입력 받기
    print("\n=== API 시크릿 키 복호화 ===")
    print("암호화된 시크릿 키를 입력하세요:")
    encoded_secret = input().strip()
    
    try:
        # 패딩 추가 (필요한 경우)
        padding_needed = len(encoded_secret) % 4
        if padding_needed:
            encoded_secret += '=' * (4 - padding_needed)
            
        # Base64 디코딩 시도 (여러 방식)
        try:
            # 방법 1: URL Safe Base64
            decoded_secret = base64.urlsafe_b64decode(encoded_secret)
            print("\n=== 복호화 결과 (URL Safe Base64) ===")
            print(decoded_secret.decode('utf-8', errors='ignore'))
        except:
            try:
                # 방법 2: 일반 Base64
                decoded_secret = base64.b64decode(encoded_secret)
                print("\n=== 복호화 결과 (Standard Base64) ===")
                print(decoded_secret.decode('utf-8', errors='ignore'))
            except:
                # 방법 3: 수정된 Base64
                encoded_secret = encoded_secret.replace('-', '+').replace('_', '/')
                decoded_secret = base64.b64decode(encoded_secret)
                print("\n=== 복호화 결과 (Modified Base64) ===")
                print(decoded_secret.decode('utf-8', errors='ignore'))
        
        print("\n이 값을 한국투자증권 OpenAPI 관리 페이지에서 확인하실 수 있습니다.")
        
    except Exception as e:
        print("\n오류: 시크릿 키 복호화에 실패했습니다.")
        print(f"상세 오류: {str(e)}")
        print("\n다른 인코딩 방식을 시도해보세요.")

if __name__ == "__main__":
    decode_secret() 