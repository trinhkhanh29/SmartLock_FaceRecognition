import crypto from 'crypto';

let db;

// Database instance sẽ được inject từ routes
let dbInstance = null;

// Hàm khởi tạo database
export function initializeTempCodeController(database) {
    console.log('[TEMP_CODE_CONTROLLER] Initializing with database');
    if (!database) {
        throw new Error('Database instance is required');
    }
    db = database;
    dbInstance = database;
    console.log('[TEMP_CODE_CONTROLLER] ✅ Initialized successfully');
}

// Phân tích chuỗi thời gian (duration) từ yêu cầu
function parseDuration(durationStr) {
    if (!durationStr) return null;

    const now = new Date();
    const value = parseInt(durationStr);
    const unit = durationStr.slice(-1).toLowerCase();

    if (isNaN(value)) return null;

    switch (unit) {
        case 'h':
            return new Date(now.getTime() + value * 60 * 60 * 1000);
        case 'd':
            return new Date(now.getTime() + value * 24 * 60 * 60 * 1000);
        default:
            return null;
    }
}

// Tạo mã tạm thời mới
export const createTempCode = async (req, res) => {
    try {
        if (!dbInstance) {
            throw new Error('Database not initialized');
        }
        
        const { lockId, duration, description } = req.body;
        
        if (!lockId || !duration) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields: lockId, duration'
            });
        }
        
        // Phân tích thời gian hết hạn
        const expiresAt = parseDuration(duration);
        if (!expiresAt) {
            return res.status(400).json({ success: false, error: 'Định dạng duration không hợp lệ' });
        }

        // Generate 6-digit code
        const code = Math.floor(100000 + Math.random() * 900000).toString();
        
        const now = new Date();
        
        const codeData = {
            code: code,
            lockId: lockId,
            createdAt: now.toISOString(),
            expiresAt: expiresAt.toISOString(),
            createdBy: req.session?.userId || 'system',
            createdFrom: req.headers['x-api-key'] ? 'api' : 'dashboard',
            description: description || 'Mã tạm thời',
            maxUses: 1,
            usedCount: 0,
            status: 'active'
        };
        
        console.log('[TEMP_CODE] Dữ liệu sẽ lưu:', JSON.stringify(codeData, null, 2));
        console.log('[TEMP_CODE] Đường dẫn Firebase:', `locks/${lockId}/temp_codes/${code}`);

        // Tạo mã mới - LƯU VÀO REALTIME DATABASE
        try {
            console.log('[TEMP_CODE] Bắt đầu ghi vào Firebase...');
            const ref = db.ref(`locks/${lockId}/temp_codes/${code}`);
            await ref.set(codeData);
            console.log('[TEMP_CODE] ✅ GHI FIREBASE THÀNH CÔNG!');
            
            // Kiểm tra lại xem đã lưu chưa
            const verifySnapshot = await ref.once('value');
            if (verifySnapshot.exists()) {
                console.log('[TEMP_CODE] ✅ XÁC NHẬN: Dữ liệu đã được lưu vào Firebase');
                console.log('[TEMP_CODE] Dữ liệu đã lưu:', verifySnapshot.val());
            } else {
                console.error('[TEMP_CODE] ❌ CẢNH BÁO: Không tìm thấy dữ liệu sau khi ghi!');
            }
        } catch (writeError) {
            console.error('[TEMP_CODE] ❌ LỖI KHI GHI FIREBASE:', writeError);
            console.error('[TEMP_CODE] Error code:', writeError.code);
            console.error('[TEMP_CODE] Error message:', writeError.message);
            console.error('[TEMP_CODE] Error stack:', writeError.stack);
            
            return res.status(500).json({
                success: false,
                error: 'Lỗi khi ghi Firebase: ' + writeError.message
            });
        }

        console.log(`[TEMP_CODE] ========== TẠO MÃ THÀNH CÔNG ==========`);
        console.log(`[TEMP_CODE] Mã: ${code}`);
        console.log(`[TEMP_CODE] Lock ID: ${lockId}`);
        console.log(`[TEMP_CODE] Hết hạn: ${new Date(expiresAt).toLocaleString('vi-VN')}`);

        res.status(201).json({
            success: true,
            code,
            lockId,
            description: description || 'No description',
            expireAtFormatted: expiresAt.toLocaleString('vi-VN', {
                timeZone: 'Asia/Ho_Chi_Minh',
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            }),
            expiresAt: expiresAt.toISOString()
        });

    } catch (error) {
        console.error('[TEMP_CODE] ❌ LỖI KHÔNG MONG ĐỢI:', error);
        console.error('[TEMP_CODE] Error stack:', error.stack);
        res.status(500).json({ 
            success: false, 
            error: 'Không thể tạo mã tạm thời: ' + error.message
        });
    }
};

