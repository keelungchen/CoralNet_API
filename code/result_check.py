import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from PIL import Image

def draw_results(image_path="downloaded_image.jpg", csv_path="classification_results.csv"):
    # 載入圖片（你可以改成從網路下載或其他方式）
    img = Image.open(image_path)
    width, height = img.size
    margin_x = width * 0.1
    margin_y = height * 0.1
    inner_left = margin_x
    inner_right = width - margin_x
    inner_top = margin_y
    inner_bottom = height - margin_y

    # 以 4x4 方式產生 16 個點（與原本的打點邏輯相同）
    x_coords = np.linspace(inner_left, inner_right, 4)
    y_coords = np.linspace(inner_top, inner_bottom, 4)
    points = []
    for y in y_coords:
        for x in x_coords:
            points.append((x, y))
    
    # 讀取 CSV 中的分類結果
    df = pd.read_csv(csv_path)
    # 建立以 (row, column) 為 key 的字典（這邊 row 對應 y 座標、column 對應 x 座標）
    classification_dict = {}
    for index, row in df.iterrows():
        key = (int(row['row']), int(row['column']))
        # 如果有多筆結果，這裡僅取第一筆；你也可以依需要做其他處理
        if key not in classification_dict:
            classification_dict[key] = f"{row['label_name']} ({row['score']})"
    
    # 繪製圖片並疊加打點與分類結果
    plt.figure(figsize=(8, 6))
    plt.imshow(img)
    for (x, y) in points:
        plt.plot(x, y, "ro")  # 紅色圓點
        # 由於 API 送入的點格式是 {"row": y, "column": x}，所以字典 key 也是 (y, x)
        label = classification_dict.get((int(y), int(x)), "")
        plt.text(x + 5, y + 5, f"({int(x)},{int(y)})\n{label}", color="yellow", fontsize=8)
    plt.title("Image with 16 Uniform Points and CoralNet Classification")
    plt.axis("off")
    plt.show()

# 只執行繪圖部分
if __name__ == "__main__":
    draw_results("downloaded_image.jpg", "classification_results.csv")
