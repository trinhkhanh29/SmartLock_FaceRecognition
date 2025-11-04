// controllers/faceController.js
import {
  startFaceRecognition,
  stopFaceRecognition,
  getStatus as getPythonServiceStatus,
  startDirectRecognition,
  stopDirectRecognition,
  runPythonScript // ← Đảm bảo có trong pythonService.js
} from "../services/pythonService.js";

// ========================================
// 🧠 NHẬN DIỆN KHUÔN MẶT (Recognize.py)
// ========================================
export const recognizeFace = async (req, res) => {
  try {
    console.log("[Controller] Bắt đầu nhận diện khuôn mặt...");
    const result = await runPythonScript("Recognize.py", []);

    res.json({
      success: true,
      message: "Nhận diện khuôn mặt hoàn tất!",
      data: {
        result: result.trim(),
        timestamp: new Date().toLocaleString("vi-VN")
      }
    });
  } catch (error) {
    console.error("❌ Lỗi nhận diện khuôn mặt:", error.message || error);
    res.status(500).json({
      success: false,
      message: "Không thể nhận diện khuôn mặt.",
      error: error.message || "Lỗi không xác định"
    });
  }
};

// ========================================
// ▶️ BẮT ĐẦU NHẬN DIỆN (quản lý tiến trình)
// ========================================
export const startRecognition = async (req, res) => {
  try {
    const result = await startFaceRecognition();
    if (result.success) {
      return res.json({
        success: true,
        message: result.message,
        data: { isRunning: true }
      });
    }
    res.status(400).json({ success: false, message: result.message });
  } catch (error) {
    console.error("Lỗi startRecognition:", error);
    res.status(500).json({ success: false, message: "Lỗi server: " + error.message });
  }
};

// ========================================
// ⏹ DỪNG NHẬN DIỆN
// ========================================
export const stopRecognition = async (req, res) => {
  try {
    const result = await stopFaceRecognition();
    if (result.success) {
      return res.json({
        success: true,
        message: result.message,
        data: { isRunning: false }
      });
    }
    res.status(400).json({ success: false, message: result.message });
  } catch (error) {
    console.error("Lỗi stopRecognition:", error);
    res.status(500).json({ success: false, message: "Lỗi server: " + error.message });
  }
};

// ========================================
// 🟢 LẤY TRẠNG THÁI
// ========================================
export const getStatus = (req, res) => {
  try {
    const status = getPythonServiceStatus(); // ← Hàm sync
    res.json({
      success: true,
      data: {
        isRunning: status.isRunning,
        message: status.message,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Lỗi getStatus:", error);
    res.status(500).json({ success: false, message: "Lỗi server" });
  }
};

// ========================================
// 📷 CHẠY TRỰC TIẾP (không quản lý tiến trình)
// ========================================
export const startDirect = async (req, res) => {
  try {
    const result = await startDirectRecognition();
    if (result.success) {
      return res.json({
        success: true,
        message: result.message,
        data: { isRunning: true, output: result.output }
      });
    }
    res.status(400).json({ success: false, message: result.message });
  } catch (error) {
    console.error("Lỗi startDirect:", error);
    res.status(500).json({ success: false, message: "Lỗi server: " + error.message });
  }
};

export const stopDirect = (req, res) => {
  const result = stopDirectRecognition();
  res.json({
    success: result.success,
    message: result.message,
    data: { isRunning: false }
  });
};