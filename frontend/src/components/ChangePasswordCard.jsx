import { useState } from 'react';
import { KeyRound, AlertCircle, CheckCircle } from 'lucide-react';
import { authAPI } from '../api';
import { useAuth } from '../AuthContext';
import { errorMessage } from '../utils/errors';

const EMPTY_FORM = { current: '', next: '', confirm: '', code: '' };

export default function ChangePasswordCard({ twoFactorEnabled, onChanged }) {
  const { user, replaceToken } = useAuth();
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);

  const update = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const validate = () => {
    if (!form.current) return 'Enter your current password';
    if (form.next.length < 6) return 'New password must be at least 6 characters';
    if (form.next !== form.confirm) return 'New passwords do not match';
    if (form.next === form.current) return 'New password must be different from the current password';
    return '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSuccess('');
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError('');
    setBusy(true);
    try {
      const res = await authAPI.changePassword({
        current_password: form.current,
        new_password: form.next,
        ...(twoFactorEnabled ? { code: form.code } : {}),
      });
      replaceToken(res.data.access_token);
      setForm(EMPTY_FORM);
      setSuccess("Password changed. You've been signed out on your other devices.");
      onChanged?.(); // e.g. refresh the backup-code count a backup code may just have reduced
    } catch (err) {
      setError(errorMessage(err, 'Failed to change password'));
      setForm((prev) => ({ ...prev, code: '' }));
      onChanged?.(); // e.g. pick up a 2FA change made elsewhere, or a spent backup code
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card max-w-3xl">
      <div className="flex items-start gap-4">
        <div className="p-3 rounded-xl flex-shrink-0 bg-primary-50 text-primary-600 dark:bg-primary-900/50 dark:text-primary-300">
          <KeyRound className="w-6 h-6" />
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Change password</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
            Changing your password signs you out on all your other devices.
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="mt-4 flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {success && (
        <div role="status" className="mt-4 flex items-center gap-2 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 px-4 py-3 rounded-lg text-sm">
          <CheckCircle className="w-4 h-4 flex-shrink-0" />
          {success}
        </div>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-4" noValidate>
        {/* Lets browsers and password managers tie this change to the saved account. */}
        <input type="text" name="username" autoComplete="username" value={user?.username || ''} readOnly hidden />
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label" htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              className="input"
              value={form.current}
              onChange={update('current')}
              required
            />
          </div>
          <div>
            <label className="label" htmlFor="new-password">New password</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              className="input"
              value={form.next}
              onChange={update('next')}
              required
            />
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">At least 6 characters</p>
          </div>
          <div>
            <label className="label" htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              className="input"
              value={form.confirm}
              onChange={update('confirm')}
              required
            />
          </div>
          {twoFactorEnabled && (
            <div className="sm:col-span-2">
              <label className="label" htmlFor="change-password-code">Authentication or backup code</label>
              <input
                id="change-password-code"
                type="text"
                autoComplete="one-time-code"
                className="input font-mono sm:max-w-xs"
                maxLength={20}
                value={form.code}
                onChange={update('code')}
                required
              />
            </div>
          )}
        </div>
        <button type="submit" disabled={busy} className="btn-primary disabled:opacity-50">
          {busy ? 'Changing…' : 'Change password'}
        </button>
      </form>
    </div>
  );
}
