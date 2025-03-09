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
    
    :param folder_path: Dropbox 資料夾路徑。
           若為 App folder 模式，請傳入空字串 ""。
           若是全 Dropbox 應用程式，請傳入正確的絕對路徑（例如 "/Apps/CoralNet_test"）。
    :param access_token: Dropbox 存取權杖。
    :return: 檔案資訊列表。
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
# CoralNet API 相關函式（簡化輸出，只顯示重點）
def check_deployment_status(status_url, token):
    headers = {"Authorization": f"Token {token}"}
    response = requests.get(status_url, headers=headers)
    if response.status_code == 200:
        try:
            data = response.json()
            # 只回報是否有分類結果，不顯示完整 JSON
            if "data" in data and data["data"] and data["data"][0].get("attributes", {}).get("points"):
                print("分類結果已回傳。")
                return data
            else:
                print("分類結果尚未回傳。")
                return None
        except json.JSONDecodeError:
            print("回應非有效 JSON。")
            return None
    elif response.status_code == 303:
        result_url = response.headers.get("Location", "")
        if not result_url.startswith("http"):
            result_url = "https://coralnet.ucsd.edu" + result_url
        print(f"分類完成，結果 URL: {result_url}")
        return fetch_result_data(result_url, token)
    else:
        print(f"檢查狀態失敗，HTTP {response.status_code}")
        return None

