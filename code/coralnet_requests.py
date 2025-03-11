import re
import requests
from io import BytesIO
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import json
import time
import csv
import dropbox
import os

# 全域點編號，跨圖片累計
global_point_counter = 1

# -----------------------------
# 使用 Dropbox API 遞迴列出指定資料夾及其子資料夾內所有圖片檔案的直接下載連結與檔案名稱
def get_dropbox_folder_file_info_recursive(folder_path, access_token):
    """
    列出 Dropbox 指定資料夾（及其子資料夾）內所有圖片檔案的資訊，
    回傳一個列表，每個元素為字典，包含 "name" 與 "link"。
    """
    dbx = dropbox.Dropbox(access_token)
    file_info_list = []
    
    def list_folder(path):
        try:
            result = dbx.files_list_folder(path)
            for entry in result.entries:
                if isinstance(entry, dropbox.files.FileMetadata):
                    if entry.name.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        try:
                            shared_link_metadata = dbx.sharing_create_shared_link_with_settings(entry.path_lower)
                        except dropbox.exceptions.ApiError as e:
                            shared_links = dbx.sharing_list_shared_links(path=entry.path_lower, direct_only=True).links
                            if shared_links:
                                shared_link_metadata = shared_links[0]
                            else:
                                print(f"無法取得 {entry.name} 的共享連結：", e)
                                continue
                        link = shared_link_metadata.url
                        direct_link = link.replace('dl=0', 'raw=1')
                        file_info_list.append({"name": entry.name, "link": direct_link})
                elif isinstance(entry, dropbox.files.FolderMetadata):
                    list_folder(entry.path_lower)
        except Exception as e:
            print(f"列出資料夾 {path} 時發生錯誤：", e)
    
    list_folder(folder_path)
    return file_info_list

# -----------------------------
# CoralNet API 相關函式（加入進度資訊）
def check_deployment_status(status_url, token, current_index=None, total_count=None):
    progress_info = f" ({current_index}/{total_count})" if current_index and total_count else ""
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(status_url, headers=headers)
    if response.status_code == 200:
        try:
            data = response.json()
            # 判斷是否有分類結果（檢查 points 資料是否存在）
            if "data" in data and data["data"] and data["data"][0].get("attributes", {}).get("points"):
                print("分類結果已回傳" + progress_info)
                return data
            else:
                print("分類結果尚未回傳" + progress_info)
                return None
        except json.JSONDecodeError:
            print("回應非有效 JSON。" + progress_info)
            return None
    elif response.status_code == 303:
        result_url = response.headers.get("Location", "")
        if not result_url.startswith("http"):
            result_url = "https://coralnet.ucsd.edu" + result_url
        print(f"分類完成，結果 URL: {result_url}" + progress_info)
        return fetch_result_data(result_url, token)
    elif response.status_code == 403:
        print("HTTP 403 Forbidden: Authentication credentials were not provided." + progress_info)
        return None
    else:
        print(f"檢查狀態失敗，HTTP {response.status_code}" + progress_info)
        return None

def poll_deployment_status(status_url, token, interval=10, timeout=1200, current_index=None, total_count=None):
    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        progress_info = f" ({current_index}/{total_count})" if current_index and total_count else ""
        print(f"累計查詢時間：{elapsed_time:.2f} 秒" + progress_info)
        if elapsed_time > timeout:
            print("超過20分鐘仍未完成，跳過此圖片。")
            return None
        result = check_deployment_status(status_url, token, current_index, total_count)
        if isinstance(result, dict):
            return result
        time.sleep(interval)

def fetch_result_data(result_url, token):
    headers = {"Authorization": f"Token {token}"}
    resp = requests.get(result_url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"取得結果失敗，HTTP {resp.status_code}")
        return None

