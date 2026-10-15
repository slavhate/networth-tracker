import { RefreshCw, X } from 'lucide-react';

// A page-level error (list load or delete failure), shown above the page content.
// onRetry adds a Retry button; onDismiss adds a close button.
export default function PageError({ message, onRetry, onDismiss }) {
  if (!message) return null;
  return (
    <div
      className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg flex flex-wrap items-center justify-between gap-3"
      role="alert"
    >
      <span className="text-sm">{message}</span>
      <div className="flex items-center gap-2">
        {onRetry && (
          <button onClick={onRetry} className="btn-secondary flex items-center gap-2 text-sm">
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        )}
        {onDismiss && (
          <button onClick={onDismiss} className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/50" aria-label="Dismiss">
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );
}
