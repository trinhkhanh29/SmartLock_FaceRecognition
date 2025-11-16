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
import fs from "fs";
import session from 'express-session';
import flash from 'connect-flash';
import https from 'https';
import { cleanupOldLogs, limitLogsPerLock } from './utils/firebase-cleanup.js';
// THÊM: Import các service mới
import CleanupService from './services/cleanupService.js';
import CleanupScheduler from './services/cleanupScheduler.js';

dotenv.config();

// Thiết lập đường dẫn tuyệt đối
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- KHỞI TẠO FIREBASE ADMIN TRƯỚC (DI CHUYỂN LÊN ĐẦU) ---
const serviceAccount = path.join(__dirname, '..', '..', 'PyCharm', '.env', 'firebase_credentials.json');
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: 'smartlockfacerecognition.firebasestorage.app',
  databaseURL: process.env.FIREBASE_DATABASE_URL
});
const bucket = admin.storage().bucket();
const db = admin.database();
console.log('✅ Firebase initialized');

// KHỞI TẠO CÁC SERVICE
const cleanupService = new CleanupService(db);
const cleanupScheduler = new CleanupScheduler(cleanupService);

// SAU ĐÓ MỚI IMPORT MIDDLEWARE BẢO MẬT
import {
    loginLimiter,
    apiLimiter,
    serviceLimiter,
    helmetConfig,
    requireAuth,
    requireAdmin,
    requireLockAccess,
    logAudit,
    sanitizeInput,
    checkBruteForce,
    resetBruteForce,
    generateToken,
    initializeSecurity  // THÊM import này
} from './middleware/security.js';

// THÊM: Middleware xác thực API Key
const requireApiKey = (req, res, next) => {
    const apiKey = req.headers['x-api-key'];
    if (apiKey && apiKey === (process.env.EXTERNAL_API_KEY || 'SuperSecretApiKey_2025_ChangeMe')) {
        // Gán một user hệ thống để controller có thể sử dụng
        req.session.userId = 'system_telegram';
        req.session.role = 'system';
        return next();
    }
    // Nếu không có API key, fallback về xác thực session
    return requireAuth(req, res, next);
};

// KHỞI TẠO SECURITY VỚI DATABASE
initializeSecurity(db);

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const PORT = process.env.PORT || 3000;

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

// ================== SECURITY MIDDLEWARE ==================
app.use(helmetConfig); // Helmet security headers
app.use(sanitizeInput); // Input sanitization

// ================== SESSION AND FLASH (CẢI TIẾN BẢO MẬT) ==================
app.use(session({
    secret: process.env.SESSION_SECRET || 'smartlock-secret-key-2025',
    resave: false,
    saveUninitialized: false,
    cookie: {
        maxAge: 24 * 60 * 60 * 1000, // 24 hours
        httpOnly: true, // Bảo vệ khỏi XSS
        secure: process.env.NODE_ENV === 'production', // HTTPS only trong production
        sameSite: 'strict' // Bảo vệ khỏi CSRF
    },
    rolling: true // Reset expiry mỗi request
}));

app.use(flash());

// Middleware để truyền thông tin vào views
app.use((req, res, next) => {
    res.locals.user = req.session.userId || null;
    res.locals.userRole = req.session.role || null;
    res.locals.userLockId = req.session.lockId || null;
    res.locals.success = req.flash('success');
    res.locals.error = req.flash('error');
    res.locals.warning = req.flash('warning'); // THÊM DÒNG NÀY
    next();
});

// ================== AUTHENTICATION ROUTES (CẢI TIẾN) ==================
app.get('/login', (req, res) => {
    if (req.session.userId) {
        if (req.session.role === 'admin') {
            return res.redirect('/locks');
        } else {
            return res.redirect(`/dashboard/${req.session.lockId}`);
        }
    }
    res.render('login');
});

app.post('/login', loginLimiter, checkBruteForce, async (req, res) => {
    const { username, password } = req.body;
    const loginIP = req.ip || req.connection.remoteAddress;
    
    try {
        // Kiểm tra admin
        if (username === 'admin' && (password === process.env.ADMIN_PASSWORD || password === 'admin123')) {
            req.session.userId = 'admin';
            req.session.role = 'admin';
            req.session.loginTime = Date.now();
            req.session.loginIP = loginIP;
            
            const token = generateToken('admin', 'admin', null);
            req.session.apiToken = token;
            
            resetBruteForce(username);
            await logAudit(req, 'LOGIN_SUCCESS', 'Admin login', 'admin');
            
            req.flash('success', 'Đăng nhập Admin thành công!');
            return res.redirect('/locks');
        }
        
        // Kiểm tra Lock ID
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.child(username).once('value');
        
        if (snapshot.exists()) {
            const lockData = snapshot.val();
            if (password === username || password === lockData.password) {
                req.session.userId = username;
                req.session.role = 'user';
                req.session.lockId = username;
                req.session.loginTime = Date.now();
                req.session.loginIP = loginIP;
                
                const token = generateToken(username, 'user', username);
                req.session.apiToken = token;
                
                resetBruteForce(username);
                await logAudit(req, 'LOGIN_SUCCESS', `User ${username} login`, username);
                
                req.flash('success', `Chào mừng đến với ${lockData.name}!`);
                return res.redirect(`/dashboard/${username}`);
            }
        }
        
        await logAudit(req, 'LOGIN_FAILED', `Failed login: ${username}`, null);
        req.flash('error', 'Tên đăng nhập hoặc mật khẩu không chính xác');
        res.redirect('/login');
    } catch (error) {
        console.error('[LOGIN ERROR]', error.message);
        await logAudit(req, 'LOGIN_ERROR', error.message, null);
        req.flash('error', 'Đã xảy ra lỗi khi đăng nhập');
        res.redirect('/login');
    }
});

