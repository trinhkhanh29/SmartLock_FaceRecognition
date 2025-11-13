// server/app.js
import express from "express";
import dotenv from "dotenv";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import admin from "firebase-admin";
import crypto from "crypto";
import http from "http";
import { Server } from "socket.io";
import fs from "fs"; // THÊM DÒNG NÀY

dotenv.config();
const app = express();
const server = http.createServer(app); // Tạo server http
const io = new Server(server); // Gắn socket.io vào server
const PORT = process.env.PORT || 3000;

// Thiết lập đường dẫn tuyệt đối (ĐÃ DI CHUYỂN LÊN ĐÂY)
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- KHỞI TẠO FIREBASE ADMIN ---
// Sửa đường dẫn để trỏ đến thư mục .env trong PyCharm
const serviceAccount = path.join(__dirname, '..', '..', 'PyCharm', '.env', 'firebase_credentials.json');
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: 'smartlockfacerecognition.firebasestorage.app',
  databaseURL: process.env.FIREBASE_DATABASE_URL // Sửa lại để đọc từ .env
});
const bucket = admin.storage().bucket();
const db = admin.database();
// ---------------------------------

// Cấu hình view engine (EJS)
app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"))

// Cho phép đọc dữ liệu từ form POST
app.use(express.urlencoded({ extended: true }));
app.use(express.json());
// Middleware để xử lý raw body cho stream
app.use('/api/livestream', express.raw({ type: 'image/jpeg', limit: '10mb' }));

// Public folder (CSS, JS, Images)
app.use(express.static(path.join(__dirname, "public")));

// ================== GUEST REGISTRATION ROUTES ==================
app.get('/register/:lockId', (req, res) => {
    const { lockId } = req.params;
    res.render('register_face', { lockId });
});

app.post('/register', (req, res) => {
    const { userName, lockId } = req.body;
    const userId = crypto.randomBytes(4).toString('hex');

    if (!userName || !lockId) {
        return res.status(400).send("Thiếu thông tin Tên hoặc Lock ID.");
    }

    console.log(`Khách đăng ký: Lock ID: ${lockId}, User ID: ${userId}, Tên: ${userName}`);

    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');
    const pythonProcess = spawn('python', [pythonScriptPath, userId, userName, lockId, '--pending']);

    pythonProcess.on('close', (code) => {
        console.log(`[Python Register] child process exited with code ${code}`);
    });

    res.render('processing', {
        userName: userName,
        userId: userId,
        lockId: lockId,
        message: "Yêu cầu đăng ký của bạn đã được gửi. Vui lòng chờ quản trị viên phê duyệt."
    });
});
// =============================================================

// Import routes
import faceRouter from "./routes/faceRoutes.js"; // Sửa từ face.js -> faceRoutes.js
import apiRouter from "./routes/api.js"; // Thêm router cho API

// Route để render trang upload.ejs
// Route này phải được đặt TRƯỚC app.use('/face', faceRouter) để được ưu tiên xử lý.
app.get('/face/upload-page', (req, res) => {
  res.render('upload'); // Đảm bảo 'upload.ejs' nằm trong thư mục views
});

// Route để hiển thị trang nhập thông tin thu thập khuôn mặt
app.get('/face/collect/:lockId', (req, res) => {
  const { lockId } = req.params;
  res.render('collect_face', { lockId }); // Truyền lockId cho view
});

// Route để xử lý dữ liệu POST từ form thu thập
app.post('/face/collect', (req, res) => {
  const { userId, userName, lockId } = req.body; // Thêm lockId

  if (!userId || !userName || !lockId) {
    return res.status(400).send("Thiếu thông tin User ID, User Name, hoặc Lock ID.");
  }

  console.log(`Bắt đầu thu thập cho Lock ID: ${lockId}, User ID: ${userId}, Tên: ${userName}`);

  // Đường dẫn đến kịch bản Python
  const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');

  // Gọi kịch bản Python với lockId
  const pythonProcess = spawn('python', [pythonScriptPath, userId, userName, lockId]);

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
    userId: userId,
    lockId: lockId,
    message: "Quá trình thu thập khuôn mặt đã bắt đầu. Vui lòng nhìn vào cửa sổ camera."
  });
});

// ================== LOCK MANAGEMENT ROUTES ==================
app.get('/locks', async (req, res) => {
    try {
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.once('value');
        const locks = snapshot.val() ? Object.values(snapshot.val()) : [];
        res.render('locks', { locks });
    } catch (error) {
        console.error("Lỗi khi tải danh sách khóa:", error);
        res.status(500).send("Không thể tải danh sách khóa.");
    }
});