def poll_deployment_status(status_url, token, interval=10, timeout=1200):
    start_time = time.time()
    while True:
        elapsed_time = time.time() - start_time
        print(f"累計查詢時間：{elapsed_time:.2f} 秒")
        if elapsed_time > timeout:
            print("超過20分鐘仍未完成，跳過此圖片。")
            return None
        result = check_deployment_status(status_url, token)
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
# 同時將 annotated 圖片存為獨立檔案，其檔名依原始檔名命名
# 此函式也計算處理時間
def process_image(image_url, filename, output_dir="annotated_images"):
    global global_point_counter
    start_time = time.time()  # 記錄開始時間
    print("\n處理圖片:", image_url)
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
    
    # 使用整個圖片範圍，將圖片分成 12x12 個矩形，取每個矩形的中心作為打點
    n_points = 12
    x_coords = [(i + 0.5) * (width / n_points) for i in range(n_points)]
    y_coords = [(j + 0.5) * (height / n_points) for j in range(n_points)]
    points = []       # 原始打點座標 (tuple: (x, y))
    api_points = []   # 用於 API 的打點資料
    for y in y_coords:
        for x in x_coords:
            points.append((x, y))
            api_points.append({"row": int(y), "column": int(x)})

    # 依據每張圖的打點由左下到左上排序（依 x 升序，若 x 相同則 y 降序），產生連續的全域編號
    sorted_indices = sorted(range(len(points)), key=lambda i: (points[i][0], -points[i][1]))
    point_seq_numbers = [0] * len(points)
    for pos, i in enumerate(sorted_indices):
        point_seq_numbers[i] = global_point_counter
        global_point_counter += 1

    # -----------------------------
    # 呼叫 CoralNet API 進行分類
    API_BASE_URL = "https://coralnet.ucsd.edu/api"
    CORALNET_TOKEN = "3d6b7a0d94c203a9ae55fe9d973bd579cd6f48ac"  # 請替換為您的 CoralNet API Token
    CLASSIFIER_ID = "41004"  # 請替換為目標分類器 ID

    def request_classifier_deployment(image_urls, points):
        endpoint = f"{API_BASE_URL}/classifier/{CLASSIFIER_ID}/deploy/"
        headers = {
            "Authorization": f"Token {CORALNET_TOKEN}",
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
            # 簡化輸出，只回報關鍵資訊
            print(f"狀態 URL: {status_url}")
            return status_url
        else:
            print("部署請求失敗。")
            return None

    status_url = request_classifier_deployment([image_url], api_points)
    if not status_url:
        print("部署請求失敗，跳過此圖片。")
        return None

    json_data = poll_deployment_status(status_url, CORALNET_TOKEN, interval=10, timeout=900)
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
        key = (int(y), int(x))  # 使用整數作為鍵
        classification = classification_dict.get((int(y), int(x)), {"score": None, "label_id": "NAN", "label_code": "NAN"})
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
    # 若該點的 score < 0.5，則顯示 label_code 加上括號；否則直接顯示 label_code
    os.makedirs(output_dir, exist_ok=True)
    output_image_path = os.path.join(output_dir, f"annotated_{filename}")
    plt.figure(figsize=(8, 6))
    plt.imshow(img)
    for i, (x, y) in enumerate(points):
        plt.plot(x, y, "ro")
        classification = classification_dict.get((int(y), int(x)), {"score": None, "label_code": "NAN"})
        score = classification["score"]
        label_code = classification["label_code"]
        if score is not None and score < 0.5:
            label_to_show = f"({label_code})"
        else:
            label_to_show = label_code
        seq_num = point_seq_numbers[i]
        plt.text(x + 5, y + 5, f"{seq_num}\n{label_to_show}", color="yellow", fontsize=8)
    plt.title(f"Image {filename} with Points and CoralNet Classification")
    plt.axis("off")
    plt.savefig(output_image_path, bbox_inches="tight")
    plt.close()
    print(f"註解圖片已儲存至 {output_image_path}")

    # 計算累計運算時間
    processing_time = time.time() - start_time

    # 將運算時間加入每個點的結果中
    for result in results_for_image:
        result["processing_time"] = processing_time

    return results_for_image

# -----------------------------
# 主程式：依檔名順序處理所有圖片，統一輸出分類結果 CSV 與 annotated 圖片
def main():
    ACCESS_TOKEN = "sl.u.AFnLi5RyoawywGNnFqZWTUzNJTwHWh3JAVRnST5yEhvcCRqS7UXvqAkuzVIOIivn9IdI7xthTflU1agUTIcLRva-CrDn8iKNs7u2TSpeJ6VmQ0D-tkgh0nn_BE-b4inzEI_4QL1qELRisuIdD4bk6W7huoptX8M5tOVnlfM3b5gdkpkP_6Z-BspvfBeHtkfAitLRBDH6dwEj18MUSWmOKYyEAeiFlcRnc7o9BQC0OF9Ym91rils-I8cMjp_E5xJXEBdDQ82aT6Csw0mc8Is6wYaS1Sr-ACSRLVHN1_HRgIsDF_QwFRU_kw0isuUrsxR2Te3uDRkqybSkPZf8Yb07zqK-IVkXV6JELclizJNoPlxrgJ_2UzmRVOWpQoAFcEq_lXUpVAP8CLqchHwmszg9y_6JgjFqootzNBBGQiwuNb8e6dL8RzTcu2qlylgi_1wfae8RfpbvWJwr1aRdoGnFWUxHREYCgM7Pr_8qXopYZeCvsQzFroT2lDnOKcx7ey8HLRitDJv9jgmvcGvdZ_XuZe9BN1wD2F0pzaHzhiOS0G2udVvm7h5HzsvXxedd7T9PbZI_RdAD4j_TKKtmxSSeGqCLF_o4Xt_KLH5SDybztNyLKvu1yljKqRVurTRd9_pKuwTU85jX4DgdZMt3UEh5VjUCCiSiENrGbrhj_CJr5OjXuH_qEePBbdVxzT7q-wGUC-0UWB8natEmshQsQi1o9Ya19f7zKL_tE8-8hR5qWizFYfnqfjPsJq4adjHQzKygY-IhM3nbMo6V__EM0gHzKoyukkH4eRNKARP4R--suDPnXbIX1SeSgK2Zl3p86DG4Le9C4KFIg1WUcF4bnyagDJHfETdPleYA7Vn5K7l5Nkgg0MkqQTbegYf8cxyxLwVqJ3unIvgHa3noCBAABziPcDexGataNpqVLYZA2Kir2BHekpNFpL24ppY67dV00vc9ZcLs_FprJP3Ic39nTtxYerNfBrNjgQfLpwlLgPwWdjdecWagLTCjJ905zH8DGj5ajkhkYeVJ7Dmf-aBWjekOCwfEAd0rYbL3EX9Lh-OJ2qvKA3TieX5b28dtPhz85Y7YLgjJRkHb2OtIwQHS_90aoavpU26EPh2kdf3Nh--wbnHsPI_QHbQYgBGyQ66Wk6lBc0qVZbamFBqQPZvo98GVP9Dh26Liwt5N3hO4yGONn5VZFAyqm0xi1sA5UdElckwlRe1gZclqougpRE4TyrsaSvglu7U0RAdwfY6mx8r_-ayU0ZrGIPFiQDoYzp9Nj-oEJFZ-O0kcmcDUvFypUCL0lWLx"  # 請替換成您的 Dropbox 存取權杖
    folder_path = ""  # 若為 App folder 模式，傳入空字串
    file_info_list = get_dropbox_folder_file_info_recursive(folder_path, ACCESS_TOKEN)
    print(f"共取得 {len(file_info_list)} 張圖片。")
    
    # 依檔名排序：檔名較小的先處理
    file_info_list.sort(key=lambda x: x["name"])
    
    all_results = []  # 收集所有圖片的分類結果
    for file_info in file_info_list:
        filename = file_info["name"]
        image_url = file_info["link"]
        print(f"開始處理 {filename} ...")
        results = process_image(image_url, filename)
        if results:
            all_results.extend(results)
    
    if all_results:
        df_all = pd.DataFrame(all_results)
        # 輸出 CSV 時取消 image_url 欄位（只保留 filename）
        df_all = df_all.drop(columns=["image_url"], errors="ignore")
        df_all.to_csv("all_classification_results.csv", index=False, encoding="utf-8-sig")
        print("所有圖片的分類結果已輸出至 all_classification_results.csv")
    else:
        print("沒有取得任何分類結果。")
    return all_results

if __name__ == "__main__":
    main()
