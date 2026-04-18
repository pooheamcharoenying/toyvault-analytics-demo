/**
 * Shared axios instance with default timeout for all frontend API calls.
 *
 * Usage in page components:
 *   import api from "@/utils/api";
 *   const res = await api.get("/api/endpoint", { signal });
 *
 * Usage with AbortController in useEffect:
 *   useEffect(() => {
 *     const controller = new AbortController();
 *     api.get("/api/foo", { signal: controller.signal })
 *       .then(res => setData(res.data))
 *       .catch(err => { if (!controller.signal.aborted) setError(err.message); });
 *     return () => controller.abort();
 *   }, []);
 */
import axios from "axios";

const DEFAULT_TIMEOUT_MS = 30_000;

const api = axios.create({
  timeout: DEFAULT_TIMEOUT_MS,
  responseType: "json",
});

// Intercept timeout errors to provide user-friendly messages
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === "ECONNABORTED" || error.message?.includes("timeout")) {
      const timeoutError = new Error("Request timed out — please try again");
      timeoutError.isTimeout = true;
      return Promise.reject(timeoutError);
    }
    if (axios.isCancel(error)) {
      // Silently reject cancelled requests (component unmounted)
      const cancelError = new Error("Request cancelled");
      cancelError.isCancelled = true;
      return Promise.reject(cancelError);
    }
    return Promise.reject(error);
  }
);

/**
 * Check if an error is from a cancelled/aborted request (component unmounted).
 * Use this to avoid setting state on unmounted components.
 */
export function isAbortError(err) {
  if (!err) return false;
  if (err.isCancelled) return true;
  if (err.name === "CanceledError" || err.name === "AbortError") return true;
  if (axios.isCancel(err)) return true;
  return false;
}

export default api;