# -----------------------------
# 處理單一圖片：下載圖片、生成打點、呼叫 CoralNet API 進行分類，並返回該圖片所有打點的分類結果（列表）
# 此函式也將 annotated 圖片存為獨立檔案，其檔名依原始檔名命名，並回傳處理結果（附上處理時間）
# 新增參數 current_index 與 total_count 以顯示進度資訊
def process_image(image_url, filename, coralnet_token, current_index, total_count, output_dir="annotated_images"):
    global global_point_counter
    start_time = time.time()  # 記錄開始時間
    print(f"\n處理圖片: {filename} ({current_index}/{total_count})")
    response = requests.get(image_url)
    if response.status_code != 200:
        print("無法下載圖片，跳過此圖片。")
        return None
    try:
        img = Image.open(BytesIO(response.content))
    except Exception as e:
        print("無法識別圖片檔案：", e)
        return None

    width, height = img.size
    print(f"圖片解析度：寬 {width} 像素, 高 {height} 像素")
    
    # 使用整個圖片範圍，將圖片分成 12x12 個矩形，取每個矩形中心作為打點
    n_points = 12
    x_coords = [(i + 0.5) * (width / n_points) for i in range(n_points)]
    y_coords = [(j + 0.5) * (height / n_points) for j in range(n_points)]
    points = []       # 原始打點座標 (tuple: (x, y))
    api_points = []   # 用於 API 的打點資料
    for y in y_coords:
        for x in x_coords:
            points.append((x, y))
            api_points.append({"row": int(y), "column": int(x)})

    # 對每張圖的打點排序（依 x 升序，若 x 相同則 y 降序），產生連續的全域編號
    sorted_indices = sorted(range(len(points)), key=lambda i: (points[i][0], -points[i][1]))
    point_seq_numbers = [0] * len(points)
    for pos, i in enumerate(sorted_indices):
        point_seq_numbers[i] = global_point_counter
        global_point_counter += 1

    # -----------------------------
    # 呼叫 CoralNet API 進行分類
    API_BASE_URL = "https://coralnet.ucsd.edu/api"
    CLASSIFIER_ID = "41004"  # 請替換為目標分類器 ID

    def request_classifier_deployment(image_urls, points):
        endpoint = f"{API_BASE_URL}/classifier/{CLASSIFIER_ID}/deploy/"
        headers = {
            "Authorization": f"Token {coralnet_token}",
            "Content-Type": "application/vnd.api+json",
        }
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
        response = requests.post(endpoint, headers=headers, json=data)
        if response.status_code == 202:
            print("部署請求已接受。")
            location = response.headers["Location"]
            if not location.startswith("http"):
                status_url = "https://coralnet.ucsd.edu" + location
            else:
                status_url = location
            print(f"狀態 URL: {status_url}")
            return status_url
        else:
            print("部署請求失敗。")
            return None

    status_url = request_classifier_deployment([image_url], api_points)
    if not status_url:
        print("部署請求失敗，跳過此圖片。")
        return None

    json_data = poll_deployment_status(status_url, coralnet_token, interval=10, timeout=900, current_index=current_index, total_count=total_count)
    if not json_data:
        print("輪詢超過15分鐘或發生錯誤，跳過此圖片。")
        return None

    # 解析分類結果：對每個打點，從 classifications 中取出所有結果，
    # 找出得分最高者，並記錄其 score、label_id、label_code
    def parse_classification_data(json_data):
        result_dict = {}
        data_list = json_data.get("data", [])
        if not data_list:
            return result_dict
        points_data = data_list[0]["attributes"].get("points", [])
        for point in points_data:
            key = (point.get("row"), point.get("column"))
            classifications = point.get("classifications", [])
            if classifications:
                best = max(classifications, key=lambda c: c.get("score", 0))
                result_dict[key] = {
                    "score": best.get("score", 0),
                    "label_id": best.get("label_id"),
                    "label_code": best.get("label_code")
                }
            else:
                result_dict[key] = {
                    "score": None,
                    "label_id": "NAN",
                    "label_code": "NAN"
                }
        return result_dict

    classification_dict = parse_classification_data(json_data)

    # 組合該圖片的結果，每個打點包含 filename、point_number、row、column、score、label_id、label_code
    results_for_image = []
    for i, (x, y) in enumerate(points):
        key = (int(y), int(x))
        classification = classification_dict.get(key, {"score": None, "label_id": "NAN", "label_code": "NAN"})
        results_for_image.append({
            "filename": filename,
            "point_number": point_seq_numbers[i],
            "row": int(y),
            "column": int(x),
            "score": classification["score"],
            "label_id": classification["label_id"],
            "label_code": classification["label_code"]
        })

    # -----------------------------
    # 繪圖：在圖片上標示每個打點的編號與分類結果
    os.makedirs(output_dir, exist_ok=True)
    output_image_path = os.path.join(output_dir, f"annotated_{filename}")
    plt.figure(figsize=(8, 6))
    plt.imshow(img)
    for i, (x, y) in enumerate(points):
        plt.plot(x, y, "ro")
        classification = classification_dict.get((int(y), int(x)), {"score": None, "label_code": "NAN"})
        score = classification["score"]
        label_code = classification["label_code"]
        label_to_show = f"({label_code})" if score is not None and score < 0.5 else label_code
        seq_num = point_seq_numbers[i]
        plt.text(x + 5, y + 5, f"{seq_num}\n{label_to_show}", color="yellow", fontsize=8)
    plt.title(f"Image {filename} with Points and CoralNet Classification")
    plt.axis("off")
    plt.savefig(output_image_path, bbox_inches="tight")
    plt.close()
    print(f"註解圖片已儲存至 {output_image_path}")

    processing_time = time.time() - start_time
    for result in results_for_image:
        result["processing_time"] = processing_time

    return results_for_image

