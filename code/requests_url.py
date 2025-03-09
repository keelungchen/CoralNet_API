import requests
import json
import csv

# 設定最終結果的 URL 與 API Token
result_url = "https://coralnet.ucsd.edu/api/deploy_job/86448/status/"  # 請替換為你的結果 URL
TOKEN = "3d6b7a0d94c203a9ae55fe9d973bd579cd6f48ac"  # 請替換為你的 CoralNet API Token

def fetch_result_data(result_url, token):
    """
    根據結果 URL 取得 JSON 資料，並回傳 Python 資料結構
    """
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(result_url, headers=headers)
    if response.status_code == 200:
        try:
            json_data = response.json()
            return json_data
        except json.JSONDecodeError as e:
            print("無法解析 JSON 資料:", e)
            return None
    else:
        print("取得結果失敗，HTTP 狀態碼:", response.status_code)
        print("回應內容:", response.text)
        return None

def parse_classification_data(json_data):
    """
    解析 CoralNet 最終分類結果 JSON，轉為列表形式。
    回傳結構範例：
    [
        [image_url, row, column, label_id, label_code, label_name, score],
        ...
    ]
    """
    results = []
    data_list = json_data.get("data", [])
    for item in data_list:
        image_url = item.get("id", "")
        attributes = item.get("attributes", {})
        points = attributes.get("points", [])
        
        for point in points:
            row = point.get("row")
            column = point.get("column")
            classifications = point.get("classifications", [])
            
            # 使用 .get() 避免 KeyError
            for classification in classifications:
                label_id   = classification.get("label_id", "")
                label_code = classification.get("label_code", "")
                label_name = classification.get("label_name", "")
                score      = classification.get("score", "")
                
                results.append([
                    image_url,
                    row,
                    column,
                    label_id,
                    label_code,
                    label_name,
                    score
                ])
    return results

def save_results_to_csv(results, output_csv="classification_results.csv"):
    """
    將解析後的結果列表存成 CSV 檔案
    """
    headers = ["image_url", "row", "column", "label_id", "label_code", "label_name", "score"]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(results)
    print(f"分類結果已輸出至 {output_csv}")

if __name__ == "__main__":
    # 取得 JSON 結果
    json_data = fetch_result_data(result_url, TOKEN)
    if json_data is None:
        print("無法取得 JSON 結果。")
    else:
        # 解析 JSON 資料並存成表格
        parsed_results = parse_classification_data(json_data)
        if parsed_results:
            save_results_to_csv(parsed_results)
        else:
            print("解析結果為空，請檢查 JSON 結構是否有變更。")
