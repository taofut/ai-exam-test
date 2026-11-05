export type Role = 'ADMIN' | 'DISPATCHER' | 'ENGINEER' | 'REPORTER';
export interface User { id: number; employeeNo: string; name: string; role: Role; deptId: number; deptName: string }
export interface Inventory {
  id: number; warehouseId: number; warehouseName: string; itemId: number; itemName: string; unit: string;
  itemNo: string; deptId: number; deptName: string;
  onHand: number; version: number; reorderPoint: number; targetStock: number;
  permissions: { canIssue: boolean; canAnalyze: boolean; canTransfer: boolean };
}
export interface MaterialIssue {
  id: number; issueNo: string; inventoryId: number; warehouseId: number; itemId: number; quantity: number;
  issuedById: number; issuedAt: string; returnedAt: string | null; status: 'ISSUED' | 'RETURNED'; version: number; inventoryVersion: number;
  issueOrderId: number | null; warehouseName: string; itemName: string; itemNo: string; unit: string;
  reasonText?: string; permissions: { canReturn: boolean };
}
export interface MaterialIssueOrder {
  id: number; orderNo: string; warehouseId: number; issuedById: number;
  reasonText: string; issuedAt: string; returnedAt: string | null; version: number;
  status: 'ISSUED' | 'RETURNED'; permissions: { canReturn: boolean };
}
export interface MaterialIssueOrderLine {
  id: number; issueNo: string; issueOrderId: number | null; inventoryId: number; quantity: number;
  issuedById: number; reasonText?: string; issuedAt: string; returnedAt: string | null;
  status: 'ISSUED' | 'RETURNED'; version: number; inventoryVersion: number;
  warehouseId: number; warehouseName: string; itemId: number; itemNo: string; itemName: string; unit: string;
  permissions: { canReturn: boolean };
}
export interface KitOrderDetail { order: MaterialIssueOrder; lines: MaterialIssueOrderLine[] }
export interface KitOrderResult extends KitOrderDetail { inventories: Inventory[] }
export interface IssueStats {
  totalQuantity: number | null;
  groups: { itemId: number; itemNo: string; name: string; unit: string; quantity: number; warehouseId?: number }[];
}
export interface Suggestion {
  warehouseId: number; itemId: number; suggestedQuantity: number; reason: string;
  confidence: number; needHuman: boolean;
  knowledgeReferences: { docId: number; title: string; version: number; quote: string }[];
}
export type Decision = 'PENDING' | 'ADOPTED' | 'ADOPTED_EDITED' | 'REJECTED';
export interface InventorySnapshot {
  id: number; warehouseId: number; warehouseName?: string; itemId: number; itemNo?: string;
  itemName?: string; unit?: string; onHand: number; version: number;
  reorderPoint: number; targetStock: number;
}
export interface AdviceIssueStats { period: 'TODAY'; quantity: number | null; scope: string; asOf: string }
export interface AdviceKnowledge { docId: number; title: string; version: number; general?: boolean; content: string }
export interface AnalysisContext {
  inventory: InventorySnapshot;
  issueStats: AdviceIssueStats;
  knowledge: AdviceKnowledge[];
  review?: { degraded?: boolean; requiresHumanReview?: boolean; reviewItems?: string[] };
  decisionMeta?: { reviewed?: boolean | null; actorId?: number; at?: string | null };
}
export interface Analysis {
  callId: number | string; inventoryId: number; inventoryVersion: number; suggestion: Suggestion;
  degraded: boolean; requiresHumanReview: boolean; reviewItems: string[];
  context: AnalysisContext; decision: Decision;
  finalSuggestion?: Suggestion | null; reviewed?: boolean | null;
  decisionById?: number | null; decisionAt?: string | null;
  usage?: Usage | null;
}
export interface TransferPreview {
  itemId: number; itemName: string; fromWarehouseId: number; toWarehouseId: number; quantity: number;
  fromOnHand: number; toOnHand: number; fromVersion: number; toVersion: number;
}
export interface AgentResponse {
  status: 'OK' | 'CONFIRM_REQUIRED' | 'EXECUTED'; answer: string; data?: Record<string, unknown> | unknown[] | null;
  citations?: { docId: number; title: string; version: number; quote: string }[]; preview?: TransferPreview;
  confirmToken?: string; confirmExpiresAt?: string; transferNo?: string; toolTrace?: Record<string, unknown>[];
  sessionId: string;
}
export interface Usage { inputTokens?: number | null; outputTokens?: number | null; prompt_tokens?: number | null; completion_tokens?: number | null; cost?: number | null; currency?: string }
export interface Notice { kind: 'success' | 'error'; message: string }
export const roleLabels: Record<Role, string> = { ADMIN: '管理员', DISPATCHER: '物资协调员', ENGINEER: '现场工程师', REPORTER: '申请查看人' };
export function formatTime(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '未知时间';
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(date);
}
