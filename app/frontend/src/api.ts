export interface LineError { lineIndex: number; inventoryId?: number; code: string; message: string }

export class ApiError extends Error {
  code: string;
  status: number;
  details?: LineError[];
  constructor(code: string, message: string, status: number, details?: LineError[]) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

type QueryValue = string | number | boolean | undefined;

export function createApi(employeeNo: string) {
  async function responseFor(path: string, method: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
    const headers = new Headers({ 'X-User': employeeNo });
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    const response = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal });
    if (!response.ok) {
      const failure = await response.json().catch(() => ({})) as { code?: string; message?: string; details?: LineError[] };
      throw new ApiError(failure.code ?? 'REQUEST_FAILED', failure.message ?? '请求失败，请稍后重试。', response.status, failure.details);
    }
    return response;
  }
  async function request<T>(path: string, method: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const response = await responseFor(path, method, body, signal);
    let result: unknown;
    try { result = await response.json(); }
    catch { throw new ApiError('INVALID_RESPONSE', '无法读取服务响应，请稍后重试。', response.status); }
    return result as T;
  }
  return {
    get<T>(path: string, query: Record<string, QueryValue> = {}, signal?: AbortSignal) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) if (value !== undefined && value !== '') params.set(key, String(value));
      return request<T>(`${path}${params.size ? `?${params}` : ''}`, 'GET', undefined, signal);
    },
    post<T>(path: string, body?: unknown, signal?: AbortSignal) { return request<T>(path, 'POST', body, signal); },
  };
}

export type Api = ReturnType<typeof createApi>;
export function describeError(error: unknown): string {
  if (error instanceof ApiError) return `${error.code} · ${error.message}`;
  return '连接失败，请检查服务后重试。';
}
/** Write calls must not invite a blind retry: an unknown outcome is "check the record" (T1-F08). */
export function describeWriteFailure(error: unknown): string {
  if (error instanceof ApiError) return `${error.code} · ${error.message}`;
  return '未收到服务结果，请到「我的领用」核对记录后再决定是否重新提交。';
}
export function isAbort(error: unknown): boolean { return error instanceof Error && error.name === 'AbortError'; }
