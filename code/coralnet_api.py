import requests
import json
import time

# CoralNet API 基本設定
API_BASE_URL = "https://coralnet.ucsd.edu/api"
TOKEN = "3d6b7a0d94c203a9ae55fe9d973bd579cd6f48ac"  # 替換為您的 CoralNet API Token
CLASSIFIER_ID = "41004"  # 替換為目標分類器 ID

## 發送部署請求
def request_classifier_deployment(image_urls, points):
    """
    發送部署請求到 CoralNet API。
    - image_urls: 圖片的公開網址列表
    - points: 矩陣點位置（包含 row 和 column）
    """
    endpoint = f"{API_BASE_URL}/classifier/{CLASSIFIER_ID}/deploy/"
    headers = {
        "Authorization": f"Token {TOKEN}",
        "Content-Type": "application/vnd.api+json",
    }

    # 構造請求數據
    data = {
        "data": [
            {
                "type": "image",
                "attributes": {
                    "url": url,
                    "points": points,
                },
            }
            for url in image_urls
        ]
    }

    # 發送 POST 請求
    response = requests.post(endpoint, headers=headers, json=data)
    if response.status_code == 202:
        print("部署請求已接受，檢查狀態 URL:")
        location = response.headers["Location"]
        # 若 location 不是完整的 URL，則補全域名
        if not location.startswith("http"):
            status_url = "https://coralnet.ucsd.edu" + location
        else:
            status_url = location
        print(status_url)
        return status_url
    else:
        print("部署請求失敗，錯誤信息：")
        print(response.json())
        return None

# 檢查部署狀態
def check_deployment_status(status_url):
    """
    檢查部署狀態。
    - status_url: 狀態檢查的 URL
    """
    headers = {"Authorization": f"Token {TOKEN}"}
    response = requests.get(status_url, headers=headers)

    if response.status_code == 200:
        try:
            data = response.json()
            status = data["data"][0]["attributes"]["status"]
            print(f"部署狀態: {status}")
            return status
        except json.JSONDecodeError:
            print("回應不是有效的 JSON 格式：", response.text)
            return None
    elif response.status_code == 303:
        result_url = response.headers.get("Location", "")
        if not result_url.startswith("http"):
            result_url = "https://coralnet.ucsd.edu" + result_url
        print(f"分類完成，結果 URL: {result_url}")
        return result_url
    else:
        print("檢查狀態失敗，HTTP 狀態碼：", response.status_code)
        print("回應內容：", response.text)
        return None

# 主程式：將圖片 URL 與矩陣點整合到 API 請求
def main():
    # 圖片的公開 URL 列表
    image_urls = [
        "https://upload.wikimedia.org/wikipedia/commons/c/ca/Acropora_coral_ffs.jpg",
    ]

    # 假設圖片尺寸為 1920x1080，生成點矩陣
    image_width, image_height = 1920, 1080
    rows, cols = 5, 5
    margin = 50

    # 計算每個點的位置
    x_spacing = (image_width - 2 * margin) / (cols - 1)
    y_spacing = (image_height - 2 * margin) / (rows - 1)

    points = []
    for i in range(rows):
        for j in range(cols):
            x = margin + j * x_spacing
            y = margin + i * y_spacing
            points.append({"row": int(y), "column": int(x)})

    print(f"生成點位數量: {len(points)}")
    print(points)

    # 發送部署請求
    status_url = request_classifier_deployment(image_urls, points)
    if status_url:
        # 等待一段時間後檢查狀態
        time.sleep(5)

        # 檢查部署狀態
        result_url = check_deployment_status(status_url)
        if result_url and "result" in result_url:
            print(f"分類結果可在此 URL 獲取: {result_url}")

# 執行主程式
if __name__ == "__main__":
    main()