// Xác thực mã từ ESP32
export const verifyTempCode = async (req, res) => {
    try {
        if (!dbInstance) {
            throw new Error('Database not initialized');
        }
        
        const { code, lockId } = req.body;
        
        if (!code || !lockId) {
            return res.status(400).json({
                success: false,
                valid: false,
                error: 'Missing code or lockId'
            });
        }
        
        const codeRef = dbInstance.ref(`locks/${lockId}/temp_codes/${code}`);
        const snapshot = await codeRef.once('value');
        
        if (!snapshot.exists()) {
            return res.json({
                success: false,
                valid: false,
                message: 'Code not found'
            });
        }
        
        const codeData = snapshot.val();
        const now = new Date();
        const expiresAt = new Date(codeData.expiresAt);
        
        if (expiresAt < now) {
            await codeRef.update({ status: 'expired' });
            return res.json({
                success: false,
                valid: false,
                message: 'Code expired'
            });
        }
        
        if (codeData.usedCount >= codeData.maxUses) {
            await codeRef.update({ status: 'used_up' });
            return res.json({
                success: false,
                valid: false,
                message: 'Code used up'
            });
        }
        
        // Update usage
        await codeRef.update({
            usedCount: (codeData.usedCount || 0) + 1,
            lastUsedAt: now.toISOString(),
            status: (codeData.usedCount + 1) >= codeData.maxUses ? 'used_up' : 'active'
        });
        
        // Log activity
        await dbInstance.ref(`locks/${lockId}/activity_log`).push({
            name: `Temp Code: ${code}`,
            type: 'TEMP_CODE_SUCCESS',
            timestamp: Date.now(),
            imageUrl: null,
            code: code
        });
        
        res.json({
            success: true,
            valid: true,
            message: 'Code verified'
        });
        
    } catch (error) {
        console.error('[VERIFY_TEMP_CODE ERROR]', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

// Lấy danh sách mã đang hoạt động
export const getActiveCodes = async (req, res) => {
    try {
        if (!dbInstance) {
            throw new Error('Database not initialized');
        }
        
        const { lockId } = req.params;
        
        const codesRef = dbInstance.ref(`locks/${lockId}/temp_codes`);
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
            
            if (expiresAt > now && data.usedCount < data.maxUses && data.status === 'active') {
                const timeRemaining = Math.round((expiresAt - now) / 1000 / 60);
                
                activeCodes.push({
                    code: code,
                    description: data.description || 'No description',
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
        console.error('[GET_ACTIVE_CODES ERROR]', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

// Thu hồi mã
export const revokeCode = async (req, res) => {
    try {
        if (!dbInstance) {
            throw new Error('Database not initialized');
        }
        
        const { lockId, code } = req.body;
        
        if (!lockId || !code) {
            return res.status(400).json({
                success: false,
                error: 'Missing lockId or code'
            });
        }
        
        const codeRef = dbInstance.ref(`locks/${lockId}/temp_codes/${code}`);
        const snapshot = await codeRef.once('value');
        
        if (!snapshot.exists()) {
            return res.status(404).json({
                success: false,
                error: 'Code not found'
            });
        }
        
        await codeRef.update({
            status: 'revoked',
            revokedAt: new Date().toISOString(),
            revokedBy: req.session?.userId || 'system'
        });
        
        console.log(`✅ Revoked code: ${code} for lock ${lockId}`);
        
        res.json({
            success: true,
            message: 'Code revoked successfully'
        });
        
    } catch (error) {
        console.error('[REVOKE_CODE ERROR]', error);
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
};

// THÊM: Public endpoint cho ESP32 (không cần auth)
export const verifyTempCodePublic = async (req, res) => {
    return verifyTempCode(req, res);
}

// Helper function: Tính thời gian còn lại
function getTimeRemaining(ms) {
    const hours = Math.floor(ms / (1000 * 60 * 60));
    const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
    
    if (hours > 24) {
        const days = Math.floor(hours / 24);
        return `${days} ngày`;
    } else if (hours > 0) {
        return `${hours} giờ ${minutes} phút`;
    } else {
        return `${minutes} phút`;
    }
}