# -----------------------------
# 主程式：依檔名順序處理所有圖片，處理完每一張圖片後即存一次 CSV，以防程式中途中斷
def main():
    # 請替換成您的 Dropbox 存取權杖
    ACCESS_TOKEN = "sl.u.AFnW4py8eQ40rErIKpg2KeH93LLxiuHqedFFAo4sGfTH5JM6Z3wzI8U8-qz464AXq4ag-3ZYjNfIFh8L8IDjR9jQKEhDY9fxmn0fLfQlfbovrGEhyjCzKYsDUiBP2oU0EI_PW8gQuVMu1rh-S1_ebyi6ifot4U0H16SrIIAtjkZtFUOn3tQ0hCkeSPH3Y5S839gXzIRYYpAZWp2emZAplaS6qb_qSJEmb1WQ9cz_rEJ27Qrr1cg8AKLA7Se7HlFwFebFkRAjOnYJlF50SefP2oqMSngrm2qtZePTKJI8eU6kIj5YgGolBDec2-3BuUy9xyBdn9Avv9-rilcfnNEvdS9f7QGVuZVY-o_JO4tKoHUqJhZsIV6X883eC7N3VJ2jRC1b7McvZxOxG1rap6Ch8jWytIe155ti7twl-27M5OfK2evDmjVjCXy2IN2tJtujc69LAWFZHBWiBKEjqEyZpm5ElJbpfvPZtv5OcprPkz1szWjufgMrhsKsayDcoxDj_1OG57HfWgfnD5PVnyE0CNiraa588Xfh5-Wrl3EQgHy1TH3Dhq1zSzYMtzlQz5hJmy-gPKzWBZAiI2FDInGErRTfE3I42S-84RZKEDhZpMCxXRaKVSYQ4e0a54efI51PC4AwOwTbPYpWr7iMg398znQWS0l1zo5fcor2gfoBwSZWCqA_ZA-3dBZYQa1DyvcMdiMg9Kj7MQs42bmd-cS88LNQa_53ye5Xz9JbZsS8-CBaGtYq6ZDUkFc8oLqC62DRGfxvsjeqozFn_tra0rEir6sgVM--1ThaSCxpcINAo5u5Hj5uSxWviFXvPlJbagX78sxVFzdMzj8UrCfrYN1kV7HKv60M58g8UGjNJuYxmSF8IXl98ViyfKye6tWTOcUGKCK9snsTt4qIwkCVxffrxIWTSBGaEg4_slH-ShXNUIoi66DIuULfLu-rW7V41NmmXitmuMBaAqiRJ1-Eknj2_v1OGOa7PQv-d17lSnJH0KVqyQyzYlYaYc7LAM_n3CPhKIz8f3mgUlaWnY_XcXAC2--23HSq2-z4mRzw05qp4w79yjVJGf29bRhPkSuz4JHOq1tjpfUAki8wbbXyn0lxStvG5XnIIjJU3W3u7ef4fUSrOVYW0HRgfNw38fU3sjRrT2jsVWZzCX0N9Nvnf5KwNA_Hty8PgQW12ZYdT6U84GZ4zB-z5wqEBhFMFLzfhiJl5xlaCkAsqMya9mdjNzfI9KVynon9nkTDWqsuk2iwMuOQKF_NPzygd1P0LQFBWaOsuoS7MmNK50DQPx_34fk49IiR"
    folder_path = ""  # 若為 App folder 模式，傳入空字串
    file_info_list = get_dropbox_folder_file_info_recursive(folder_path, ACCESS_TOKEN)
    print(f"共取得 {len(file_info_list)} 張圖片。")
    
    # 依檔名排序：檔名較小的先處理
    file_info_list.sort(key=lambda x: x["name"])
    
    total_images = len(file_info_list)
    all_results = []  # 收集所有圖片的分類結果
    
    for idx, file_info in enumerate(file_info_list, start=1):
        filename = file_info["name"]
        image_url = file_info["link"]
        print(f"\n開始處理 {filename} ... ({idx}/{total_images})")
        results = process_image(image_url, filename, coralnet_token="3d6b7a0d94c203a9ae55fe9d973bd579cd6f48ac", current_index=idx, total_count=total_images)
        if results:
            all_results.extend(results)
            # 每次處理完就存一次 CSV 檔，避免資料遺失
            df_partial = pd.DataFrame(all_results)
            df_partial = df_partial.drop(columns=["image_url"], errors="ignore")
            df_partial.to_csv("all_classification_results_partial.csv", index=False, encoding="utf-8-sig")
            print(f"目前累計 {len(all_results)} 筆結果，已儲存至 all_classification_results_partial.csv")
        else:
            print(f"{filename} 處理失敗或無結果。")
    
    if all_results:
        df_all = pd.DataFrame(all_results)
        df_all = df_all.drop(columns=["image_url"], errors="ignore")
        df_all.to_csv("all_classification_results.csv", index=False, encoding="utf-8-sig")
        print("所有圖片的分類結果已輸出至 all_classification_results.csv")
    else:
        print("沒有取得任何分類結果。")
    return all_results

if __name__ == "__main__":
    main()
