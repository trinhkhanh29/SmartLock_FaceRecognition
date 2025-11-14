# image_enhancement.py (phiên bản cải thiện để xử lý lóa tốt hơn)
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

def detect_high_light(image, threshold=170):  # HẠ NGƯỠNG XUỐNG 170 ĐỂ DỄ TRIGGER HƠN VỚI LÓA NHẸ
    """
    Phát hiện ảnh có ánh sáng quá gắt hoặc bị lóa.
    Returns: (is_high_light: bool, mean_brightness: float)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.median(gray)
    return mean_brightness > threshold, mean_brightness

def detect_glare(image, bright_threshold=230, percent_threshold=2):  # MỚI: Phát hiện lóa dựa trên % pixel sáng cao
    """
    Phát hiện lóa (glare) dựa trên phần trăm pixel có độ sáng vượt ngưỡng.
    Returns: (has_glare: bool, glare_percent: float)
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    glare_percent = np.sum(gray > bright_threshold) / gray.size * 100
    return glare_percent > percent_threshold, glare_percent

def reduce_glare(image):
    """
    Giảm lóa và cân bằng lại ảnh bị sáng gắt (cải thiện: thêm gamma + bilateral filter).
    """
    # Chuyển sang HSV để xử lý Value (độ sáng)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)

    # CLAHE trên V với clipLimit=2.0 để giảm chênh lệch sáng/tối
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    v = clahe.apply(v)

    # Gộp lại và chuyển về BGR
    hsv = cv2.merge([h, s, v])
    enhanced = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # Áp dụng gamma >1 để làm tối highlight tự nhiên
    gamma = 1.2
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in np.arange(256)]).astype("uint8")
    enhanced = cv2.LUT(enhanced, table)

    # Thêm bilateral filter để giảm nhiễu lóa mà giữ cạnh khuôn mặt
    enhanced = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)

    return enhanced

def auto_gamma(image):
    """
    Tự động điều chỉnh gamma dựa trên độ sáng trung bình của ảnh.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = np.mean(gray)
    
    # Map độ sáng [0,255] sang gamma [2.2, 1.2, 0.8]
    gamma = np.interp(mean_brightness, [0, 128, 255], [2.2, 1.2, 0.8])
    inv_gamma = 1.0 / gamma

    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in np.arange(256)]).astype("uint8")
    return cv2.LUT(image, table)

def enhance_image_for_low_light(image):
    """
    Cải thiện ảnh trong điều kiện ánh sáng yếu (sử dụng phiên bản mạnh).
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    # CLAHE mạnh hơn cho low light
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    l = clahe.apply(l)

    lab = cv2.merge([l, a, b])
    enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # Giảm nhiễu
    enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 10, 10, 7, 21)

    # Làm sắc nét
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 3)
    enhanced = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)

    # Auto gamma
    enhanced = auto_gamma(enhanced)

    return enhanced

def auto_brightness_contrast(image, clip_hist_percent=1.5):  # TĂNG LÊN 1.5 ĐỂ CLIP MẠNH HƠN, GIẢM LÓA NHẸ
    """
    Tự động điều chỉnh độ sáng & tương phản cho ảnh bình thường.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist_size = len(hist)

    accumulator = np.cumsum(hist)

    maximum = accumulator[-1]
    clip_hist_percent *= (maximum / 100.0)
    clip_hist_percent /= 2.0

    minimum_gray = np.searchsorted(accumulator, clip_hist_percent)
    maximum_gray = np.searchsorted(accumulator, maximum - clip_hist_percent)

    if maximum_gray - minimum_gray == 0:
        return image

    alpha = 255 / (maximum_gray - minimum_gray)
    beta = -minimum_gray * alpha

    auto_result = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)
    return auto_result

def preprocess_image(image):
    """
    Pipeline tiền xử lý hoàn chỉnh:
    - Tự phát hiện low light, high light, glare, hoặc bình thường
    - Áp dụng xử lý tương ứng
    """
    low_light, brightness = detect_low_light(image)
    high_light, brightness_high = detect_high_light(image)
    glare, glare_percent = detect_glare(image)

    if low_light:
        print(f"[INFO] Ảnh ánh sáng yếu (brightness={brightness:.2f}) → Tăng sáng...")
        processed = enhance_image_for_low_light(image)
    elif high_light or glare:
        print(f"[INFO] Ảnh lóa/gắt (brightness={brightness_high:.2f}, glare={glare_percent:.1f}%) → Giảm lóa...")
        processed = reduce_glare(image)
    else:
        print(f"[INFO] Ảnh bình thường (brightness={brightness:.2f}) → Cân bằng...")
        processed = auto_brightness_contrast(image)

    return processed

# Hàm cũ để tương thích
def adjust_gamma(image, gamma=1.5):
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    return cv2.LUT(image, table)