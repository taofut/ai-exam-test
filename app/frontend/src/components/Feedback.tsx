import { AlertCircle, CheckCircle2, LoaderCircle } from 'lucide-react';
import type { Notice } from '../types';

export function Feedback({ notice }: { notice: Notice | null }) {
  if (!notice) return null;
  return <div className={`feedback ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
    {notice.kind === 'error' ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}<span>{notice.message}</span>
  </div>;
}
export function EmptyState({ text, loading = false }: { text: string; loading?: boolean }) {
  return <div className="empty-state" role="status">{loading ? <LoaderCircle className="spin" size={22} /> : null}<p>{text}</p></div>;
}