app.post('/locks/create', async (req, res) => {
    const { lockName } = req.body;
    if (!lockName) {
        return res.status(400).send('Tên khóa là bắt buộc.');
    }
    try {
        const lockId = crypto.randomBytes(8).toString('hex'); // Tạo ID ngẫu nhiên
        const locksRef = db.ref(`locks_registry/${lockId}`);
        await locksRef.set({
            id: lockId,
            name: lockName,
            createdAt: new Date().toISOString()
        });
        console.log(`Đã tạo khóa mới: ${lockName} với ID: ${lockId}`);
        res.redirect('/locks');
    } catch (error) {
        console.error("Lỗi khi tạo khóa mới:", error);
        res.status(500).send('Lỗi server khi tạo khóa.');
    }
});

app.post('/locks/delete', async (req, res) => {
    const { lockId } = req.body;
    if (!lockId) {
        return res.status(400).send('Thiếu Lock ID.');
    }
    try {
        // Xóa registry
        await db.ref(`locks_registry/${lockId}`).remove();
        // Xóa activity log
        await db.ref(`locks/${lockId}`).remove();
        // Xóa ảnh trên storage
        await bucket.deleteFiles({ prefix: `locks/${lockId}/` });

        console.log(`Đã xóa hoàn toàn khóa: ${lockId}`);
        res.redirect('/locks');
    } catch (error) {
        console.error(`Lỗi khi xóa khóa ${lockId}:`, error);
        res.status(500).send('Lỗi server khi xóa khóa.');
    }
});
// ==========================================================

// ================== SERVICE MANAGEMENT ==================
const runningServices = {};

app.post('/service/start/:lockId', (req, res) => {
    const { lockId } = req.params;
    const { mode } = req.body; // face_only hoặc face_pin

    if (runningServices[lockId]) {
        return res.status(400).send(`Dịch vụ cho khóa ${lockId} đã chạy.`);
    }

    console.log(`Bắt đầu dịch vụ nhận diện cho khóa: ${lockId} với chế độ ${mode}`);
    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'Recognize.py');
    const pythonProcess = spawn('python', [pythonScriptPath, '--lock_id', lockId, '--mode', mode]);

    runningServices[lockId] = pythonProcess;

    pythonProcess.stdout.on('data', (data) => console.log(`[Recognize-${lockId}] stdout: ${data}`));
    pythonProcess.stderr.on('data', (data) => console.error(`[Recognize-${lockId}] stderr: ${data}`));

    pythonProcess.on('close', (code) => {
        console.log(`Dịch vụ cho khóa ${lockId} đã dừng với mã ${code}.`);
        delete runningServices[lockId];
    });

    res.redirect(`/dashboard/${lockId}?service=started`);
});

app.post('/service/stop/:lockId', (req, res) => {
    const { lockId } = req.params;
    if (runningServices[lockId]) {
        runningServices[lockId].kill('SIGINT');
        console.log(`Đã gửi yêu cầu dừng cho dịch vụ của khóa ${lockId}.`);
    }
    res.redirect(`/dashboard/${lockId}?service=stopped`);
});
// ========================================================

// ================== DASHBOARD ROUTES ==================
app.get('/livestream/:lockId', (req, res) => {
    const { lockId } = req.params;
    res.render('livestream', { lockId });
});

// Sửa route để nhận lockId
app.get('/dashboard/:lockId', async (req, res) => {
  const { lockId } = req.params;
  try {
    // Lọc file theo lockId
    const [files] = await bucket.getFiles({ prefix: `locks/${lockId}/faces/` });
    const users = {};

    files.forEach(file => {
      const parts = file.name.split('/'); // locks/{lockId}/faces/{userId}/{fileName}
      if (parts.length >= 5) {
        const userId = parts[3];
        const fileName = parts[4];
        const userNameMatch = fileName.match(/^(\d+|[a-f0-9]+)_(.+?)_/);
        if (userNameMatch) {
            const userName = userNameMatch[2].replace(/_/g, ' ');
            if (!users[userId]) {
                users[userId] = { id: userId, name: userName, imageCount: 0, sampleImage: null };
            }
            users[userId].imageCount++;
            if (!users[userId].sampleImage) {
                users[userId].sampleImage = `https://storage.googleapis.com/${bucket.name}/${file.name}`;
            }
        }
      }
    });

    // Lấy người dùng chờ duyệt
    const pendingUsersRef = db.ref(`locks/${lockId}/pending_users`);
    const pendingSnapshot = await pendingUsersRef.once('value');
    const pendingUsers = [];
    if(pendingSnapshot.exists()){
        pendingSnapshot.forEach(child => {
            pendingUsers.push({ id: child.key, ...child.val() });
        });
    }

    // Lọc log theo lockId
    const activityLogRef = db.ref(`locks/${lockId}/activity_log`).orderByChild('timestamp').limitToLast(20);
    const snapshot = await activityLogRef.once('value');
    const logs = [];
    snapshot.forEach(childSnapshot => {
        logs.unshift({ id: childSnapshot.key, ...childSnapshot.val() });
    });

    const serviceStatus = runningServices[lockId] ? 'running' : 'stopped';
    res.render('dashboard', { users: Object.values(users), logs, lockId, pendingUsers, serviceStatus });
  } catch (error) {
    console.error("Lỗi khi tải dữ liệu dashboard:", error);
    res.status(500).send("Không thể tải dữ liệu dashboard.");
  }
});

