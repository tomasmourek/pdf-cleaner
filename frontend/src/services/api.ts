/**
 * API klient pro upravpdf.eu — PDF upload, polling, handoff, auth.
 */
import axios, { AxiosInstance } from "axios";

const AUTH_URL = import.meta.env.VITE_AUTH_URL || "https://auth.upravpdf.eu";
const PDF_URL = import.meta.env.VITE_PDF_URL || "https://upravpdf.eu";

const getAccessToken = () => localStorage.getItem("access_token");
const getRefreshToken = () => localStorage.getItem("refresh_token");
const setTokens = (access: string, refresh: string) => {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
};
const clearTokens = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
};

const createClient = (baseURL: string): AxiosInstance => {
  const client = axios.create({ baseURL, withCredentials: false });
  client.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  });
  client.interceptors.response.use(
    (res) => res,
    async (error) => {
      const original = error.config;
      if (error.response?.status === 401 && !original._retry) {
        original._retry = true;
        const refreshToken = getRefreshToken();
        if (refreshToken) {
          try {
            const res = await axios.post(`${AUTH_URL}/auth/refresh`, { refresh_token: refreshToken });
            const { access_token, refresh_token: newRefresh } = res.data;
            setTokens(access_token, newRefresh);
            original.headers.Authorization = `Bearer ${access_token}`;
            return client(original);
          } catch {
            clearTokens();
            window.location.href = "/login";
          }
        }
      }
      return Promise.reject(error);
    }
  );
  return client;
};

export const authClient = createClient(AUTH_URL);
export const pdfClient = createClient(PDF_URL);

export const authApi = {
  login: (data: { email: string; password: string; remember_me: boolean }) =>
    authClient.post("/auth/login", data).then((r) => {
      setTokens(r.data.access_token, r.data.refresh_token);
      return r.data;
    }),
  logout: () => authClient.post("/auth/logout", { refresh_token: getRefreshToken() }).finally(clearTokens),
  getMe: () => authClient.get("/auth/me"),
  register: (data: object) => authClient.post("/auth/register", data),
  verifyEmail: (token: string) => authClient.post("/auth/verify-email", { token }),
  forgotPassword: (email: string) => authClient.post("/auth/forgot-password", { email }),
  resetPassword: (token: string, new_password: string) =>
    authClient.post("/auth/reset-password", { token, new_password }),
};

export const pdfApi = {
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return pdfClient.post("/pdf/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  getJob: (id: string) => pdfClient.get(`/pdf/jobs/${id}`),
  getResult: (id: string) => pdfClient.get(`/pdf/jobs/${id}/result`),
  handoff: (id: string) => pdfClient.post(`/pdf/handoff/${id}`),
  getHistory: (page = 1) => pdfClient.get(`/pdf/history?page=${page}`),
  deleteHistory: (id: string) => pdfClient.delete(`/pdf/history/${id}`),
  // Batch
  batchUpload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return pdfClient.post("/pdf/batch/upload", form, { headers: { "Content-Type": "multipart/form-data" } });
  },
  getBatch: (id: string) => pdfClient.get(`/pdf/batch/${id}/status`),
  mergeBatch: (id: string) => pdfClient.post(`/pdf/batch/${id}/merge`),
};
