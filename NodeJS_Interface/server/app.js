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

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// KHỞI TẠO FIREBASE
const serviceAccount = path.join(__dirname, '..', '..', 'PyCharm', '.env', 'firebase_credentials.json');
admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
  storageBucket: 'smartlockfacerecognition.firebasestorage.app',
  databaseURL: process.env.FIREBASE_DATABASE_URL
});
const bucket = admin.storage().bucket();
const db = admin.database();
console.log('✅ Firebase đã được khởi tạo');

// IMPORT MIDDLEWARE
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
    verifyToken,
    initializeSecurity
} from './middleware/security.js';

initializeSecurity(db);

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const PORT = process.env.PORT || 3000;

app.set("view engine", "ejs");
app.set("views", path.join(__dirname, "views"));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());
app.use('/api/livestream', express.raw({ type: 'image/jpeg', limit: '10mb' }));
app.use(express.static(path.join(__dirname, "public")));
app.use(helmetConfig);
app.use(sanitizeInput);

app.use(session({
    secret: process.env.SESSION_SECRET || 'smartlock-secret-key-2025',
    resave: false,
    saveUninitialized: false,
    cookie: {
        maxAge: 24 * 60 * 60 * 1000,
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict'
    },
    rolling: true
}));

app.use(flash());

app.use((req, res, next) => {
    res.locals.user = req.session.userId || null;
    res.locals.userRole = req.session.role || null;
    res.locals.userLockId = req.session.lockId || null;
    res.locals.success = req.flash('success');
    res.locals.error = req.flash('error');
    res.locals.warning = req.flash('warning');
    next();
});

// ROUTES
app.get('/login', (req, res) => {
    if (req.session.userId) {
        return res.redirect(req.session.role === 'admin' ? '/locks' : `/dashboard/${req.session.lockId}`);
    }
    res.render('login');
});

app.post('/login', loginLimiter, checkBruteForce, async (req, res) => {
    const { username, password } = req.body;
    const loginIP = req.ip || req.connection.remoteAddress;
    
    try {
        if (username === 'admin' && (password === process.env.ADMIN_PASSWORD || password === 'admin123')) {
            req.session.userId = 'admin';
            req.session.role = 'admin';
            req.session.loginTime = Date.now();
            req.session.loginIP = loginIP;
            req.session.apiToken = generateToken('admin', 'admin', null);
            
            resetBruteForce(username);
            await logAudit(req, 'LOGIN_SUCCESS', 'Admin đăng nhập thành công', 'admin');
            req.flash('success', 'Đăng nhập Admin thành công!');
            return res.redirect('/locks');
        }
        
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
                req.session.apiToken = generateToken(username, 'user', username);
                
                resetBruteForce(username);
                await logAudit(req, 'LOGIN_SUCCESS', `User ${username} đăng nhập thành công`, username);
                req.flash('success', `Chào mừng đến với ${lockData.name}!`);
                return res.redirect(`/dashboard/${username}`);
            }
        }
        
        await logAudit(req, 'LOGIN_FAILED', `Đăng nhập thất bại cho username: ${username}`, null);
        req.flash('error', 'Tên đăng nhập hoặc mật khẩu không chính xác');
        res.redirect('/login');
    } catch (error) {
        console.error('Login error:', error);
        await logAudit(req, 'LOGIN_ERROR', `Lỗi đăng nhập: ${error.message}`, null);
        req.flash('error', 'Đã xảy ra lỗi khi đăng nhập');
        res.redirect('/login');
    }
});

app.get('/logout', requireAuth, async (req, res) => {
    const userId = req.session.userId;
    await logAudit(req, 'LOGOUT', 'User đăng xuất', userId);
    req.session.destroy((err) => {
        if (err) console.error('Logout error:', err);
        res.redirect('/login');
    });
});

app.get('/register/:lockId', (req, res) => {
    res.render('register_face', { lockId: req.params.lockId });
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
        userName,
        userId,
        lockId,
        message: "Yêu cầu đăng ký của bạn đã được gửi. Vui lòng chờ quản trị viên phê duyệt."
    });
});

import faceRouter from "./routes/faceRoutes.js";
import apiRouter from "./routes/api.js";

