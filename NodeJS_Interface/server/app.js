// server/app.js
import express from "express";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";

dotenv.config();
const app = express();
const PORT = process.env.PORT || 3000;

// Thiết lập đường dẫn tuyệt đối
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Cấu hình view engine (EJS)
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));

// Cho phép đọc dữ liệu từ form POST
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Public folder (CSS, JS, Images)
app.use(express.static(path.join(__dirname, "public")));

// Import routes
import faceRouter from "./routes/faceRoutes.js"; // Sửa từ face.js -> faceRoutes.js
import apiRouter from "./routes/api.js"; // Thêm router cho API

// Route để render trang upload.ejs
// Route này phải được đặt TRƯỚC app.use('/face', faceRouter) để được ưu tiên xử lý.
app.get('/face/upload-page', (req, res) => {
  res.render('upload'); // Đảm bảo 'upload.ejs' nằm trong thư mục views
});

app.use("/face", faceRouter);
app.use("/api", apiRouter); // Sử dụng API router với tiền tố /api

// Trang chủ
app.get("/", (req, res) => {
  res.render("index", { title: "Hệ thống nhận diện khuôn mặt" });
});

// Khởi động server
app.listen(PORT, () => {
  console.log(`✅ Server đang chạy tại http://localhost:${PORT}`);
});
