// server/app.js
import express from "express";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process"; // Thêm dòng này

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

// Route để hiển thị trang nhập thông tin thu thập khuôn mặt
app.get('/face/collect', (req, res) => {
  res.render('collect_face'); // Render file collect_face.ejs
});

// Route để xử lý dữ liệu POST từ form thu thập
app.post('/face/collect', (req, res) => {
  const { userId, userName } = req.body;

  if (!userId || !userName) {
    return res.status(400).send("Mã người dùng và Tên người dùng là bắt buộc.");
  }

  console.log(`Bắt đầu thu thập cho ID: ${userId}, Tên: ${userName}`);

  // Đường dẫn đến kịch bản Python
  const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');

  // Gọi kịch bản Python
  const pythonProcess = spawn('python', [pythonScriptPath, userId, userName]);

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] stdout: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python] stderr: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`[Python] child process exited with code ${code}`);
  });

  // Phản hồi bằng cách render một trang EJS mới
  res.render('processing', {
    userName: userName,
    userId: userId
  });
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
