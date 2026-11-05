import { useEffect, useState } from 'react';
import { createRequestScope } from './requestScope';

export function useRequestScope() {
  const [scope] = useState(createRequestScope);
  useEffect(() => () => scope.cancelAll(), [scope]);
  return scope;
}