app.post('/dashboard/approve-user', async (req, res) => {
    const { userId, lockId } = req.body;
    try {
        const pendingPrefix = `locks/${lockId}/pending_faces/${userId}/`;
        const [pendingFiles] = await bucket.getFiles({ prefix: pendingPrefix });

        for (const file of pendingFiles) {
            const newName = file.name.replace('pending_faces', 'faces');
            await file.move(newName);
        }

        await db.ref(`locks/${lockId}/pending_users/${userId}`).remove();
        console.log(`Đã phê duyệt người dùng ${userId} cho khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("Lỗi khi phê duyệt:", error);
        res.status(500).send("Lỗi server khi phê duyệt.");
    }
});

app.post('/dashboard/reject-user', async (req, res) => {
    const { userId, lockId } = req.body;
    try {
        await bucket.deleteFiles({ prefix: `locks/${lockId}/pending_faces/${userId}/` });
        await db.ref(`locks/${lockId}/pending_users/${userId}`).remove();
        console.log(`Đã từ chối người dùng ${userId} cho khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("Lỗi khi từ chối:", error);
        res.status(500).send("Lỗi server khi từ chối.");
    }
});

app.post('/dashboard/delete-user', async (req, res) => {
    const { userId, lockId } = req.body; // Thêm lockId
    if (!userId || !lockId) {
        return res.status(400).send('Thiếu User ID hoặc Lock ID');
    }
    try {
        // Xóa file theo lockId
        await bucket.deleteFiles({ prefix: `locks/${lockId}/faces/${userId}/` });
        console.log(`Đã xóa tất cả ảnh của người dùng ${userId} từ khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`Lỗi khi xóa người dùng ${userId}:`, error);
        res.status(500).send('Lỗi server khi xóa người dùng.');
    }
});

app.post('/dashboard/train-model', (req, res) => {
    const { lockId } = req.body;
    if (!lockId) {
        return res.status(400).send('Thiếu Lock ID');
    }
    console.log(`Bắt đầu train model cho khóa: ${lockId}`);

    // XÓA FILE EMBEDDINGS CŨ ĐỂ BẮT BUỘC TẠO LẠI
    const embeddingsPath = path.join(__dirname, '..', '..', 'PyCharm', 'dataset', lockId, 'embeddings.pkl');
    if (fs.existsSync(embeddingsPath)) {
        try {
            fs.unlinkSync(embeddingsPath);
            console.log(`Đã xóa embeddings cũ: ${embeddingsPath}`);
        } catch (err) {
            console.error(`Lỗi khi xóa embeddings: ${err}`);
        }
    }

    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'trainer.py');
    const pythonProcess = spawn('python', [pythonScriptPath, lockId]);

    pythonProcess.stdout.on('data', (data) => console.log(`[Trainer] stdout: ${data}`));
    pythonProcess.stderr.on('data', (data) => console.error(`[Trainer] stderr: ${data}`));

    pythonProcess.on('close', (code) => {
        console.log(`[Trainer] quá trình kết thúc với mã ${code}`);
        res.redirect(`/dashboard/${lockId}?status=trained`);
    });
});

app.post('/dashboard/clear-logs', async (req, res) => {
    const { lockId } = req.body;
    if (!lockId) {
        return res.status(400).send('Thiếu Lock ID');
    }
    try {
        await db.ref(`locks/${lockId}/activity_log`).remove();
        console.log(`Đã xóa lịch sử truy cập của khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`Lỗi khi xóa lịch sử của khóa ${lockId}:`, error);
        res.status(500).send('Lỗi server khi xóa lịch sử.');
    }
});
// ======================================================

// ================== API ROUTES =======================
app.post('/api/livestream/:lockId', (req, res) => {
    const { lockId } = req.params;
    const frameBuffer = req.body;
    // Chuyển buffer thành base64
    const base64Frame = frameBuffer.toString('base64');
    // Gửi đến các client trong phòng của lockId
    io.to(lockId).emit('new_frame', { frame: base64Frame });
    res.sendStatus(200);
});
// ======================================================

app.use("/face", faceRouter);
app.use("/api", apiRouter); // Sử dụng API router với tiền tố /api

// Trang chủ
app.get("/", (req, res) => {
  // Sửa trang chủ để chuyển hướng đến trang quản lý khóa
  res.redirect('/locks');
});

// Socket.IO connection
io.on('connection', (socket) => {
    console.log('Một client đã kết nối:', socket.id);
    socket.on('join_room', (lockId) => {
        socket.join(lockId);
        console.log(`Client ${socket.id} đã tham gia phòng ${lockId}`);
    });
    socket.on('disconnect', () => {
        console.log('Client đã ngắt kết nối:', socket.id);
    });
});

// Khởi động server
server.listen(PORT, () => { // Sửa app.listen -> server.listen
  console.log(`✅ Server đang chạy tại http://localhost:${PORT}`);
});
