import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Eye, EyeOff } from 'lucide-react';

const SESSION_EXPIRED = 'Invalid or expired login session';

const errorDetail = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};

export default function Login() {
  const [formData, setFormData] = useState({ username: '', password: '' });
  const [step, setStep] = useState('credentials');
  const [mfaToken, setMfaToken] = useState(null);
  const [code, setCode] = useState('');
  const [useBackupCode, setUseBackupCode] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const { login, completeMfaLogin } = useAuth();
  const navigate = useNavigate();

  const backToCredentials = (message = '') => {
    setStep('credentials');
    setMfaToken(null);
    setCode('');
    setUseBackupCode(false);
    setFormData((prev) => ({ ...prev, password: '' }));
    setError(message);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const result = await login(formData);
      if (result.mfaRequired) {
        setMfaToken(result.mfaToken);
        setCode('');
        setStep('code');
      } else {
        navigate('/');
      }
    } catch (err) {
      setError(errorDetail(err, 'Login failed. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  const handleCodeSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await completeMfaLogin(mfaToken, code);
      navigate('/');
    } catch (err) {
      const detail = errorDetail(err, 'Verification failed. Please try again.');
      if (detail === SESSION_EXPIRED) {
        backToCredentials('Login session expired, please sign in again');
      } else {
        setError(detail);
        setCode('');
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleBackupCode = () => {
    setUseBackupCode(!useBackupCode);
    setCode('');
    setError('');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-primary-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <img src="/logo.png" alt="NetWorth Tracker" className="inline-block w-16 h-16 rounded-2xl shadow-lg mb-4" />
          <h1 className="text-2xl font-bold text-gray-900">
            {step === 'code' ? 'Two-factor authentication' : 'Welcome Back'}
          </h1>
          <p className="text-gray-600 mt-1">
            {step === 'code'
              ? (useBackupCode ? 'Enter one of your backup codes' : 'Enter the 6-digit code from your authenticator app')
              : 'Sign in to your Net Worth Tracker'}
          </p>
        </div>

        {/* Form */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          {step === 'credentials' ? (
            <form onSubmit={handleSubmit} className="space-y-5">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label">Username</label>
                <input
                  type="text"
                  className="input"
                  placeholder="Enter your username"
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    className="input pr-12"
                    placeholder="Enter your password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    required
                  />
                  <button
                    type="button"
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Signing in...' : 'Sign In'}
              </button>
            </form>
          ) : (
            <form onSubmit={handleCodeSubmit} className="space-y-5">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label" htmlFor="mfa-code">
                  {useBackupCode ? 'Backup code' : 'Authentication code'}
                </label>
                {useBackupCode ? (
                  <input
                    key="backup"
                    id="mfa-code"
                    type="text"
                    className="input font-mono tracking-wider"
                    placeholder="xxxx-xxxx"
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    maxLength={20}
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    autoFocus
                    required
                  />
                ) : (
                  <input
                    key="totp"
                    id="mfa-code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]{6}"
                    className="input text-center text-2xl font-mono tracking-[0.5em]"
                    placeholder="000000"
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    autoFocus
                    required
                  />
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-3 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Verifying...' : 'Verify'}
              </button>

              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-primary-600 hover:text-primary-700 font-medium"
                  onClick={toggleBackupCode}
                >
                  {useBackupCode ? 'Use authenticator app' : 'Use a backup code instead'}
                </button>
                <button
                  type="button"
                  className="text-gray-600 hover:text-gray-800"
                  onClick={() => backToCredentials()}
                >
                  Back to sign in
                </button>
              </div>
            </form>
          )}

          {step === 'credentials' && (
            <div className="mt-6 text-center">
              <p className="text-gray-600">
                Don't have an account?{' '}
                <Link to="/register" className="text-primary-600 hover:text-primary-700 font-medium">
                  Sign up
                </Link>
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
