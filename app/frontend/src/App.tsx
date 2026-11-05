import { useEffect, useState } from 'react';
import { Boxes, RefreshCw, UserRound } from 'lucide-react';
import { createApi, describeError, isAbort } from './api';
import { roleLabels, type User } from './types';
import { EmptyState } from './components/Feedback';
import Workspace from './components/Workspace';

export default function App() {
  const [users, setUsers] = useState<User[]>([]);
  const [employeeNo, setEmployeeNo] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    createApi('').get<User[]>('/api/session/users', {}, controller.signal).then((result) => {
      if (controller.signal.aborted) return;
      setUsers(result);
      setEmployeeNo((current) => result.some((user) => user.employeeNo === current) ? current : (result.find((user) => user.role === 'DISPATCHER') ?? result[0])?.employeeNo ?? '');
    }).catch((reason: unknown) => { if (!isAbort(reason)) setError(describeError(reason)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reload]);
  const selectedUser = users.find((user) => user.employeeNo === employeeNo);
  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark"><Boxes size={20} /></span><span>MaterialOps</span></div>
      <div className="topbar-context"><strong>设备备件助手</strong><span className="context-separator">/</span>领退 · 查证 · 调拨</div>
      <label className="user-switcher"><UserRound size={16} /><span className="sr-only">当前身份</span>
        <select data-test="identity-select" title={selectedUser ? `${selectedUser.name} · ${roleLabels[selectedUser.role]} · ${selectedUser.deptName}` : undefined} value={employeeNo} disabled={loading || users.length === 0} onChange={(event) => setEmployeeNo(event.target.value)}>
          {users.length === 0 ? <option value="">{loading ? '加载身份…' : '身份不可用'}</option> : users.map((user) => <option key={user.id} value={user.employeeNo}>{user.name} · {roleLabels[user.role]} · {user.deptName}</option>)}
        </select>
      </label>
    </header>
    {selectedUser ? <Workspace key={selectedUser.employeeNo} user={selectedUser} /> : <main className="startup-state">
      <EmptyState text={loading ? '正在加载身份…' : error || '暂无可用身份'} loading={loading} />
      {!loading ? <button className="button secondary" onClick={() => setReload((value) => value + 1)}><RefreshCw size={15} />重新加载</button> : null}
    </main>}
  </div>;
}
