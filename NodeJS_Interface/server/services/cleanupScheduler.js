const CLEANUP_INTERVAL = 24 * 60 * 60 * 1000; // 24 giờ
const CLEANUP_HOUR = 2; // 2 giờ sáng

class CleanupScheduler {
    constructor(cleanupService) {
        this.cleanupService = cleanupService;
        this.timeoutId = null;
    }

    start() {
        const now = new Date();
        const nextCleanup = new Date(
            now.getFullYear(),
            now.getMonth(),
            now.getDate() + (now.getHours() >= CLEANUP_HOUR ? 1 : 0),
            CLEANUP_HOUR,
            0,
            0
        );

        const timeUntilNextCleanup = nextCleanup.getTime() - now.getTime();

        this.timeoutId = setTimeout(() => {
            this.cleanupService.performAllCleanup();
            setInterval(() => this.cleanupService.performAllCleanup(), CLEANUP_INTERVAL);
        }, timeUntilNextCleanup);

        console.log(`[CLEANUP] Scheduled next cleanup at ${nextCleanup.toLocaleString('vi-VN')}`);
    }

    stop() {
        if (this.timeoutId) {
            clearTimeout(this.timeoutId);
            this.timeoutId = null;
            console.log('[CLEANUP] Scheduler stopped.');
        }
    }
}

export default CleanupScheduler;
