import rateLimit from 'express-rate-limit';
import helmet from 'helmet';
import hpp from 'hpp';
import jwt from 'jsonwebtoken';

// Biến toàn cục để lưu reference database
let db = null;

// THÊM HÀM KHỞI TẠO
export function initializeSecurity(database) {
    db = database;
}

// ================== RATE LIMITING ==================
export const loginLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 phút
    max: 5, // 5 lần thử
    message: 'Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau 15 phút.',
    standardHeaders: true,
    legacyHeaders: false,
    handler: (req, res) => {
        logAudit(req, 'LOGIN_BLOCKED', 'Bị chặn do quá nhiều lần thử đăng nhập', null);
        req.flash('error', 'Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau 15 phút.');
        res.redirect('/login');
    }
});

export const apiLimiter = rateLimit({
    windowMs: 1 * 60 * 1000, // 1 phút
    max: 60, // 60 requests
    message: 'Quá nhiều request. Vui lòng thử lại sau.',
    standardHeaders: true,
    legacyHeaders: false,
});

export const serviceLimiter = rateLimit({
    windowMs: 5 * 60 * 1000, // 5 phút
    max: 10, // 10 lần bật/tắt
    message: 'Quá nhiều lần bật/tắt dịch vụ. Vui lòng thử lại sau.',
    standardHeaders: true,
    legacyHeaders: false,
});

// ================== HELMET CONFIG ==================
export const helmetConfig = helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            styleSrc: ["'self'", "'unsafe-inline'", "https://cdnjs.cloudflare.com"],
            scriptSrc: ["'self'", "'unsafe-inline'"],
            imgSrc: ["'self'", "data:", "https:", "blob:"],
            connectSrc: ["'self'", "wss:", "ws:"],
            fontSrc: ["'self'", "https://cdnjs.cloudflare.com"],
        },
    },
    hsts: {
        maxAge: 31536000,
        includeSubDomains: true,
        preload: true
    }
});

// ================== JWT UTILITIES ==================
const JWT_SECRET = process.env.JWT_SECRET || 'smartlock-jwt-secret-change-this-2025';
const JWT_EXPIRE = '24h';

export function generateToken(userId, role, lockId) {
    return jwt.sign(
        { userId, role, lockId, iat: Date.now() },
        JWT_SECRET,
        { expiresIn: JWT_EXPIRE }
    );
}

export function verifyToken(token) {
    try {
        return jwt.verify(token, JWT_SECRET);
    } catch (err) {
        return null;
    }
}

// ================== AUTHORIZATION MIDDLEWARE ==================
export function requireAuth(req, res, next) {
    if (req.session && req.session.userId) {
        return next();
    }
    
    logAudit(req, 'AUTH_FAILED', 'Truy cập bị từ chối - chưa đăng nhập', null);
    req.flash('error', 'Vui lòng đăng nhập để tiếp tục');
    res.redirect('/login');
}

export function requireAdmin(req, res, next) {
    if (req.session && req.session.role === 'admin') {
        return next();
    }
    
    logAudit(req, 'ADMIN_REQUIRED', 'Truy cập bị từ chối - không phải admin', req.session?.userId);
    req.flash('error', 'Bạn không có quyền truy cập tài nguyên này');
    res.redirect('/login');
}

// ================== RESOURCE AUTHORIZATION ==================
export const requireLockAccess = (req, res, next) => {
    const { lockId } = req.params;
    const userRole = req.session.role;
    const userLockId = req.session.lockId;

    // BỎ QUA KIỂM TRA NẾU LÀ ADMIN HOẶC SYSTEM (TỪ API KEY)
    if (userRole === 'admin' || userRole === 'system') {
        return next();
    }

    // Kiểm tra user thường
    if (userRole === 'user' && userLockId === lockId) {
        return next();
    }

    // Nếu không có quyền, trả về lỗi thay vì redirect
    // Điều này quan trọng cho các API call
    if (req.headers['x-api-key'] || req.path.startsWith('/api')) {
        return res.status(403).json({ success: false, error: 'Forbidden: Access Denied' });
    }

    // Đối với các request từ trình duyệt, redirect về login
    req.flash('error', 'Bạn không có quyền truy cập vào khóa này.');
    res.redirect('/login');
};

// ================== AUDIT LOGGING ==================
export async function logAudit(req, eventType, message, userId) {
    const logEntry = {
        timestamp: Date.now(),
        eventType,
        message,
        userId: userId || req.session?.userId || 'anonymous',
        userRole: req.session?.role || 'guest',
        ip: req.ip || req.connection.remoteAddress,
        userAgent: req.get('user-agent') || 'unknown',
        url: req.originalUrl,
        method: req.method,
        lockId: req.params?.lockId || req.body?.lockId || null
    };
    
    try {
        // ============================================
        // AUDIT MODE CONFIGURATION
        // ============================================
        const AUDIT_MODE = process.env.AUDIT_MODE || 'console'; // Options: 'firebase', 'console', 'off'
        
        // Log ra console (luôn chạy khi không phải 'off')
        if (AUDIT_MODE !== 'off') {
            console.log(`[AUDIT] ${eventType}: ${message} | User: ${logEntry.userId} | IP: ${logEntry.ip}`);
        }
        
        // Chỉ ghi Firebase khi AUDIT_MODE = 'firebase'
        if (AUDIT_MODE === 'firebase') {
            // KIỂM TRA db đã được khởi tạo chưa
            if (!db) {
                console.warn('[AUDIT WARNING] Database chưa được khởi tạo');
                return;
            }
            
            // Ghi vào Firebase
            const auditRef = db.ref('audit_logs');
            await auditRef.push(logEntry);
        }
    } catch (error) {
        console.error('[AUDIT ERROR]', error);
    }
}

// ================== INPUT SANITIZATION ==================
export function sanitizeInput(req, res, next) {
    // Loại bỏ các ký tự đặc biệt nguy hiểm
    const sanitize = (obj) => {
        if (typeof obj === 'string') {
            return obj.replace(/[<>]/g, '').trim();
        }
        if (typeof obj === 'object' && obj !== null) {
            for (let key in obj) {
                obj[key] = sanitize(obj[key]);
            }
        }
        return obj;
    };
    
    req.body = sanitize(req.body);
    req.query = sanitize(req.query);
    req.params = sanitize(req.params);
    
    next();
}

// ================== BRUTE FORCE PROTECTION ==================
const loginAttempts = new Map();

export function checkBruteForce(req, res, next) {
    const identifier = req.body.username || req.ip;
    const now = Date.now();
    
    if (!loginAttempts.has(identifier)) {
        loginAttempts.set(identifier, { count: 0, firstAttempt: now });
    }
    
    const attempts = loginAttempts.get(identifier);
    
    // Reset sau 30 phút
    if (now - attempts.firstAttempt > 30 * 60 * 1000) {
        loginAttempts.set(identifier, { count: 1, firstAttempt: now });
        return next();
    }
    
    // Chặn sau 10 lần thử
    if (attempts.count >= 10) {
        logAudit(req, 'BRUTE_FORCE_BLOCKED', `IP/User ${identifier} bị chặn do brute-force`, null);
        req.flash('error', 'Tài khoản tạm thời bị khóa do quá nhiều lần đăng nhập thất bại. Vui lòng liên hệ admin.');
        return res.redirect('/login');
    }
    
    attempts.count++;
    loginAttempts.set(identifier, attempts);
    next();
}

export function resetBruteForce(identifier) {
    loginAttempts.delete(identifier);
}
