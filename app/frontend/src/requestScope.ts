/** Each channel owns its latest request; cleanup invalidates even late responses. */
export function createRequestScope() {
  let epoch = 0;
  const active = new Map<string, AbortController>();
  return {
    begin(channel: string) {
      active.get(channel)?.abort();
      const controller = new AbortController();
      const generation = epoch;
      active.set(channel, controller);
      return {
        signal: controller.signal,
        isCurrent: () => generation === epoch && !controller.signal.aborted && active.get(channel) === controller,
        finish: () => { if (active.get(channel) === controller) active.delete(channel); },
      };
    },
    cancelAll() {
      epoch += 1;
      for (const controller of active.values()) controller.abort();
      active.clear();
    },
  };
}