app.get('/logout', requireAuth, async (req, res) => {
    const userId = req.session.userId;
    await logAudit(req, 'LOGOUT', 'User logout', userId);
    
    req.session.destroy((err) => {
        if (err) console.error('[LOGOUT ERROR]', err.message);
        res.redirect('/login');
    });
});

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

    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');
    const pythonProcess = spawn('python', [pythonScriptPath, userId, userName, lockId, '--pending']);

    pythonProcess.on('close', (code) => {
        if (code !== 0) console.error(`[REGISTER] Process exited with code ${code}`);
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
import faceRouter from "./routes/faceRoutes.js";
import apiRouter from "./routes/api.js";
import { initializeTempCodeRoutes } from "./routes/tempCodeRoutes.js";

// Route để render trang upload.ejs
// Route này phải được đặt TRƯỚC app.use('/face', faceRouter) để được ưu tiên xử lý.
app.get('/face/upload-page', requireAuth, (req, res) => {
  res.render('upload'); // Đảm bảo 'upload.ejs' nằm trong thư mục views
});

// Route để hiển thị trang nhập thông tin thu thập khuôn mặt
app.get('/face/collect/:lockId', requireAuth, (req, res) => {
  const { lockId } = req.params;
  
  // Kiểm tra quyền truy cập
  if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
    req.flash('error', 'Bạn không có quyền truy cập khóa này');
    return res.redirect('/login');
  }
  
  res.render('collect_face', { lockId }); // Truyền lockId cho view
});

// Route để xử lý dữ liệu POST từ form thu thập
app.post('/face/collect', requireAuth, (req, res) => {
  const { userId, userName, lockId } = req.body;

  if (!userId || !userName || !lockId) {
    return res.status(400).send("Thiếu thông tin User ID, User Name, hoặc Lock ID.");
  }

  const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');
  const pythonProcess = spawn('python', [pythonScriptPath, userId, userName, lockId]);

  pythonProcess.stdout.on('data', (data) => {
    // Log chỉ khi cần debug
    if (process.env.DEBUG_MODE === 'true') {
      console.log(`[Python] ${data}`);
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python ERROR] ${data}`);
  });

  pythonProcess.on('close', (code) => {
    if (code !== 0) console.error(`[Python] Process exited with code ${code}`);
  });

  res.render('processing', {
    userName: userName,
    userId: userId,
    lockId: lockId,
    message: "Quá trình thu thập khuôn mặt đã bắt đầu. Vui lòng nhìn vào cửa sổ camera."
  });
});

// ================== LOCK MANAGEMENT (CẢI TIẾN) ==================
app.get('/locks', requireAuth, requireAdmin, async (req, res) => {
    try {
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.once('value');
        const locks = snapshot.val() ? Object.values(snapshot.val()) : [];
        res.render('locks', { locks, isAdmin: true });
    } catch (error) {
        console.error("[LOCKS ERROR]", error.message);
        res.status(500).send("Không thể tải danh sách khóa.");
    }
});

app.post('/locks/create', requireAuth, requireAdmin, async (req, res) => {
    const { lockName } = req.body;
    if (!lockName) {
        return res.status(400).send('Tên khóa là bắt buộc.');
    }
    try {
        const lockId = crypto.randomBytes(8).toString('hex');
        const locksRef = db.ref(`locks_registry/${lockId}`);
        await locksRef.set({
            id: lockId,
            name: lockName,
            createdAt: new Date().toISOString(),
            createdBy: req.session.userId
        });
        
        await logAudit(req, 'LOCK_CREATED', `Created: ${lockName} (${lockId})`, req.session.userId);
        console.log(`✅ Lock created: ${lockName} (${lockId})`);
        res.redirect('/locks');
    } catch (error) {
        console.error("[LOCK CREATE ERROR]", error.message);
        await logAudit(req, 'LOCK_CREATE_ERROR', error.message, req.session.userId);
        res.status(500).send('Lỗi server khi tạo khóa.');
    }
});

app.post('/locks/delete', requireAuth, requireAdmin, async (req, res) => {
    const { lockId } = req.body;
    if (!lockId) {
        return res.status(400).send('Thiếu Lock ID.');
    }
    try {
        await db.ref(`locks_registry/${lockId}`).remove();
        await db.ref(`locks/${lockId}`).remove();
        await bucket.deleteFiles({ prefix: `locks/${lockId}/` });

        await logAudit(req, 'LOCK_DELETED', `Deleted: ${lockId}`, req.session.userId);
        console.log(`✅ Lock deleted: ${lockId}`);
        res.redirect('/locks');
    } catch (error) {
        console.error(`[LOCK DELETE ERROR] ${lockId}:`, error.message);
        await logAudit(req, 'LOCK_DELETE_ERROR', error.message, req.session.userId);
        res.status(500).send('Lỗi server khi xóa khóa.');
    }
});

// ================== SERVICE MANAGEMENT (CẢI TIẾN) ==================
const runningServices = {}; // THÊM DÒNG NÀY - Đã thiếu
const runningTelegramBots = {}; // THÊM: Quản lý Telegram Bots

app.post('/service/start/:lockId', requireAuth, requireLockAccess, serviceLimiter, async (req, res) => {
    const { lockId } = req.params;
    const { mode } = req.body;
    
    if (runningServices[lockId]) {
        req.flash('error', `Dịch vụ cho khóa ${lockId} đã chạy.`);
        return res.redirect(`/dashboard/${lockId}`);
    }

    await logAudit(req, 'SERVICE_STARTED', `Started service (mode: ${mode})`, req.session.userId);
    console.log(`✅ Service started: ${lockId} (${mode})`);
    
    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'Recognize.py');
    const pythonProcess = spawn('python', [pythonScriptPath, '--lock_id', lockId, '--mode', mode]);

    runningServices[lockId] = pythonProcess;

    pythonProcess.stdout.on('data', (data) => {
        if (process.env.DEBUG_MODE === 'true') {
            console.log(`[Service-${lockId}] ${data}`);
        }
    });
    
    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Service-${lockId} ERROR] ${data}`);
    });

    pythonProcess.on('close', async (code) => {
        if (code !== 0) console.error(`[Service-${lockId}] Stopped with code ${code}`);
        await logAudit(req, 'SERVICE_STOPPED', `Service stopped`, req.session.userId);
        delete runningServices[lockId];
    });

    req.flash('success', 'Dịch vụ đã được khởi động');
    res.redirect(`/dashboard/${lockId}`);
});

