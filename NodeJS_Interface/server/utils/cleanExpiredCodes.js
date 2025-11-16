let db;

// Khởi tạo với database instance
export function initializeCleanup(database) {
    db = database;
}

// Dọn dẹp mã hết hạn
export async function cleanupExpiredCodes() {
    try {
        console.log('[CLEANUP] Starting expired temp codes cleanup...');
        
        const snapshot = await db.ref('temp_codes').once('value');
        
        if (!snapshot.exists()) {
            console.log('[CLEANUP] No temp codes found');
            return;
        }

        const now = Date.now();
        let deletedCount = 0;

        const promises = [];
        
        snapshot.forEach(lockSnap => {
            const lockId = lockSnap.key;
            
            lockSnap.forEach(codeSnap => {
                const data = codeSnap.val();
                const code = codeSnap.key;
                
                // Xóa nếu hết hạn hoặc đã sử dụng
                if (now > data.expireAt || data.used) {
                    promises.push(
                        db.ref(`temp_codes/${lockId}/${code}`).remove()
                            .then(() => {
                                deletedCount++;
                                console.log(`[CLEANUP] Deleted code ${code} from lock ${lockId}`);
                            })
                    );
                }
            });
        });

        await Promise.all(promises);
        
        console.log(`[CLEANUP] Completed. Deleted ${deletedCount} expired/used codes`);
        
    } catch (error) {
        console.error('[CLEANUP] Error cleaning up temp codes:', error);
    }
}

// Lên lịch chạy mỗi 30 phút
export function startCleanupScheduler() {
    const INTERVAL = 30 * 60 * 1000; // 30 phút
    
    // Chạy ngay lập tức lần đầu
    cleanupExpiredCodes();
    
    // Sau đó chạy định kỳ
    setInterval(cleanupExpiredCodes, INTERVAL);
    
    console.log('[CLEANUP] Temp code cleanup scheduler started (runs every 30 minutes)');
}
