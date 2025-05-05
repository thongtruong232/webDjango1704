import requests
from msal import ConfidentialClientApplication

# Config
CLIENT_ID = 'CLIENT_ID_CỦA_BẠN'
CLIENT_SECRET = 'CLIENT_SECRET_CỦA_BẠN'
TENANT_ID = 'common'  # hoặc 'organizations' hoặc tenant cụ thể
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
REDIRECT_URI = 'http://localhost'  # Dùng cho grant flow nếu cần

SCOPES = ['https://graph.microsoft.com/.default']  # dùng với client credentials flow

# Danh sách email cần đọc (dạng địa chỉ email)
email_accounts = [
    "email1@outlook.com",
    "email2@domain.com",
]

# Khởi tạo ứng dụng MSAL
app = ConfidentialClientApplication(
    client_id=CLIENT_ID,
    client_credential=CLIENT_SECRET,
    authority=AUTHORITY
)

# Lấy access token
token_result = app.acquire_token_for_client(scopes=SCOPES)

if "access_token" in token_result:
    access_token = token_result["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    for email in email_accounts:
        print(f"\n🔍 Đang đọc email của {email}")
        # API đọc thư mục Inbox
        url = f"https://graph.microsoft.com/v1.0/users/{email}/mailFolders/Inbox/messages?$top=5"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            messages = response.json().get('value', [])
            for msg in messages:
                print(f"- {msg['subject']} | Từ: {msg['from']['emailAddress']['address']}")
        else:
            print(f"❌ Không đọc được email {email} - lỗi {response.status_code}")
else:
    print("Không lấy được access token!")
