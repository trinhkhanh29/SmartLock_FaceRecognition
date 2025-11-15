import admin from 'firebase-admin';

/**
 * Tự động xóa log cũ hơn X ngày
 * @param {number} daysToKeep - Số ngày giữ lại log (mặc định 30)
 */
export async function cleanupOldLogs(daysToKeep = 30) {
    const db = admin.database();
    const now = Date.now();
    const cutoffTime = now - (daysToKeep * 24 * 60 * 60 * 1000);
    
    try {
        // Lấy tất cả locks
        const locksRef = db.ref('locks_registry');
        const locksSnapshot = await locksRef.once('value');
        
        if (!locksSnapshot.exists()) {
            console.log('[CLEANUP] Không có lock nào');
            return;
        }
        
        const locks = Object.keys(locksSnapshot.val());
        let totalDeleted = 0;
        
        for (const lockId of locks) {
            const logsRef = db.ref(`locks/${lockId}/activity_log`);
            const logsSnapshot = await logsRef.orderByChild('timestamp').endAt(cutoffTime).once('value');
            
            if (logsSnapshot.exists()) {
                const oldLogs = logsSnapshot.val();
                const deleteCount = Object.keys(oldLogs).length;
                
                // Xóa các log cũ
                for (const logKey in oldLogs) {
                    await logsRef.child(logKey).remove();
                }
                
                totalDeleted += deleteCount;
                console.log(`[CLEANUP] Đã xóa ${deleteCount} log cũ từ lock ${lockId}`);
            }
        }
        
        console.log(`[CLEANUP] Tổng cộng đã xóa ${totalDeleted} log cũ`);
        return totalDeleted;
    } catch (error) {
        console.error('[CLEANUP ERROR]', error);
        throw error;
    }
}

/**
 * Giới hạn số lượng log tối đa cho mỗi lock
 * @param {string} lockId - ID của lock
 * @param {number} maxLogs - Số log tối đa giữ lại (mặc định 100)
 */
export async function limitLogsPerLock(lockId, maxLogs = 100) {
    const db = admin.database();
    
    try {
        const logsRef = db.ref(`locks/${lockId}/activity_log`);
        const snapshot = await logsRef.orderByChild('timestamp').once('value');
        
        if (!snapshot.exists()) {
            return 0;
        }
        
        const logs = [];
        snapshot.forEach(child => {
            logs.push({ key: child.key, timestamp: child.val().timestamp });
        });
        
        // Sắp xếp theo timestamp giảm dần
        logs.sort((a, b) => b.timestamp - a.timestamp);
        
        // Xóa các log vượt quá maxLogs
        if (logs.length > maxLogs) {
            const logsToDelete = logs.slice(maxLogs);
            for (const log of logsToDelete) {
                await logsRef.child(log.key).remove();
            }
            console.log(`[LIMIT] Đã xóa ${logsToDelete.length} log từ lock ${lockId}`);
            return logsToDelete.length;
        }
        
        return 0;
    } catch (error) {
        console.error('[LIMIT ERROR]', error);
        throw error;
    }
}
