import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { subscribe } from '../utils/notices';

const SHOW_FOR_MS = 15000;
const MAX_SHOWN = 3;
let nextId = 0;

// Warnings flashed in the top-right corner; each can be dismissed and hides on its own 15 seconds after it comes on
// screen. At most three are shown at once; the rest wait in a queue, counted on a line that can dismiss them all.
export default function Notices() {
  // In arrival order: the first MAX_SHOWN are on screen, the others queued
  const [notices, setNotices] = useState([]);
  const timers = useRef(new Map());

  useEffect(() => subscribe((message) => {
    setNotices((list) => (list.some((n) => n.message === message) ? list : [...list, { id: ++nextId, message }]));
  }), []);

  const dismiss = (id) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setNotices((list) => list.filter((n) => n.id !== id));
  };

  const clearTimers = () => {
    timers.current.forEach((timer) => clearTimeout(timer));
    timers.current.clear();
  };

  const dismissAll = () => {
    clearTimers();
    setNotices([]);
  };

  const shown = notices.slice(0, MAX_SHOWN);
  const queued = notices.length - shown.length;

  // A toast's time starts when it comes on screen, so one revealed from the queue gets its full 15 seconds
  useEffect(() => {
    shown.forEach((n) => {
      if (!timers.current.has(n.id)) timers.current.set(n.id, setTimeout(() => dismiss(n.id), SHOW_FOR_MS));
    });
  }, [notices]);

  useEffect(() => clearTimers, []);

  // The live region stays mounted (empty it has no height and, being pointer-events-none, never blocks clicks)
  // so screen readers announce toasts that are added to it later.
  return (
    <div className="pointer-events-none fixed top-4 right-4 z-[70] w-[calc(100%-2rem)] max-w-sm space-y-2" aria-live="polite">
      {shown.map((n) => (
        <div
          key={n.id}
          className="pointer-events-auto flex items-start gap-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/60 text-amber-800 dark:text-amber-100 px-4 py-3 shadow-lg"
        >
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-sm flex-1">{n.message}</p>
          <button
            type="button"
            onClick={() => dismiss(n.id)}
            aria-label={`Dismiss: ${n.message}`}
            className="p-1 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-800/60"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
      {queued > 0 && (
        <div className="pointer-events-auto flex items-center justify-between gap-3 rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/60 text-amber-800 dark:text-amber-100 px-4 py-2 shadow-lg">
          <p className="text-sm">+{queued} more {queued === 1 ? 'warning' : 'warnings'}</p>
          <button
            type="button"
            onClick={dismissAll}
            className="text-sm font-medium px-2 py-1 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-800/60"
          >
            Dismiss all
          </button>
        </div>
      )}
    </div>
  );
}
