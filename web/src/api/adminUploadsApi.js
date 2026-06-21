// Admin V2 image upload client (file → /assets/admin_uploads/...). Reuses V2 session.
import { requestAdminJson } from "./adminApi.js";

// Прочитать File в чистый base64 (без data:-префикса — сервер принимает оба).
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",", 2)[1] : result);
    };
    reader.onerror = () => reject(new Error("Не удалось прочитать файл."));
    reader.readAsDataURL(file);
  });
}

export function uploadImage(category, key, contentBase64, reason) {
  return requestAdminJson(`/api/admin/v2/uploads/image`, {
    method: "POST",
    body: JSON.stringify({ category, key, content_base64: contentBase64, reason: reason || "" }),
  });
}
