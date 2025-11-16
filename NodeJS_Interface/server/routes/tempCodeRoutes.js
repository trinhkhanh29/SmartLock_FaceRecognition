import express from 'express';
import {
    createTempCode,
    getActiveCodes,
    revokeCode,
    initializeTempCodeController,
    verifyTempCodePublic
} from '../controllers/tempCodeController.js';
import { requireAuth, requireLockAccess, apiLimiter } from '../middleware/security.js';

const router = express.Router();

// Middleware xác thực API Key hoặc Session
const requireApiKeyOrAuth = (req, res, next) => {
    const apiKey = req.headers['x-api-key'];
    if (apiKey && apiKey === (process.env.EXTERNAL_API_KEY || 'SuperSecretApiKey_2025_ChangeMe')) {
        req.session = req.session || {}; // Đảm bảo session tồn tại
        req.session.userId = `system_bot_${req.body.lockId || req.params.lockId || 'unknown'}`;
        req.session.role = 'system';
        // Cho phép truy cập mọi lockId khi dùng API key
        req.session.lockId = req.body.lockId || req.params.lockId;
        return next();
    }
    // Nếu không có API key, fallback về xác thực session
    return requireAuth(req, res, next);
};

// Hàm khởi tạo routes với database
export function initializeTempCodeRoutes(db) {
    initializeTempCodeController(db);
    
    // Tạo mã mới (yêu cầu đăng nhập hoặc API Key)
    router.post('/create', requireApiKeyOrAuth, createTempCode);

    // Lấy danh sách mã đang hoạt động (yêu cầu đăng nhập hoặc API Key)
    // SỬA: Bỏ requireLockAccess vì requireApiKeyOrAuth đã xử lý quyền truy cập cho API
    router.get('/active/:lockId', requireApiKeyOrAuth, (req, res, next) => {
        // Nếu không phải là system (tức là user thường), thì mới cần check lock access
        if (req.session.role !== 'system') {
            return requireLockAccess(req, res, next);
        }
        // Nếu là system, bỏ qua và đi tiếp
        return next();
    }, getActiveCodes);

    // Thu hồi mã (yêu cầu đăng nhập hoặc API Key)
    router.post('/revoke', requireApiKeyOrAuth, revokeCode);
    
    // Public endpoint cho ESP32 xác thực mã
    router.post('/verify-public', apiLimiter, verifyTempCodePublic);
    
    // Endpoint cũ, có thể bỏ đi trong tương lai
    router.post('/verify', apiLimiter, verifyTempCodePublic);

    return router;
}

export default router;