app.post('/service/stop/:lockId', requireAuth, requireLockAccess, async (req, res) => {
    const { lockId } = req.params;
    
    if (runningServices[lockId]) {
        runningServices[lockId].kill('SIGINT');
        await logAudit(req, 'SERVICE_STOPPED', `Service stopped manually`, req.session.userId);
        console.log(`✅ Service stopped: ${lockId}`);
    }
    
    req.flash('success', 'Dịch vụ đã được dừng');
    res.redirect(`/dashboard/${lockId}`);
});

// ================== TELEGRAM BOT MANAGEMENT (THÊM MỚI SAU SERVICE MANAGEMENT) ==================
app.post('/telegram/start/:lockId', requireAuth, requireLockAccess, async (req, res) => {
    const { lockId } = req.params;
    
    if (runningTelegramBots[lockId]) {
        req.flash('warning', `Telegram Bot cho khóa ${lockId} đã chạy.`);
        return res.redirect(`/dashboard/${lockId}`);
    }

    try {
        await logAudit(req, 'TELEGRAM_BOT_STARTED', `Started Telegram Bot for ${lockId}`, req.session.userId);
        console.log(`✅ Telegram Bot started: ${lockId}`);
        
        const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'telegram_control.py');
        const pythonProcess = spawn('python', [pythonScriptPath]);

        runningTelegramBots[lockId] = pythonProcess;

        pythonProcess.stdout.on('data', (data) => {
            console.log(`[TelegramBot-${lockId}] ${data}`);
        });
        
        pythonProcess.stderr.on('data', (data) => {
            console.error(`[TelegramBot-${lockId} ERROR] ${data}`);
        });

        pythonProcess.on('close', async (code) => {
            if (code !== 0) {
                console.error(`[TelegramBot-${lockId}] Stopped with code ${code}`);
            }
            await logAudit(req, 'TELEGRAM_BOT_STOPPED', `Telegram Bot stopped`, req.session.userId);
            delete runningTelegramBots[lockId];
        });

        req.flash('success', 'Telegram Bot đã được khởi động');
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error('[TELEGRAM BOT START ERROR]', error.message);
        req.flash('error', 'Không thể khởi động Telegram Bot');
        res.redirect(`/dashboard/${lockId}`);
    }
});

app.post('/telegram/stop/:lockId', requireAuth, requireLockAccess, async (req, res) => {
    const { lockId } = req.params;
    
    if (runningTelegramBots[lockId]) {
        runningTelegramBots[lockId].kill('SIGINT');
        await logAudit(req, 'TELEGRAM_BOT_STOPPED', `Telegram Bot stopped manually`, req.session.userId);
        console.log(`✅ Telegram Bot stopped: ${lockId}`);
        delete runningTelegramBots[lockId];
        req.flash('success', 'Telegram Bot đã được dừng');
    } else {
        req.flash('warning', 'Telegram Bot không đang chạy');
    }
    
    res.redirect(`/dashboard/${lockId}`);
});

