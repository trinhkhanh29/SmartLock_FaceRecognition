import { Router } from "express";
import { spawn } from "child_process";
import path from "path";
import { fileURLToPath } from "url";

const router = Router();

// Thiết lập đường dẫn tuyệt đối để tìm kịch bản Python
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pythonScriptPath = path.join(__dirname, "../../../PyCharm/src/Recognize.py");
const pythonExecutable = "python"; // Hoặc "python3" tùy vào môi trường của bạn

router.get("/recognize", (req, res) => {
  const { mode } = req.query; // CHỈ LẤY MODE

  const args = [pythonScriptPath];
  if (mode) {
    args.push("--mode", mode);
  }

  console.log(`[NodeJS] Executing: ${pythonExecutable} ${args.join(" ")}`);

  const pythonProcess = spawn(pythonExecutable, args);

  pythonProcess.stdout.on("data", (data) => {
    console.log(`[Python] stdout: ${data}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    console.error(`[Python] stderr: ${data}`);
  });

  pythonProcess.on("close", (code) => {
    console.log(`[NodeJS] Python process exited with code ${code}`);
    res.redirect(`/?status=recognized&exit_code=${code}`);
  });
});

// Route cho việc thu thập dữ liệu (nếu cần)
router.get("/collect", (req, res) => {
  // Tương tự, bạn có thể gọi một kịch bản Python khác ở đây
  res.redirect("/?status=collect_started");
});

export default router;
