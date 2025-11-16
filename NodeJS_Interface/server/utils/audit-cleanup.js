// utils/audit-cleanup.js
import admin from 'firebase-admin';

/**
 * Xóa audit logs cũ hơn X ngày
 * @param {number} days - Số ngày
 */
export async function cleanupOldAuditLogs(days = 30) {
    try {
        const db = admin.database();
        const auditRef = db.ref('audit_logs');
        const cutoffTime = Date.now() - (days * 24 * 60 * 60 * 1000);
        
        console.log(`[AUDIT CLEANUP] Đang xóa logs cũ hơn ${days} ngày...`);
        
        const snapshot = await auditRef.orderByChild('timestamp').endAt(cutoffTime).once('value');
        
        if (!snapshot.exists()) {
            console.log('[AUDIT CLEANUP] Không có logs cũ cần xóa');
            return { success: true, deleted: 0 };
        }
        
        const oldLogs = snapshot.val();
        const deletePromises = [];
        
        for (const logKey in oldLogs) {
            deletePromises.push(auditRef.child(logKey).remove());
        }
        
        await Promise.all(deletePromises);
        
        const deletedCount = Object.keys(oldLogs).length;
        console.log(`[AUDIT CLEANUP] ✅ Đã xóa ${deletedCount} audit logs`);
        
        return { success: true, deleted: deletedCount };
    } catch (error) {
        console.error('[AUDIT CLEANUP ERROR]', error);
        return { success: false, error: error.message };
    }
}

/**
 * Giới hạn số lượng audit logs tối đa
 * @param {number} maxLogs - Số logs tối đa
 */
export async function limitAuditLogs(maxLogs = 1000) {
    try {
        const db = admin.database();
        const auditRef = db.ref('audit_logs');
        
        console.log(`[AUDIT CLEANUP] Đang giới hạn logs tối đa ${maxLogs}...`);
        
        // Đếm tổng số logs
        const snapshot = await auditRef.once('value');
        const totalLogs = snapshot.numChildren();
        
        if (totalLogs <= maxLogs) {
            console.log(`[AUDIT CLEANUP] Số logs hiện tại (${totalLogs}) trong giới hạn`);
            return { success: true, deleted: 0 };
        }
        
        // Lấy logs cũ nhất cần xóa
        const logsToDelete = totalLogs - maxLogs;
        const oldestLogs = await auditRef.orderByChild('timestamp').limitToFirst(logsToDelete).once('value');
        
        const deletePromises = [];
        oldestLogs.forEach(child => {
            deletePromises.push(auditRef.child(child.key).remove());
        });
        
        await Promise.all(deletePromises);
        
        console.log(`[AUDIT CLEANUP] ✅ Đã xóa ${logsToDelete} logs cũ nhất`);
        
        return { success: true, deleted: logsToDelete };
    } catch (error) {
        console.error('[AUDIT CLEANUP ERROR]', error);
        return { success: false, error: error.message };
    }
}

/**
 * Xóa toàn bộ audit logs
 */
export async function clearAllAuditLogs() {
    try {
        const db = admin.database();
        const auditRef = db.ref('audit_logs');
        
        console.log('[AUDIT CLEANUP] ⚠️ Đang xóa TOÀN BỘ audit logs...');
        
        await auditRef.remove();
        
        console.log('[AUDIT CLEANUP] ✅ Đã xóa toàn bộ audit logs');
        
        return { success: true };
    } catch (error) {
        console.error('[AUDIT CLEANUP ERROR]', error);
        return { success: false, error: error.message };
    }
}

/**
 * Export audit logs ra file JSON (backup trước khi xóa)
 */
export async function exportAuditLogs(outputPath = './audit_logs_backup.json') {
    try {
        const db = admin.database();
        const auditRef = db.ref('audit_logs');
        
        console.log('[AUDIT EXPORT] Đang export logs...');
        
        const snapshot = await auditRef.once('value');
        const logs = snapshot.val();
        
        if (!logs) {
            console.log('[AUDIT EXPORT] Không có logs để export');
            return { success: true, count: 0 };
        }
        
        const fs = await import('fs');
        fs.default.writeFileSync(outputPath, JSON.stringify(logs, null, 2));
        
        const count = Object.keys(logs).length;
        console.log(`[AUDIT EXPORT] ✅ Đã export ${count} logs vào ${outputPath}`);
        
        return { success: true, count, path: outputPath };
    } catch (error) {
        console.error('[AUDIT EXPORT ERROR]', error);
        return { success: false, error: error.message };
    }
}

// Nếu chạy trực tiếp file này
if (import.meta.url === `file://${process.argv[1]}`) {
    const command = process.argv[2];
    
    // Khởi tạo Firebase
    const serviceAccountPath = '../../../PyCharm/.env/firebase_credentials.json';
    const cred = admin.credential.cert(serviceAccountPath);
    if (!admin.apps.length) {
        admin.initializeApp({
            credential: cred,
            databaseURL: process.env.FIREBASE_DATABASE_URL || 'https://smartlockfacerecognition-default-rtdb.asia-southeast1.firebasedatabase.app/'
        });
    }
    
    switch (command) {
        case 'cleanup':
            const days = parseInt(process.argv[3]) || 30;
            await cleanupOldAuditLogs(days);
            break;
        case 'limit':
            const maxLogs = parseInt(process.argv[3]) || 1000;
            await limitAuditLogs(maxLogs);
            break;
        case 'clear':
            await clearAllAuditLogs();
            break;
        case 'export':
            const outputPath = process.argv[3] || './audit_logs_backup.json';
            await exportAuditLogs(outputPath);
            break;
        default:
            console.log(`
Audit Logs Cleanup Utility

Usage:
  node audit-cleanup.js cleanup [days]    - Xóa logs cũ hơn X ngày (default: 30)
  node audit-cleanup.js limit [maxLogs]   - Giới hạn số logs (default: 1000)
  node audit-cleanup.js clear             - Xóa TOÀN BỘ audit logs
  node audit-cleanup.js export [path]     - Export logs ra file JSON

Examples:
  node audit-cleanup.js cleanup 7         - Xóa logs cũ hơn 7 ngày
  node audit-cleanup.js limit 500         - Giữ lại 500 logs mới nhất
  node audit-cleanup.js export backup.json - Export ra backup.json
            `);
    }
    
    process.exit(0);
}
