// Firebase utilities (nếu cần)
// Database instance được khởi tạo trong app.js và truyền vào các module cần thiết

export function formatTimestamp(timestamp) {
    return new Date(timestamp).toLocaleString('vi-VN');
}

export function isExpired(expireAt) {
    return Date.now() > expireAt;
}
