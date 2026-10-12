import { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { ShieldCheck, ShieldOff, Copy, Check, Download, KeyRound, AlertCircle } from 'lucide-react';
import { twoFactorAPI } from '../api';

const errorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

const groupSecret = (secret) => secret.match(/.{1,4}/g).join(' ');

// Resolves only if the text really reached the clipboard; throws otherwise.
const copyText = async (text) => {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // permission denied or document not focused: fall through to the textarea fallback
    }
  }
  // navigator.clipboard is unavailable over plain http (common for self-hosted LAN installs)
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.readOnly = true; // keeps iOS from opening the keyboard
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  try {
    textarea.select();
    textarea.setSelectionRange(0, text.length); // iOS Safari ignores select() alone
    const ok = document.execCommand('copy');
    if (!ok) throw new Error('copy failed');
  } finally {
    document.body.removeChild(textarea);
  }
};

function BackupCodesModal({ codes, onClose }) {
  const [copyState, setCopyState] = useState(null); // null | 'copied' | 'failed'
  const text = codes.join('\n');

  const handleCopy = async () => {
    let result = 'copied';
    try {
      await copyText(text);
    } catch {
      result = 'failed';
    }
    setCopyState(result);
    setTimeout(() => setCopyState(null), result === 'copied' ? 2000 : 3000);
  };

  const handleDownload = () => {
    const blob = new Blob(
      [`NetWorth Tracker backup codes\nEach code can be used once.\n\n${text}\n`],
      { type: 'text/plain' }
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'networth-tracker-backup-codes.txt';
    document.body.appendChild(link); // some browsers ignore click() on a detached anchor
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl w-full max-w-md p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Save your backup codes</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
          Each code can be used once to sign in if you lose your authenticator app. They won't be shown again.
        </p>
        <div className="grid grid-cols-2 gap-2 my-5 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg font-mono text-sm text-gray-900 dark:text-gray-100">
          {codes.map((code) => (
            <span key={code} className="text-center">{code}</span>
          ))}
        </div>
        <div className="flex gap-3 mb-3">
          <button type="button" onClick={handleCopy} autoFocus className="btn-secondary flex-1 flex items-center justify-center gap-2">
            {copyState === 'copied' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            {copyState === 'copied' ? 'Copied' : 'Copy all'}
          </button>
          <button type="button" onClick={handleDownload} className="btn-secondary flex-1 flex items-center justify-center gap-2">
            <Download className="w-4 h-4" />
            Download .txt
          </button>
        </div>
        {copyState === 'failed' && (
          <p role="alert" className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400 mb-3">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            Couldn't copy — use Download .txt instead.
          </p>
        )}
        <button type="button" onClick={onClose} className="btn-primary w-full">
          I've saved these codes
        </button>
      </div>
    </div>
  );
}

export default function Security() {
  const [status, setStatus] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState('');
  const [disableForm, setDisableForm] = useState({ password: '', code: '' });
  const [backupCodes, setBackupCodes] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [secretCopy, setSecretCopy] = useState(null); // null | 'copied' | 'failed'

  const loadStatus = async () => {
    try {
      const res = await twoFactorAPI.status();
      setStatus(res.data);
    } catch (err) {
      setLoadError(errorMessage(err, 'Failed to load security settings'));
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const startSetup = async () => {
    setError('');
    setBusy(true);
    try {
      const res = await twoFactorAPI.setup();
      setSetup(res.data);
      setCode('');
    } catch (err) {
      setError(errorMessage(err, 'Failed to start setup'));
    } finally {
      setBusy(false);
    }
  };

  const cancelSetup = () => {
    setSetup(null);
    setCode('');
    setError('');
  };

  const copySecret = async () => {
    let result = 'copied';
    try {
      await copyText(setup.secret);
    } catch {
      result = 'failed';
    }
    setSecretCopy(result);
    setTimeout(() => setSecretCopy(null), result === 'copied' ? 2000 : 3000);
  };

  const confirmEnable = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const res = await twoFactorAPI.enable(code);
      setSetup(null);
      setCode('');
      setBackupCodes(res.data.backup_codes);
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err, 'Failed to enable two-factor authentication'));
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await twoFactorAPI.disable(disableForm.password, disableForm.code);
      setDisableForm({ password: '', code: '' });
      await loadStatus();
    } catch (err) {
      setError(errorMessage(err, 'Failed to disable two-factor authentication'));
      setDisableForm((prev) => ({ ...prev, code: '' }));
    } finally {
      setBusy(false);
    }
  };

  const lowOnCodes = status?.enabled && status.backup_codes_remaining <= 3;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Security</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-1">Protect your account with two-factor authentication</p>
      </div>

      {loadError && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {loadError}
        </div>
      )}

      {!status && !loadError && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary-600"></div>
        </div>
      )}

      {status && (
        <div className="card max-w-3xl">
          <div className="flex items-start gap-4">
            <div className={`p-3 rounded-xl flex-shrink-0 ${status.enabled
              ? 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400'
              : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}`}
            >
              {status.enabled ? <ShieldCheck className="w-6 h-6" /> : <ShieldOff className="w-6 h-6" />}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Two-factor authentication</h2>
                {status.enabled && (
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400">
                    Enabled
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {status.enabled
                  ? 'Signing in requires a code from your authenticator app or a backup code.'
                  : 'Require a code from an authenticator app (Google Authenticator, Authy, 1Password, ...) in addition to your password when signing in.'}
              </p>
            </div>
          </div>

          {error && (
            <div className="mt-4 flex items-center gap-2 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {!status.enabled && !setup && (
            <button type="button" onClick={startSetup} disabled={busy} className="btn-primary mt-6 disabled:opacity-50">
              Enable two-factor authentication
            </button>
          )}

          {!status.enabled && setup && (
            <div className="mt-6 space-y-5">
              <div className="flex flex-col sm:flex-row gap-6 items-center sm:items-start">
                <div className="p-3 bg-white rounded-lg border border-gray-200 flex-shrink-0">
                  <QRCodeSVG value={setup.otpauth_uri} size={176} bgColor="#ffffff" fgColor="#000000" />
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400 space-y-3 min-w-0 w-full">
                  <p><span className="font-medium text-gray-900 dark:text-white">1.</span> Scan this QR code with your authenticator app.</p>
                  <p>Can't scan it? Enter this key manually:</p>
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 px-3 py-2 rounded-lg break-all">
                      {groupSecret(setup.secret)}
                    </code>
                    <button
                      type="button"
                      onClick={copySecret}
                      className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 flex-shrink-0"
                      title="Copy key"
                    >
                      {secretCopy === 'copied' ? <Check className="w-4 h-4 text-green-600" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </div>
                  {secretCopy === 'failed' && (
                    <p role="alert" className="text-red-600 dark:text-red-400">Copy failed — type the key manually</p>
                  )}
                  <p><span className="font-medium text-gray-900 dark:text-white">2.</span> Enter the 6-digit code the app shows to confirm.</p>
                </div>
              </div>
              <form onSubmit={confirmEnable} className="flex flex-col sm:flex-row gap-3">
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  className="input sm:max-w-[12rem] text-center font-mono tracking-[0.3em]"
                  placeholder="000000"
                  aria-label="Authentication code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  autoFocus
                  required
                />
                <button type="submit" disabled={busy || code.length !== 6} className="btn-primary disabled:opacity-50">
                  Verify &amp; enable
                </button>
                <button type="button" onClick={cancelSetup} className="btn-secondary">
                  Cancel
                </button>
              </form>
            </div>
          )}

          {status.enabled && (
            <div className="mt-6 space-y-5">
              <div className={`flex items-center gap-2 text-sm ${lowOnCodes
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-gray-600 dark:text-gray-400'}`}
              >
                <KeyRound className="w-4 h-4 flex-shrink-0" />
                <span>
                  Backup codes remaining: <strong>{status.backup_codes_remaining}</strong>
                  {lowOnCodes && ' (disable and re-enable 2FA to get a new set)'}
                </span>
              </div>

              <form onSubmit={handleDisable} className="border-t border-gray-100 dark:border-gray-700 pt-5 space-y-4">
                <h3 className="font-medium text-gray-900 dark:text-white">Disable two-factor authentication</h3>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="label" htmlFor="disable-password">Password</label>
                    <input
                      id="disable-password"
                      type="password"
                      autoComplete="current-password"
                      className="input"
                      value={disableForm.password}
                      onChange={(e) => setDisableForm({ ...disableForm, password: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <label className="label" htmlFor="disable-code">Authentication or backup code</label>
                    <input
                      id="disable-code"
                      type="text"
                      autoComplete="one-time-code"
                      className="input font-mono"
                      maxLength={20}
                      value={disableForm.code}
                      onChange={(e) => setDisableForm({ ...disableForm, code: e.target.value })}
                      required
                    />
                  </div>
                </div>
                <button type="submit" disabled={busy} className="btn-danger disabled:opacity-50">
                  Disable 2FA
                </button>
              </form>
            </div>
          )}
        </div>
      )}

      {backupCodes && <BackupCodesModal codes={backupCodes} onClose={() => setBackupCodes(null)} />}
    </div>
  );
}
