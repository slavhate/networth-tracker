// A tiny hub for warnings shown as dismissible toasts: the API client publishes, <Notices /> listens.
const listeners = new Set();

export function publishWarnings(messages) {
  messages.forEach((message) => listeners.forEach((listener) => listener(message)));
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
