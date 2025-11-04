import { runPythonScript } from "../utils/execPython.js";

// Biến để quản lý tiến trình chạy nền
let recognitionProcess = null;
let processStatus = {
  isRunning: false,
  message: "Tiến trình chưa được khởi động."
};

// Bắt đầu nhận diện (chạy nền)
export const startFaceRecognition = async () => {
  if (recognitionProcess) {
    return { success: false, message: "Tiến trình đã đang chạy." };
  }
  // Logic để khởi động script chạy nền ở đây (nếu cần)
  // Ví dụ: recognitionProcess = spawn(...)
  processStatus = { isRunning: true, message: "Tiến trình đã bắt đầu." };
  return { success: true, message: "Đã bắt đầu tiến trình nhận diện." };
};

// Dừng nhận diện
export const stopFaceRecognition = async () => {
  if (!recognitionProcess) {
    return { success: false, message: "Không có tiến trình nào đang chạy." };
  }
  // Logic để dừng script
  // Ví dụ: recognitionProcess.kill();
  recognitionProcess = null;
  processStatus = { isRunning: false, message: "Tiến trình đã dừng." };
  return { success: true, message: "Đã dừng tiến trình nhận diện." };
};

// Lấy trạng thái
export const getStatus = () => {
  return processStatus;
};

// Chạy trực tiếp (không quản lý)
export const startDirectRecognition = () => {
  return runPythonScript("Recognize.py", []);
};

// Dừng trực tiếp (thường không cần thiết cho script chạy một lần)
export const stopDirectRecognition = () => {
  return { success: true, message: "Không có hành động nào được thực hiện cho script chạy một lần." };
};

// Export runPythonScript để faceController có thể sử dụng
export { runPythonScript };