// ================== DASHBOARD ROUTES (CẢI TIẾN) ==================
app.get('/dashboard/:lockId', requireAuth, requireLockAccess, async (req, res) => {
  const { lockId } = req.params;
  
  const embeddingsPath = path.join(__dirname, '..', '..', 'PyCharm', 'dataset', lockId, 'embeddings.pkl');
  const hasEmbeddings = fs.existsSync(embeddingsPath);
  const serviceStatus = runningServices[lockId] ? 'running' : 'stopped';
  const telegramBotStatus = runningTelegramBots[lockId] ? 'running' : 'stopped'; // THÊM DÒNG NÀY
  
  try {
    const [files] = await bucket.getFiles({ prefix: `locks/${lockId}/faces/` });
    const users = {};

    files.forEach(file => {
      const parts = file.name.split('/');
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

    let pendingUsers = [];
    try {
        const pendingUsersRef = db.ref(`locks/${lockId}/pending_users`);
        const pendingSnapshot = await pendingUsersRef.once('value');
        if(pendingSnapshot.exists()){
            pendingSnapshot.forEach(child => {
                pendingUsers.push({ id: child.key, ...child.val() });
            });
        }
    } catch (err) {
        console.error('[DASHBOARD] Pending users error:', err.message);
    }

    let logs = [];
    try {
        const activityLogRef = db.ref(`locks/${lockId}/activity_log`).orderByChild('timestamp').limitToLast(20);
        const snapshot = await activityLogRef.once('value');
        snapshot.forEach(childSnapshot => {
            logs.unshift({ id: childSnapshot.key, ...childSnapshot.val() });
        });
    } catch (err) {
        console.error('[DASHBOARD] Logs error:', err.message);
    }
    
    if (!hasEmbeddings && Object.values(users).length > 0) {
        req.flash('warning', 'Model chưa được train! Vui lòng train model trước khi bắt đầu dịch vụ nhận diện.');
    }
    
    res.render('dashboard', { 
      users: Object.values(users), 
      logs, 
      lockId, 
      pendingUsers, 
      serviceStatus,
      telegramBotStatus, // THÊM DÒNG NÀY
      isAdmin: req.session.role === 'admin',
      hasEmbeddings
    });
  } catch (error) {
    console.error("[DASHBOARD ERROR]", error.message);
    req.flash('error', 'Không thể tải dữ liệu dashboard: ' + error.message);
    
    res.render('dashboard', {
        users: [],
        logs: [],
        lockId,
        pendingUsers: [],
        serviceStatus,
        telegramBotStatus, // THÊM DÒNG NÀY
        isAdmin: req.session.role === 'admin',
        hasEmbeddings
    });
  }
});

app.post('/dashboard/approve-user', requireAuth, async (req, res) => {
    const { userId, lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    try {
        const pendingPrefix = `locks/${lockId}/pending_faces/${userId}/`;
        const [pendingFiles] = await bucket.getFiles({ prefix: pendingPrefix });

        for (const file of pendingFiles) {
            const newName = file.name.replace('pending_faces', 'faces');
            await file.move(newName);
        }

        await db.ref(`locks/${lockId}/pending_users/${userId}`).remove();
        console.log(`✅ User approved: ${userId} (${lockId})`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("[APPROVE ERROR]", error.message);
        res.status(500).send("Lỗi server khi phê duyệt.");
    }
});

app.post('/dashboard/reject-user', requireAuth, async (req, res) => {
    const { userId, lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    try {
        await bucket.deleteFiles({ prefix: `locks/${lockId}/pending_faces/${userId}/` });
        await db.ref(`locks/${lockId}/pending_users/${userId}`).remove();
        console.log(`✅ User rejected: ${userId} (${lockId})`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("[REJECT ERROR]", error.message);
        res.status(500).send("Lỗi server khi từ chối.");
    }
});

app.post('/dashboard/delete-user', requireAuth, async (req, res) => {
    const { userId, lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    try {
        await bucket.deleteFiles({ prefix: `locks/${lockId}/faces/${userId}/` });
        console.log(`✅ User deleted: ${userId} (${lockId})`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`[DELETE USER ERROR] ${userId}:`, error.message);
        res.status(500).send('Lỗi server khi xóa người dùng.');
    }
});

app.post('/dashboard/train-model', requireAuth, (req, res) => {
    const { lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    console.log(`🚀 Training model: ${lockId}`);

    const embeddingsPath = path.join(__dirname, '..', '..', 'PyCharm', 'dataset', lockId, 'embeddings.pkl');
    if (fs.existsSync(embeddingsPath)) {
        try {
            fs.unlinkSync(embeddingsPath);
        } catch (err) {
            console.error('[TRAIN] Delete embeddings error:', err.message);
        }
    }

    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'trainer.py');
    const pythonProcess = spawn('python', [pythonScriptPath, lockId]);

    pythonProcess.stdout.on('data', (data) => {
        if (process.env.DEBUG_MODE === 'true') {
            console.log(`[Trainer] ${data}`);
        }
    });
    
    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Trainer ERROR] ${data}`);
    });

    pythonProcess.on('close', (code) => {
        if (code === 0) {
            console.log(`✅ Training completed: ${lockId}`);
        } else {
            console.error(`[Trainer] Failed with code ${code}`);
        }
        res.redirect(`/dashboard/${lockId}?status=trained`);
    });
});

app.post('/dashboard/clear-logs', requireAuth, async (req, res) => {
    const { lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    try {
        await db.ref(`locks/${lockId}/activity_log`).remove();
        console.log(`✅ Logs cleared: ${lockId}`);
        req.flash('success', 'Đã xóa toàn bộ lịch sử');
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`[CLEAR LOGS ERROR] ${lockId}:`, error.message);
        req.flash('error', 'Lỗi server khi xóa lịch sử');
        res.redirect(`/dashboard/${lockId}`);
    }
});

app.post('/dashboard/clear-logs-by-date', requireAuth, async (req, res) => {
    const { lockId, days } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    try {
        const daysNum = parseInt(days) || 7;
        const cutoffTime = Date.now() - (daysNum * 24 * 60 * 60 * 1000);
        
        const logsRef = db.ref(`locks/${lockId}/activity_log`);
        const snapshot = await logsRef.orderByChild('timestamp').endAt(cutoffTime).once('value');
        
        if (snapshot.exists()) {
            const oldLogs = snapshot.val();
            const deletePromises = [];
            
            for (const logKey in oldLogs) {
                deletePromises.push(logsRef.child(logKey).remove());
            }
            
            await Promise.all(deletePromises);
            
            const deletedCount = Object.keys(oldLogs).length;
            console.log(`✅ Cleared ${deletedCount} old logs (${daysNum} days) from ${lockId}`);
            req.flash('success', `Đã xóa ${deletedCount} log cũ hơn ${daysNum} ngày`);
        } else {
            req.flash('info', `Không có log cũ hơn ${daysNum} ngày`);
        }
        
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`[CLEAR LOGS BY DATE ERROR] ${lockId}:`, error.message);
        req.flash('error', 'Lỗi server khi xóa lịch sử: ' + error.message);
        res.redirect(`/dashboard/${lockId}`);
    }
});

// ================== LIVESTREAM ROUTE (THÊM VÀO) ==================
app.get('/livestream/:lockId', requireAuth, requireLockAccess, (req, res) => {
    const { lockId } = req.params;
    res.render('livestream', { 
        lockId,
        isAdmin: req.session.role === 'admin'
    });
});

// ======================================================

// ================== API ROUTES WITH JWT ==================
app.post('/api/livestream/:lockId', apiLimiter, async (req, res) => {
    const { lockId } = req.params;
    const token = req.headers.authorization?.split(' ')[1];
    
    if (!token) {
        return res.status(401).json({ error: 'Missing token' });
    }
    
    const decoded = verifyToken(token);
    if (!decoded || (decoded.role !== 'admin' && decoded.lockId !== lockId)) {
        await logAudit(req, 'API_UNAUTHORIZED', `Unauthorized API access: ${lockId}`, decoded?.userId);
        return res.status(403).json({ error: 'Unauthorized' });
    }
    
    const frameBuffer = req.body;
    const base64Frame = frameBuffer.toString('base64');
    io.to(lockId).emit('new_frame', { frame: base64Frame });
    res.sendStatus(200);
});

// ================== ROOT ROUTE (THÊM VÀO) ==================
app.get('/', (req, res) => {
    // Redirect đến login hoặc dashboard tùy theo session
    if (req.session && req.session.userId) {
        if (req.session.role === 'admin') {
            return res.redirect('/locks');
        } else {
            return res.redirect(`/dashboard/${req.session.lockId}`);
        }
    }
    res.redirect('/login');
});

app.use("/face", faceRouter);
app.use("/api", apiRouter);

// Khởi tạo temp code routes với database instance
console.log('[APP] ========== INITIALIZING TEMP CODE ROUTES ==========');
console.log('[APP] Database instance:', db ? '✅ EXISTS' : '❌ NULL');
console.log('[APP] Database type:', typeof db);

try {
    const tempCodeRouter = initializeTempCodeRoutes(db);
    app.use('/api/temp-code', tempCodeRouter);
    console.log('✅ Temp code routes initialized');
} catch (error) {
    console.error('❌ CRITICAL: Temp code routes initialization failed:', error.message);
    process.exit(1);
}

// ================== HTTPS SERVER (PRODUCTION) ==================
if (process.env.NODE_ENV === 'production') {
    const httpsOptions = {
        key: fs.readFileSync(path.join(__dirname, '.ssl', 'private.key')),
        cert: fs.readFileSync(path.join(__dirname, '.ssl', 'certificate.crt'))
    };
    
    const httpsServer = https.createServer(httpsOptions, app);
    httpsServer.listen(443, () => {
        console.log(`✅ HTTPS Server running at https://localhost:443`);
    });
    
    const httpApp = express();
    httpApp.use((req, res) => {
        res.redirect(`https://${req.headers.host}${req.url}`);
    });
    httpApp.listen(80);
} else {
    server.listen(PORT, () => {
        console.log(`✅ Server running at http://localhost:${PORT}`);
    });
}

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

// ================== SCHEDULED CLEANUP (REFACTORED) ==================
// Khởi động cleanup scheduler
cleanupScheduler.start();

// THÊM: Test endpoint để verify Firebase connection
app.get('/api/test-firebase', async (req, res) => {
    try {
        console.log('[TEST] Testing Firebase connection...');
        
        // Test 1: Đọc dữ liệu
        const testRef = db.ref('test_connection');
        await testRef.set({
            timestamp: Date.now(),
            message: 'Connection test'
        });
        console.log('[TEST] ✅ Write successful');
        
        // Test 2: Đọc lại
        const snapshot = await testRef.once('value');
        const data = snapshot.val();
        console.log('[TEST] ✅ Read successful:', data);
        
        // Test 3: Xóa
        await testRef.remove();
        console.log('[TEST] ✅ Delete successful');
        
        res.json({
            success: true,
            message: 'Firebase connection OK',
            data: data
        });
    } catch (error) {
        console.error('[TEST] ❌ Firebase error:', error);
        res.status(500).json({
            success: false,
            error: error.message,
            stack: error.stack
        });
    }
});

// ================== ESP32 AUTO-REGISTRATION (THÊM VÀO) ==================
app.post('/api/esp32/register', async (req, res) => {
    try {
        const { lockId, macAddress, ipAddress } = req.body;
        
        if (!lockId) {
            return res.status(400).json({ 
                success: false, 
                error: 'Missing lockId' 
            });
        }
        
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.child(lockId).once('value');
        
        if (snapshot.exists()) {
            return res.json({
                success: true,
                message: 'Lock already registered',
                lockId: lockId,
                name: snapshot.val().name,
                alreadyExists: true
            });
        }
        
        const lockName = `SmartLock ${lockId.substring(0, 8)}`;
        await locksRef.child(lockId).set({
            id: lockId,
            name: lockName,
            createdAt: new Date().toISOString(),
            createdBy: 'ESP32_AUTO',
            macAddress: macAddress || 'unknown',
            ipAddress: ipAddress || 'unknown',
            lastSeen: Date.now()
        });
        
        console.log(`✅ ESP32 auto-registered: ${lockName} (${lockId})`);
        
        res.json({
            success: true,
            message: 'Lock registered successfully',
            lockId: lockId,
            name: lockName,
            alreadyExists: false
        });
        
    } catch (error) {
        console.error('[ESP32 REGISTER ERROR]', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// ================== ESP32 HEARTBEAT (THÊM VÀO) ==================
app.post('/api/esp32/heartbeat', async (req, res) => {
    try {
        const { lockId } = req.body;
        
        if (!lockId) {
            return res.status(400).json({ success: false });
        }
        
        // Cập nhật lastSeen
        await db.ref(`locks_registry/${lockId}`).update({
            lastSeen: Date.now(),
            status: 'online'
        });
        
        res.json({ success: true });
        
    } catch (error) {
        console.error('[ESP32_HEARTBEAT] Error:', error);
        res.status(500).json({ success: false });
    }
});

// ================== CẬP NHẬT IP CHO LOCK (THÊM VÀO) ==================
app.post('/api/lock/update-ip', requireAuth, async (req, res) => {
    try {
        const { lockId, newIp } = req.body;
        
        // Kiểm tra quyền
        if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
            return res.status(403).json({ success: false, error: 'Không có quyền' });
        }
        
        if (!lockId || !newIp) {
            return res.status(400).json({ success: false, error: 'Thiếu lockId hoặc newIp' });
        }
        
        // Validate IP format
        const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
        if (!ipRegex.test(newIp)) {
            return res.status(400).json({ success: false, error: 'IP không hợp lệ' });
        }
        
        // Cập nhật trong Firebase
        await db.ref(`locks_registry/${lockId}`).update({
            ipAddress: newIp,
            lastIpUpdate: Date.now(),
            updatedBy: req.session.userId
        });
        
        await logAudit(req, 'IP_UPDATED', `Updated IP to ${newIp} for ${lockId}`, req.session.userId);
        
        console.log(`✅ IP updated for ${lockId}: ${newIp}`);
        
        res.json({
            success: true,
            message: 'Cập nhật IP thành công',
            lockId: lockId,
            newIp: newIp
        });
        
    } catch (error) {
        console.error('[UPDATE_IP ERROR]', error);
        res.status(500).json({ success: false, error: error.message });
    }
});

// ================== TELEGRAM API ENDPOINTS (THAY THẾ PHẦN CŨ) ==================
app.post('/api/telegram/command', requireAuth, async (req, res) => {
    try {
        const { lockId, command, params } = req.body;
        
        // Kiểm tra quyền truy cập
        if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
            return res.status(403).json({ success: false, error: 'Không có quyền' });
        }
        
        // Lấy thông tin ESP32 từ database
        const lockRef = db.ref(`locks_registry/${lockId}`);
        const lockSnapshot = await lockRef.once('value');
        
        if (!lockSnapshot.exists()) {
            return res.status(404).json({ success: false, error: 'Không tìm thấy khóa' });
        }
        
        const lockData = lockSnapshot.val();
        const ESP32_IP = lockData.ipAddress || process.env.ESP32_IP || '10.132.95.33';
        
        let result = {};
        
        switch(command) {
            case 'open':
                // Gửi lệnh mở cửa trực tiếp đến ESP32
                try {
                    const url = `http://${ESP32_IP}/SUCCESS?key=28280303`;
                    const response = await fetch(url, { timeout: 5000 });
                    
                    if (response.ok) {
                        // Log activity
                        await db.ref(`locks/${lockId}/activity_log`).push({
                            name: 'Dashboard Control',
                            type: 'DASHBOARD_OPEN',
                            timestamp: Date.now(),
                            imageUrl: null,
                            userId: req.session.userId
                        });
                        
                        await logAudit(req, 'DOOR_OPENED', `Opened via dashboard: ${lockId}`, req.session.userId);
                        
                        result = {
                            success: true,
                            message: 'Cửa đã được mở thành công!'
                        };
                    } else {
                        result = {
                            success: false,
                            error: 'ESP32 không phản hồi'
                        };
                    }
                } catch (error) {
                    console.error('[DOOR CONTROL ERROR]', error);
                    result = {
                        success: false,
                        error: 'Không thể kết nối đến ESP32: ' + error.message
                    };
                }
                break;
                
            case 'close':
                // Gửi lệnh đóng cửa trực tiếp đến ESP32
                try {
                    const url = `http://${ESP32_IP}/CLOSE`;
                    const response = await fetch(url, { timeout: 5000 });
                    
                    if (response.ok) {
                        // Log activity
                        await db.ref(`locks/${lockId}/activity_log`).push({
                            name: 'Dashboard Control',
                            type: 'DASHBOARD_CLOSE',
                            timestamp: Date.now(),
                            imageUrl: null,
                            userId: req.session.userId
                        });
                        
                        await logAudit(req, 'DOOR_CLOSED', `Closed via dashboard: ${lockId}`, req.session.userId);
                        
                        result = {
                            success: true,
                            message: 'Cửa đã được đóng thành công!'
                        };
                    } else {
                        result = {
                            success: false,
                            error: 'ESP32 không phản hồi'
                        };
                    }
                } catch (error) {
                    console.error('[DOOR CONTROL ERROR]', error);
                    result = {
                        success: false,
                        error: 'Không thể kết nối đến ESP32: ' + error.message
                    };
                }
                break;
                
            case 'createcode':
                // Tạo mã tạm thời trực tiếp trong NodeJS
                try {
                    const hours = params.hours || 1;
                    const code = Math.floor(100000 + Math.random() * 900000).toString(); // 6 số ngẫu nhiên
                    const now = new Date();
                    const expiresAt = new Date(now.getTime() + hours * 60 * 60 * 1000);
                    
                    // Lưu vào Firebase
                    await db.ref(`locks/${lockId}/temp_codes/${code}`).set({
                        code: code,
                        lockId: lockId,
                        createdAt: now.toISOString(),
                        expiresAt: expiresAt.toISOString(),
                        createdBy: req.session.userId,
                        createdFrom: 'dashboard',
                        maxUses: 1,
                        usedCount: 0,
                        status: 'active'
                    });
                    
                    await logAudit(req, 'TEMP_CODE_CREATED', `Created code: ${code} for ${lockId}`, req.session.userId);
                    
                    result = {
                        success: true,
                        message: 'Mã PIN đã được tạo thành công',
                        code: code,
                        expireAt: expiresAt.toLocaleString('vi-VN', { 
                            timeZone: 'Asia/Ho_Chi_Minh',
                            year: 'numeric',
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit'
                        })
                    };
                    
                    console.log(`✅ Created temp code: ${code} for lock ${lockId}`);
                } catch (error) {
                    console.error('[CREATE CODE ERROR]', error);
                    result = {
                        success: false,
                        error: 'Không thể tạo mã: ' + error.message
                    };
                }
                break;
                
            default:
                return res.status(400).json({ success: false, error: 'Lệnh không hợp lệ' });
        }
        
        res.json(result);
        
    } catch (error) {
        console.error('[TELEGRAM COMMAND ERROR]', error.message);
        res.status(500).json({ 
            success: false, 
            error: 'Lỗi server: ' + error.message 
        });
    }
});

app.get('/api/telegram/list-codes/:lockId', requireAuth, requireLockAccess, async (req, res) => {
    try {
        const { lockId } = req.params;
        
        // Lấy danh sách mã từ Firebase
        const codesRef = db.ref(`locks/${lockId}/temp_codes`);
        const snapshot = await codesRef.once('value');
        
        if (!snapshot.exists()) {
            return res.json({
                success: true,
                codes: []
            });
        }
        
        const codesData = snapshot.val();
        const now = new Date();
        const activeCodes = [];
        
        for (const [code, data] of Object.entries(codesData)) {
            const expiresAt = new Date(data.expiresAt);
            
            // Chỉ lấy mã còn hiệu lực
            if (expiresAt > now && data.usedCount < data.maxUses && data.status === 'active') {
                const timeRemaining = Math.round((expiresAt - now) / 1000 / 60); // phút
                
                activeCodes.push({
                    code: code,
                    expireAt: expiresAt.toLocaleString('vi-VN', { 
                        timeZone: 'Asia/Ho_Chi_Minh',
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit'
                    }),
                    timeRemaining: timeRemaining > 60 
                        ? `${Math.floor(timeRemaining / 60)} giờ ${timeRemaining % 60} phút`
                        : `${timeRemaining} phút`,
                    usedCount: data.usedCount || 0,
                    maxUses: data.maxUses || 1
                });
            }
        }
        
        res.json({
            success: true,
            codes: activeCodes
        });
        
    } catch (error) {
        console.error('[LIST CODES ERROR]', error.message);
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// THÊM: API xác thực mã tạm thời (cho ESP32 gọi)
app.post('/api/verify-temp-code', apiLimiter, async (req, res) => {
    try {
        const { code, lockId } = req.body;
        
        if (!code || !lockId) {
            return res.status(400).json({ 
                success: false, 
                error: 'Missing code or lockId' 
            });
        }
        
        // Lấy thông tin mã từ Firebase
        const codeRef = db.ref(`locks/${lockId}/temp_codes/${code}`);
        const snapshot = await codeRef.once('value');
        
        if (!snapshot.exists()) {
            console.log(`❌ Code not found: ${code}`);
            return res.json({ 
                success: false, 
                valid: false,
                message: 'Mã không tồn tại' 
            });
        }
        
        const codeData = snapshot.val();
        const now = new Date();
        const expiresAt = new Date(codeData.expiresAt);
        
        // Kiểm tra hết hạn
        if (expiresAt < now) {
            console.log(`❌ Code expired: ${code}`);
            await codeRef.update({ status: 'expired' });
            return res.json({ 
                success: false, 
                valid: false,
                message: 'Mã đã hết hạn' 
            });
        }
        
        // Kiểm tra số lần sử dụng
        if (codeData.usedCount >= codeData.maxUses) {
            console.log(`❌ Code used up: ${code}`);
            await codeRef.update({ status: 'used_up' });
            return res.json({ 
                success: false, 
                valid: false,
                message: 'Mã đã hết lượt sử dụng' 
            });
        }
        
        // Mã hợp lệ - tăng số lần sử dụng
        await codeRef.update({
            usedCount: (codeData.usedCount || 0) + 1,
            lastUsedAt: now.toISOString(),
            status: (codeData.usedCount + 1) >= codeData.maxUses ? 'used_up' : 'active'
        });
        
        // Log activity
        await db.ref(`locks/${lockId}/activity_log`).push({
            name: `Temp Code: ${code}`,
            type: 'TEMP_CODE_SUCCESS',
            timestamp: Date.now(),
            imageUrl: null,
            code: code
        });
        
        console.log(`✅ Code verified: ${code} (${codeData.usedCount + 1}/${codeData.maxUses})`);
        
        res.json({ 
            success: true, 
            valid: true,
            message: 'Mã hợp lệ',
            remaining: codeData.maxUses - (codeData.usedCount || 0) - 1
        });
        
    } catch (error) {
        console.error('[VERIFY CODE ERROR]', error);
        res.status(500).json({ 
            success: false, 
            error: error.message 
        });
    }
});

// ================== LOCK INFO API (THÊM SAU ESP32 ENDPOINTS) ==================
app.get('/api/lock-info/:lockId', async (req, res) => {
    try {
        const { lockId } = req.params;
        
        const lockRef = db.ref(`locks_registry/${lockId}`);
        const snapshot = await lockRef.once('value');
        
        if (!snapshot.exists()) {
            return res.status(404).json({
                success: false,
                error: 'Lock not found'
            });
        }
        
        const lockData = snapshot.val();
        
        res.json({
            success: true,
            id: lockData.id,
            name: lockData.name,
            ipAddress: lockData.ipAddress || process.env.DEFAULT_ESP32_IP || '10.132.95.33',
            createdAt: lockData.createdAt,
            lastSeen: lockData.lastSeen || null
        });
        
    } catch (error) {
        console.error('[LOCK_INFO ERROR]', error.message);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// THÊM: Test endpoint để trigger cleanup thủ công
app.post('/api/admin/cleanup-now', requireAuth, requireAdmin, async (req, res) => {
    try {
        console.log('[MANUAL CLEANUP] Starting manual cleanup...');
        await cleanupService.performAllCleanup();
        res.json({
            success: true,
            message: 'Cleanup completed successfully'
        });
    } catch (error) {
        console.error('[MANUAL CLEANUP ERROR]', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});
