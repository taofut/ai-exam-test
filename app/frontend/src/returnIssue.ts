import type { Api } from './api';
import type { MaterialIssue } from './types';

export async function returnMaterialIssue(api: Api, issueId: number, signal?: AbortSignal) {
  const issue = await api.get<MaterialIssue>(`/api/material-issues/${issueId}`, {}, signal);
  return api.post<{ issue: MaterialIssue }>(`/api/material-issues/${issueId}/return`, { issueVersion: issue.version, inventoryVersion: issue.inventoryVersion }, signal);
}
