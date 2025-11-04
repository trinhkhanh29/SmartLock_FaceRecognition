// server/utils/execPython.js
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

// Thiết lập đường dẫn đến thư mục chứa script Python
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pythonScriptsPath = path.join(__dirname, "../../../PyCharm/src");

/**
 * Thực thi một script Python.
 * @param {string} scriptName - Tên của script (ví dụ: 'Recognize.py').
 * @param {string[]} args - Các tham số cho script.
 * @returns {Promise<string>} - Output từ script.
 */
export function runPythonScript(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(pythonScriptsPath, scriptName);
    const pythonProcess = spawn("python", [scriptPath, ...args]);

    let output = "";
    let errorOutput = "";

    pythonProcess.stdout.on("data", (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on("data", (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on("close", (code) => {
      if (code !== 0) {
        console.error(`Lỗi khi chạy script Python '${scriptName}':`, errorOutput);
        return reject(new Error(`Python script exited with code ${code}: ${errorOutput}`));
      }
      resolve(output);
    });

    pythonProcess.on("error", (err) => {
        console.error(`Không thể khởi động script Python '${scriptName}':`, err);
        reject(err);
    });
  });
}
