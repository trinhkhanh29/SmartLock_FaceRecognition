// NodeJS_Interface/server/services/pythonService.js
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Biến toàn cục quản lý tiến trình
let recognitionProcess = null;
let isRunning = false;

// === Đường dẫn script Python ===
const getScriptPath = (scriptName) => {
  return path.join(__dirname, "../../../PyCharm/src", scriptName);
};

// === Khởi động nhận diện (Recognize.py) ===
export const startFaceRecognition = () => {
  return new Promise((resolve) => {
    if (isRunning || recognitionProcess) {
      return resolve({ success: false, message: "Nhận diện đã đang chạy!" });
    }

    const scriptPath = getScriptPath("Recognize.py");
    const pythonCmd = process.env.PYTHON_PATH || "python";

    recognitionProcess = spawn(pythonCmd, [scriptPath], {
      shell: true,
      stdio: "pipe"
    });

    isRunning = true;

    recognitionProcess.stdout.on("data", (data) => {
      console.log(`[Recognize.py] ${data}`);
    });

    recognitionProcess.stderr.on("data", (data) => {
      console.error(`[Recognize.py ERROR] ${data}`);
    });

    recognitionProcess.on("close", (code) => {
      console.log(`[Recognize.py] Dừng với code: ${code}`);
      recognitionProcess = null;
      isRunning = false;
      resolve({ success: true, message: `Đã dừng (code: ${code})` });
    });

    recognitionProcess.on("error", (err) => {
      console.error(`[Recognize.py] Lỗi spawn: ${err}`);
      recognitionProcess = null;
      isRunning = false;
      resolve({ success: false, message: `Lỗi: ${err.message}` });
    });

    setTimeout(() => {
      resolve({ success: true, message: "Đã khởi động nhận diện!" });
    }, 500);
  });
};

// === Dừng nhận diện ===
export const stopFaceRecognition = () => {
  return new Promise((resolve) => {
    if (!recognitionProcess || !isRunning) {
      return resolve({ success: false, message: "Không có tiến trình nào đang chạy!" });
    }

    recognitionProcess.kill("SIGTERM");
    recognitionProcess = null;
    isRunning = false;

    resolve({ success: true, message: "Đã dừng nhận diện!" });
  });
};

// === Trạng thái ===
export const getStatus = () => {
  return {
    isRunning,
    message: isRunning ? "Đang nhận diện..." : "Đã dừng"
  };
};

// === Chạy trực tiếp (không quản lý tiến trình) ===
export const startDirectRecognition = async () => {
  const { runPythonScript } = await import("../utils/execPython.js");
  try {
    const result = await runPythonScript("Recognize.py", []);
    return { success: true, message: "Chạy thành công!", output: result };
  } catch (error) {
    return { success: false, message: `Lỗi: ${error.message}` };
  }
};

// === Dừng direct (không dùng) ===
export const stopDirectRecognition = () => {
  return { success: false, message: "Không hỗ trợ dừng direct mode!" };
};