app.get('/face/upload-page', requireAuth, (req, res) => {
  res.render('upload');
});

app.get('/face/collect/:lockId', requireAuth, (req, res) => {
  const { lockId } = req.params;
  
  if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
    req.flash('error', 'Bạn không có quyền truy cập khóa này');
    return res.redirect('/login');
  }
  
  res.render('collect_face', { lockId });
});

app.post('/face/collect', requireAuth, (req, res) => {
  const { userId, userName, lockId } = req.body;
  
  if (!userId || !userName || !lockId) {
    return res.status(400).send("Thiếu thông tin User ID, User Name, hoặc Lock ID.");
  }
  
  console.log(`Bắt đầu thu thập cho Lock ID: ${lockId}, User ID: ${userId}, Tên: ${userName}`);
  
  const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'facedetect.py');
  const pythonProcess = spawn('python', [pythonScriptPath, userId, userName, lockId]);
  
  pythonProcess.stdout.on('data', (data) => console.log(`[Python] stdout: ${data}`));
  pythonProcess.stderr.on('data', (data) => console.error(`[Python] stderr: ${data}`));
  pythonProcess.on('close', (code) => console.log(`[Python] child process exited with code ${code}`));
  
  res.render('processing', {
    userName,
    userId,
    lockId,
    message: "Quá trình thu thập khuôn mặt đã bắt đầu. Vui lòng nhìn vào cửa sổ camera."
  });
});

app.get('/locks', requireAuth, requireAdmin, async (req, res) => {
    try {
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.once('value');
        const locks = snapshot.val() ? Object.values(snapshot.val()) : [];
        res.render('locks', { locks, isAdmin: true });
    } catch (error) {
        console.error("Lỗi khi tải danh sách khóa:", error);
        res.status(500).send("Không thể tải danh sách khóa.");
    }
});

app.post('/locks/create', requireAuth, requireAdmin, async (req, res) => {
    const { lockName } = req.body;
    if (!lockName) return res.status(400).send('Tên khóa là bắt buộc.');
    
    try {
        const lockId = crypto.randomBytes(8).toString('hex');
        await db.ref(`locks_registry/${lockId}`).set({
            id: lockId,
            name: lockName,
            createdAt: new Date().toISOString(),
            createdBy: req.session.userId
        });
        
        await logAudit(req, 'LOCK_CREATED', `Tạo khóa mới: ${lockName} (ID: ${lockId})`, req.session.userId);
        console.log(`Đã tạo khóa mới: ${lockName} với ID: ${lockId}`);
        res.redirect('/locks');
    } catch (error) {
        console.error("Lỗi khi tạo khóa mới:", error);
        await logAudit(req, 'LOCK_CREATE_ERROR', `Lỗi tạo khóa: ${error.message}`, req.session.userId);
        res.status(500).send('Lỗi server khi tạo khóa.');
    }
});

app.post('/locks/delete', requireAuth, requireAdmin, async (req, res) => {
    const { lockId } = req.body;
    if (!lockId) return res.status(400).send('Thiếu Lock ID.');
    
    try {
        await db.ref(`locks_registry/${lockId}`).remove();
        await db.ref(`locks/${lockId}`).remove();
        await bucket.deleteFiles({ prefix: `locks/${lockId}/` });
        
        await logAudit(req, 'LOCK_DELETED', `Xóa khóa: ${lockId}`, req.session.userId);
        console.log(`Đã xóa hoàn toàn khóa: ${lockId}`);
        res.redirect('/locks');
    } catch (error) {
        console.error(`Lỗi khi xóa khóa ${lockId}:`, error);
        await logAudit(req, 'LOCK_DELETE_ERROR', `Lỗi xóa khóa: ${error.message}`, req.session.userId);
        res.status(500).send('Lỗi server khi xóa khóa.');
    }
});

const runningServices = {};

