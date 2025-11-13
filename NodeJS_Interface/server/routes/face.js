// routes/face.js
import express from "express";
import { runPythonScript } from "../utils/execPython.js";

const router = express.Router();

// GET: Route mới để nhận diện khuôn mặt
router.get("/recognize", async (req, res) => {
  try {
    // Gọi script Recognize.py
    const result = await runPythonScript("Recognize.py", []);
    
    // Render trang kết quả
    res.render("recognize_result", {
      title: "Kết quả nhận diện",
      message: "Quá trình nhận diện khuôn mặt đã hoàn tất.",
      output: result
    });
  } catch (error) {
    console.error("Lỗi khi nhận diện khuôn mặt:", error.message || error);
    
    res.status(500).render("error", {
      title: "Lỗi hệ thống",
      message: "Không thể thực hiện nhận diện khuôn mặt. Vui lòng thử lại.",
      error: error.message
    });
  }
});

// GET: Trang thu thập khuôn mặt
router.get("/collect", (req, res) => {
  res.render("collect_face", {
    title: "Thu thập khuôn mặt",
    page: "collect"
  });
});

// POST: Xử lý thu thập khuôn mặt
router.post("/collect", async (req, res) => {
  const { userId, userName } = req.body;

  if (!userId || !userName) {
    return res.status(400).render("error", {
      title: "Lỗi",
      message: "Vui lòng nhập ID và Tên người dùng!"
    });
  }

  try {
    const result = await runPythonScript("facedetect.py", [userId, userName]);
    
    res.render("success", {
      title: "Thành công",
      message: "Thu thập khuôn mặt thành công!",
      output: result,
      userId,
      userName
    });
  } catch (error) {
    console.error("Lỗi thu thập khuôn mặt:", error.message || error);
    
    res.status(500).render("error", {
      title: "Lỗi hệ thống",
      message: "Không thể thu thập khuôn mặt. Vui lòng thử lại.",
      error: error.message
    });
  }
});

export default router;