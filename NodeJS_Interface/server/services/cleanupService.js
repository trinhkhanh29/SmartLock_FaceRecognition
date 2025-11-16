import admin from "firebase-admin";
import { cleanupOldLogs, limitLogsPerLock } from '../utils/firebase-cleanup.js';
import { cleanupOldAuditLogs, limitAuditLogs } from '../utils/audit-cleanup.js';

class CleanupService {
    constructor(db) {
        if (!db) {
            throw new Error("Database instance is required for CleanupService.");
        }
        this.db = db;
    }

    async cleanupTempCodes() {
        const allLocksSnapshot = await this.db.ref('locks').once('value');
        if (!allLocksSnapshot.exists()) {
            console.log('[CLEANUP] ℹ️ No locks found to clean temp codes.');
            return;
        }

        const allLocks = allLocksSnapshot.val();
        const now = new Date();
        let totalDeletedCodes = 0;

        for (const lockId in allLocks) {
            const tempCodesRef = this.db.ref(`locks/${lockId}/temp_codes`);
            const codesSnapshot = await tempCodesRef.once('value');

            if (codesSnapshot.exists()) {
                const codes = codesSnapshot.val();
                let deletedCount = 0;

                for (const code in codes) {
                    const codeData = codes[code];
                    const expiresAt = new Date(codeData.expiresAt);

                    if (expiresAt < now || codeData.status === 'used_up' || codeData.status === 'expired') {
                        await tempCodesRef.child(code).remove();
                        deletedCount++;
                    }
                }

                if (deletedCount > 0) {
                    totalDeletedCodes += deletedCount;
                    console.log(`[CLEANUP] ✅ Deleted ${deletedCount} expired/used temp codes for lock ${lockId}`);
                }
            }
        }

        if (totalDeletedCodes > 0) {
            console.log(`[CLEANUP] ✅ Total deleted temp codes: ${totalDeletedCodes}`);
        } else {
            console.log('[CLEANUP] ℹ️ No expired temp codes found to delete.');
        }
    }

    async cleanupActivityLogs() {
        await cleanupOldLogs(30); // Xóa logs cũ hơn 30 ngày

        const locksRef = this.db.ref('locks_registry');
        const snapshot = await locksRef.once('value');
        if (snapshot.exists()) {
            const locks = Object.keys(snapshot.val());
            for (const lockId of locks) {
                await limitLogsPerLock(lockId, 200); // Giới hạn 200 logs mỗi khóa
            }
        }
    }

    async cleanupAuditLogs() {
        if (process.env.AUDIT_MODE === 'firebase') {
            await cleanupOldAuditLogs(30); // Xóa audit logs cũ hơn 30 ngày
            await limitAuditLogs(1000); // Giữ tối đa 1000 audit logs
        }
    }

    async performAllCleanup() {
        console.log('[CLEANUP] Starting scheduled cleanup...');
        try {
            await this.cleanupTempCodes();
            await this.cleanupActivityLogs();
            await this.cleanupAuditLogs();
            console.log('[CLEANUP] ✅ Cleanup completed successfully');
        } catch (error) {
            console.error('[CLEANUP ERROR]', error.message);
        }
    }
}

export default CleanupService;