app.post('/service/start/:lockId', requireAuth, requireLockAccess, serviceLimiter, async (req, res) => {
    const { lockId } = req.params;
    const { mode } = req.body;
    
    if (runningServices[lockId]) {
        req.flash('error', `Dịch vụ cho khóa ${lockId} đã chạy.`);
        return res.redirect(`/dashboard/${lockId}`);
    }
    
    await logAudit(req, 'SERVICE_STARTED', `Bắt đầu dịch vụ cho khóa ${lockId} với chế độ ${mode}`, req.session.userId);
    console.log(`Bắt đầu dịch vụ nhận diện cho khóa: ${lockId} với chế độ ${mode}`);
    
    const pythonScriptPath = path.join(__dirname, '..', '..', 'PyCharm', 'src', 'Recognize.py');
    const pythonProcess = spawn('python', [pythonScriptPath, '--lock_id', lockId, '--mode', mode]);
    
    runningServices[lockId] = pythonProcess;
    
    pythonProcess.stdout.on('data', (data) => console.log(`[Recognize-${lockId}] stdout: ${data}`));
    pythonProcess.stderr.on('data', (data) => console.error(`[Recognize-${lockId}] stderr: ${data}`));
    pythonProcess.on('close', async (code) => {
        console.log(`Dịch vụ cho khóa ${lockId} đã dừng với mã ${code}.`);
        await logAudit(req, 'SERVICE_STOPPED', `Dịch vụ cho khóa ${lockId} đã dừng`, req.session.userId);
        delete runningServices[lockId];
    });
    
    req.flash('success', 'Dịch vụ đã được khởi động');
    res.redirect(`/dashboard/${lockId}`);
});

app.post('/service/stop/:lockId', requireAuth, requireLockAccess, async (req, res) => {
    const { lockId } = req.params;
    
    if (runningServices[lockId]) {
        runningServices[lockId].kill('SIGINT');
        await logAudit(req, 'SERVICE_STOPPED', `Dừng dịch vụ cho khóa ${lockId}`, req.session.userId);
        console.log(`Đã gửi yêu cầu dừng cho dịch vụ của khóa ${lockId}.`);
    }
    
    req.flash('success', 'Dịch vụ đã được dừng');
    res.redirect(`/dashboard/${lockId}`);
});

app.get('/dashboard/:lockId', requireAuth, requireLockAccess, async (req, res) => {
  const { lockId } = req.params;
  const embeddingsPath = path.join(__dirname, '..', '..', 'PyCharm', 'dataset', lockId, 'embeddings.pkl');
  const hasEmbeddings = fs.existsSync(embeddingsPath);
  const serviceStatus = runningServices[lockId] ? 'running' : 'stopped';
  
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
        console.error('Lỗi khi lấy pending users:', err);
    }
    
    let logs = [];
    try {
        const activityLogRef = db.ref(`locks/${lockId}/activity_log`).orderByChild('timestamp').limitToLast(20);
        const snapshot = await activityLogRef.once('value');
        snapshot.forEach(childSnapshot => {
            logs.unshift({ id: childSnapshot.key, ...childSnapshot.val() });
        });
    } catch (err) {
        console.error('Lỗi khi lấy logs:', err);
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
      isAdmin: req.session.role === 'admin',
      hasEmbeddings
    });
  } catch (error) {
    console.error("Lỗi khi tải dữ liệu dashboard:", error);
    req.flash('error', 'Không thể tải dữ liệu dashboard: ' + error.message);
    res.render('dashboard', {
        users: [],
        logs: [],
        lockId,
        pendingUsers: [],
        serviceStatus,
        isAdmin: req.session.role === 'admin',
        hasEmbeddings: false
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
        console.log(`Đã phê duyệt người dùng ${userId} cho khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("Lỗi khi phê duyệt:", error);
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
        console.log(`Đã từ chối người dùng ${userId} cho khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error("Lỗi khi từ chối:", error);
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
        console.log(`Đã xóa tất cả ảnh của người dùng ${userId} từ khóa ${lockId}`);
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`Lỗi khi xóa người dùng ${userId}:`, error);
        res.status(500).send('Lỗi server khi xóa người dùng.');
    }
});

