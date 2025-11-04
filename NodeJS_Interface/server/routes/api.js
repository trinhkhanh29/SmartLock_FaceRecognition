// routes/api.js
import express from "express";
import {
  recognizeFace,
  startRecognition,
  stopRecognition,
  getStatus,
  startDirect,
  stopDirect
} from "../controllers/faceController.js";

const router = express.Router();

// ========================================
// API Routes for Face Recognition
// ========================================

// POST: Chạy script nhận diện một lần và trả về kết quả
router.post("/recognize", recognizeFace);

// POST: Bắt đầu tiến trình nhận diện chạy nền
router.post("/recognize/start", startRecognition);

// POST: Dừng tiến trình nhận diện chạy nền
router.post("/recognize/stop", stopRecognition);

// GET: Lấy trạng thái của tiến trình nhận diện
router.get("/recognize/status", getStatus);

// POST: Chạy script trực tiếp (không quản lý tiến trình)
router.post("/direct/start", startDirect);

// POST: Dừng script chạy trực tiếp
router.post("/direct/stop", stopDirect);

export default router;
