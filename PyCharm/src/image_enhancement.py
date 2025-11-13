import cv2
import numpy as np

def detect_low_light(image, threshold=60):
    """
    Phát hiện ảnh có ánh sáng yếu dựa trên độ sáng trung bình.
    Returns: (is_low_light: bool, mean_brightness: float)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.median(gray)  # median cho kết quả ổn định hơn mean
    return mean_brightness < threshold, mean_brightness


def auto_gamma(image):
    """
    Tự động điều chỉnh gamma dựa trên độ sáng trung bình của ảnh.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray)
    
    # Map độ sáng [0,255] sang gamma [2.2, 1.0, 0.8]
    gamma = np.interp(mean_brightness, [0, 128, 255], [2.2, 1.2, 0.8])
    inv_gamma = 1.0 / gamma

    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in np.arange(256)]).astype("uint8")
    return cv2.LUT(image, table)


def enhance_image_for_low_light(image):
    """
    Cải thiện ảnh trong điều kiện ánh sáng yếu (Low-Light Enhancement)
    """
    # 1. Chuyển sang LAB để cân bằng độ sáng mà không ảnh hưởng màu
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # 2. Áp dụng CLAHE để tăng tương phản cục bộ
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    # 3. Gộp lại và chuyển về BGR
    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # 4. Giảm nhiễu màu
    enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 10, 10, 7, 21)

    # 5. Làm sắc nét bằng Unsharp Masking (giữ tự nhiên hơn sharpen kernel)
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 3)
    enhanced = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)

    # 6. Áp dụng Gamma tự động để tăng sáng nhẹ nếu cần
    enhanced = auto_gamma(enhanced)

    return enhanced


def auto_brightness_contrast(image, clip_hist_percent=1.0):
    """
    Tự động điều chỉnh độ sáng & tương phản cho ảnh bình thường
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_size = len(hist)

    # Tính toán cumulative histogram
    accumulator = np.cumsum(hist)

    maximum = accumulator[-1]
    clip_hist_percent *= (maximum / 100.0)
    clip_hist_percent /= 2.0

    # Tìm ngưỡng min/max sau khi cắt histogram
    minimum_gray = np.searchsorted(accumulator, clip_hist_percent)
    maximum_gray = np.searchsorted(accumulator, maximum - clip_hist_percent)

    if maximum_gray - minimum_gray == 0:
        return image  # tránh chia 0 khi ảnh quá đều

    alpha = 255 / (maximum_gray - minimum_gray)
    beta = -minimum_gray * alpha

    auto_result = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
    return auto_result


def preprocess_image(image):
    """
    Pipeline tiền xử lý hoàn chỉnh:
    - Tự phát hiện ảnh sáng yếu
    - Áp dụng xử lý tương ứng
    """
    low_light, brightness = detect_low_light(image)

    if low_light:
        print(f"[INFO] Ảnh ánh sáng yếu (brightness={brightness:.2f}) → Tăng sáng và tăng tương phản...")
        processed = enhance_image_for_low_light(image)
    else:
        print(f"[INFO] Ảnh sáng bình thường (brightness={brightness:.2f}) → Cân bằng sáng/tương phản...")
        processed = auto_brightness_contrast(image)

    return processed


# Giữ lại hàm adjust_gamma cũ để tương thích ngược (nếu cần)
def adjust_gamma(image, gamma=1.5):
    """
    Điều chỉnh gamma thủ công (deprecated, dùng auto_gamma thay thế)
    """
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255
                      for i in np.arange(0, 256)]).astype("uint8")
    return cv2.LUT(image, table)
