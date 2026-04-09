import axios from 'axios'

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export function normalizeApiError(error) {
  if (error?.response?.data?.detail) {
    const { detail } = error.response.data
    if (typeof detail === 'string') {
      return detail
    }
    return JSON.stringify(detail)
  }

  if (error?.message === 'Network Error') {
    return '无法连接后端接口，请确认 FastAPI 服务已启动并允许跨域访问。'
  }

  if (error?.code === 'ECONNABORTED') {
    return '请求超时，请稍后重试。'
  }

  return error?.message || '请求失败，请稍后重试。'
}

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20000,
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(new Error(normalizeApiError(error))),
)

export default http
