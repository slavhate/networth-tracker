import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, X } from 'lucide-react';
import { exportAPI } from '../api';
import { downloadJson } from '../utils/download';
import { errorMessage } from '../utils/errors';
import { BACKUP_SECTIONS, countOf } from '../utils/backup';

const describeBackupDate = (value) => {
  const date = value ? new Date(value) : null;
  if (!date || isNaN(date)) return 'Backup date unknown';
  return `Backup from ${new Intl.DateTimeFormat('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true,
  }).format(date)}`;
};

const filenameTimestamp = () => {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
};

export default function RestoreDialog({ file, backup, onClose, onRestored }) {
  const [current, setCurrent] = useState(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [downloadFirst, setDownloadFirst] = useState(true);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState('');
  const downloadedRef = useRef(false);
  const backupIsEmpty = BACKUP_SECTIONS.every(({ key }) => countOf(backup, key) === 0) && !backup?.goal;

  useEffect(() => {
    let cancelled = false;
    exportAPI.download()
      .then((response) => { if (!cancelled) setCurrent(response.data); })
      .catch(() => { if (!cancelled) setLoadFailed(true); });
    return () => { cancelled = true; };
  }, []);

  const handleReplace = async () => {
    setError('');
    setRestoring(true);
    let restored;
    try {
      if (downloadFirst && !downloadedRef.current) {
        downloadJson(current, `networth_pre-restore_${filenameTimestamp()}.json`);
        downloadedRef.current = true;
      }
      restored = (await exportAPI.restore(file)).data.restored;
    } catch (err) {
      setError(errorMessage(err, 'Restore failed'));
      setRestoring(false);
      return;
    }
    onRestored(restored);
  };

  const loading = current === null && !loadFailed;
  const canReplace = current !== null && !restoring;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Restore from backup</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{describeBackupDate(backup?.export_date)}</p>
          </div>
          <button
            onClick={onClose}
            disabled={restoring}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm break-words">
              {error}
            </div>
          )}

          {loadFailed ? (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
              Couldn't load your current data
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="font-medium pb-2"></th>
                  <th className="font-medium pb-2 text-right">In backup</th>
                  <th className="font-medium pb-2 text-right">In your account now</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-gray-100">
                {BACKUP_SECTIONS.map(({ key, label }) => (
                  <tr key={key}>
                    <td className="py-1">{label}</td>
                    <td className="py-1 text-right">{countOf(backup, key)}</td>
                    <td className="py-1 text-right">{loading ? '…' : countOf(current, key)}</td>
                  </tr>
                ))}
                <tr>
                  <td className="py-1">Goal</td>
                  <td className="py-1 text-right">{backup?.goal ? 'Yes' : 'No'}</td>
                  <td className="py-1 text-right">{loading ? '…' : (current?.goal ? 'Yes' : 'No')}</td>
                </tr>
              </tbody>
            </table>
          )}

          {backupIsEmpty && (
            <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm font-medium">
              This backup is empty — restoring it deletes everything in your account.
            </div>
          )}

          <div className="flex gap-2 bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 px-4 py-3 rounded-lg text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>Everything currently in your account will be replaced by this backup. This can't be undone.</span>
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              type="checkbox"
              checked={downloadFirst}
              onChange={(e) => setDownloadFirst(e.target.checked)}
              disabled={restoring}
            />
            Download my current data first
          </label>

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} disabled={restoring} className="btn-secondary flex-1 disabled:opacity-50">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReplace}
              disabled={!canReplace}
              className="btn-danger flex-1 flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {(restoring || loading) && <Loader2 className="w-4 h-4 animate-spin" />}
              {restoring ? 'Restoring...' : loading ? 'Loading...' : 'Replace my data'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
