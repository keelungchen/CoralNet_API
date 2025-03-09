import re
import requests
from io import BytesIO
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

def convert_drive_link(share_link):
    """
    從 Google Drive 共用連結中提取檔案 ID，
    並返回直接存取圖片的連結。
    """
    match = re.search(r'/d/([^/]+)', share_link)
    if match:
        file_id = match.group(1)
        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
        return direct_link
    else:
        raise ValueError("無法從共用連結中提取檔案 ID")

# 請替換成你的 Google Drive 共用連結
share_link = "https://drive.google.com/file/d/1C5AAf9h_k8kxxlLuA2oxJf_dNAFLZoy6/view?usp=drive_link"
direct_image_url = convert_drive_link(share_link)
print("Direct image URL:", direct_image_url)

# 1. 下載圖片
response = requests.get(direct_image_url)
if response.status_code != 200:
    raise Exception("Unable to download the image from Google Drive.")
img = Image.open(BytesIO(response.content))

# 2. 取得圖片尺寸
width, height = img.size
print(f"Image resolution: width {width} pixels, height {height} pixels")

# 3. 計算四邊保留 10% 邊界空間
margin_x = width * 0.1
margin_y = height * 0.1
print(f"Margin: {margin_x:.2f} pixels horizontally, {margin_y:.2f} pixels vertically")

# 內部區域邊界
inner_left = margin_x
inner_right = width - margin_x
inner_top = margin_y
inner_bottom = height - margin_y

# 4. 在內部區域內生成 4x4 均勻分布的 16 個點
x_coords = np.linspace(inner_left, inner_right, 4)
y_coords = np.linspace(inner_top, inner_bottom, 4)
points = []
for y in y_coords:
    for x in x_coords:
        points.append((x, y))

# 5. 計算每個點與圖片邊界的距離：Left, Right, Top, Bottom
data = []
for (x, y) in points:
    left = x          # 距離左邊界
    right = width - x # 距離右邊界
    top = y           # 距離上邊界
    bottom = height - y  # 距離下邊界
    data.append({
        "x": x,
        "y": y,
        "Left Distance": left,
        "Right Distance": right,
        "Top Distance": top,
        "Bottom Distance": bottom
    })

# 6. 使用 pandas 建立 DataFrame 並輸出成 CSV (欄位名稱皆用英文)
df = pd.DataFrame(data)
csv_filename = "image_points.csv"
df.to_csv(csv_filename, index=False, encoding="utf-8-sig")
print("Point data has been saved to", csv_filename)
print(df)

# 7. 繪製圖片與打點結果 (以英文標註)
plt.figure(figsize=(8, 6))
plt.imshow(img)
for (x, y) in points:
    plt.plot(x, y, "ro")  # 紅色圓點
    plt.text(x + 5, y + 5, f"({int(x)},{int(y)})", color="yellow", fontsize=8)
plt.title("Image with 16 Uniform Points in Inner Area (10% Margin)")
plt.axis("off")
plt.show()
