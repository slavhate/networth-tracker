import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Camera, X } from 'lucide-react';
import { dashboardAPI, snapshotSettingsAPI } from '../api';
import { formatDate } from '../utils/dates';
import { errorMessage } from '../utils/errors';
import { SNAPSHOT_FREQUENCIES, snapshotFrequency } from '../utils/snapshotFrequencies';

// Automatic snapshot frequency and a manual "save now", opened from the dashboard header.
// onFrequencyChanged receives the saved settings ({ frequency, next_snapshot_on });
// onSaved runs after a manual snapshot is stored.
export default function SnapshotDialog({ frequency, nextSnapshotOn, lastSnapshotOn, onClose, onFrequencyChanged, onSaved }) {
  const [frequencySaving, setFrequencySaving] = useState(false);
  const [frequencyError, setFrequencyError] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  useEffect(() => {
    const closeOnEscape = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  // Saved straight away; the response carries the recalculated next date
  const changeFrequency = async (value) => {
    try {
      setFrequencySaving(true);
      setFrequencyError('');
      const response = await snapshotSettingsAPI.update(value);
      onFrequencyChanged(response.data);
    } catch (err) {
      setFrequencyError(errorMessage(err, 'Failed to change the snapshot frequency'));
    } finally {
      setFrequencySaving(false);
    }
  };

  const saveNow = async () => {
    try {
      setSaving(true);
      setSaveError('');
      await dashboardAPI.createSnapshot();
      onSaved();
    } catch (err) {
      setSaveError(errorMessage(err, 'Failed to create snapshot'));
      setSaving(false);
    }
  };

  const current = snapshotFrequency(frequency);

  // Rendered on <body> so page spacing (space-y margins) can't shift the fixed overlay
  return createPortal(
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="snapshot-dialog-title"
        className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md"
      >
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <h2 id="snapshot-dialog-title" className="text-lg font-semibold text-gray-900 dark:text-white">Snapshots</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6 space-y-5">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            A snapshot records your net worth and asset allocation for the history charts.
          </p>

          <div>
            <label htmlFor="auto-snapshot" className="label">Automatic snapshot</label>
            <select
              id="auto-snapshot"
              className="input"
              value={current.value}
              onChange={(e) => changeFrequency(e.target.value)}
              disabled={frequencySaving}
              autoFocus
            >
              {SNAPSHOT_FREQUENCIES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
            {nextSnapshotOn && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Next automatic snapshot: {formatDate(nextSnapshotOn)}, saved when you open the dashboard on or after that day.
              </p>
            )}
            {frequencyError && (
              <p role="alert" className="text-xs text-red-600 dark:text-red-400 mt-1">{frequencyError}</p>
            )}
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400">
            {lastSnapshotOn ? `Last snapshot: ${formatDate(lastSnapshotOn)}` : 'No snapshots yet.'}
          </p>

          {saveError && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">{saveError}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button onClick={onClose} className="btn-secondary flex-1">
              Close
            </button>
            <button
              onClick={saveNow}
              disabled={saving}
              className="btn-primary flex-1 flex items-center justify-center gap-2"
            >
              <Camera className="w-4 h-4" />
              {saving ? 'Saving...' : 'Save now'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