app.post('/dashboard/train-model', requireAuth, (req, res) => {
    const { lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
    }
    
    console.log(`Bắt đầu train model cho khóa: ${lockId}`);
    
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

app.post('/dashboard/clear-logs', requireAuth, async (req, res) => {
    const { lockId } = req.body;
    
    if (req.session.role !== 'admin' && req.session.lockId !== lockId) {
        return res.status(403).send('Không có quyền');
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
            for (const logKey in oldLogs) {
                await logsRef.child(logKey).remove();
            }
            const deletedCount = Object.keys(oldLogs).length;
            console.log(`Đã xóa ${deletedCount} log cũ hơn ${daysNum} ngày từ khóa ${lockId}`);
            req.flash('success', `Đã xóa ${deletedCount} log cũ hơn ${daysNum} ngày`);
        } else {
            req.flash('info', `Không có log cũ hơn ${daysNum} ngày`);
        }
        
        res.redirect(`/dashboard/${lockId}`);
    } catch (error) {
        console.error(`Lỗi khi xóa lịch sử của khóa ${lockId}:`, error);
        res.status(500).send('Lỗi server khi xóa lịch sử.');
    }
});

app.get('/livestream/:lockId', requireAuth, requireLockAccess, (req, res) => {
    res.render('livestream', { 
        lockId: req.params.lockId,
        isAdmin: req.session.role === 'admin'
    });
});

app.post('/api/livestream/:lockId', apiLimiter, async (req, res) => {
    const { lockId } = req.params;
    const token = req.headers.authorization?.split(' ')[1];
    
    if (!token) return res.status(401).json({ error: 'Missing token' });
    
    const decoded = verifyToken(token);
    if (!decoded || (decoded.role !== 'admin' && decoded.lockId !== lockId)) {
        await logAudit(req, 'API_UNAUTHORIZED', `Truy cập API không được phép cho lock ${lockId}`, decoded?.userId);
        return res.status(403).json({ error: 'Unauthorized' });
    }
    
    const frameBuffer = req.body;
    const base64Frame = frameBuffer.toString('base64');
    io.to(lockId).emit('new_frame', { frame: base64Frame });
    res.sendStatus(200);
});

app.get('/', (req, res) => {
    if (req.session && req.session.userId) {
        return res.redirect(req.session.role === 'admin' ? '/locks' : `/dashboard/${req.session.lockId}`);
    }
    res.redirect('/login');
});

app.use("/face", faceRouter);
app.use("/api", apiRouter);

// CLEANUP SCHEDULER
import { cleanupOldLogs, limitLogsPerLock } from './utils/firebase-cleanup.js';

const CLEANUP_INTERVAL = 24 * 60 * 60 * 1000;
const CLEANUP_HOUR = 2;

function scheduleCleanup() {
    const now = new Date();
    const nextCleanup = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate() + 1,
        CLEANUP_HOUR,
        0,
        0
    );
    
    setTimeout(() => {
        performCleanup();
        setInterval(performCleanup, CLEANUP_INTERVAL);
    }, nextCleanup.getTime() - now.getTime());
    
    console.log(`[CLEANUP] Đã lên lịch cleanup lúc ${nextCleanup.toLocaleString('vi-VN')}`);
}

async function performCleanup() {
    console.log('[CLEANUP] Bắt đầu dọn dẹp log cũ...');
    try {
        await cleanupOldLogs(30);
        
        const locksRef = db.ref('locks_registry');
        const snapshot = await locksRef.once('value');
        if (snapshot.exists()) {
            const locks = Object.keys(snapshot.val());
            for (const lockId of locks) {
                await limitLogsPerLock(lockId, 200);
            }
        }
        
        console.log('[CLEANUP] Hoàn tất dọn dẹp log');
    } catch (error) {
        console.error('[CLEANUP] Lỗi khi dọn dẹp:', error);
    }
}

scheduleCleanup();

// SERVER STARTUP
if (process.env.NODE_ENV === 'production') {
    const httpsOptions = {
        key: fs.readFileSync(path.join(__dirname, '.ssl', 'private.key')),
        cert: fs.readFileSync(path.join(__dirname, '.ssl', 'certificate.crt'))
    };
    
    const httpsServer = https.createServer(httpsOptions, app);
    httpsServer.listen(443, () => {
        console.log(`✅ HTTPS Server đang chạy tại https://localhost:443`);
    });
    
    const httpApp = express();
    httpApp.use((req, res) => {
        res.redirect(`https://${req.headers.host}${req.url}`);
    });
    httpApp.listen(80);
} else {
    server.listen(PORT, () => {
        console.log(`✅ Server đang chạy tại http://localhost:${PORT}`);
    });
}

// SOCKET.IO
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
