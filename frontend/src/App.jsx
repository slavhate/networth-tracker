import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './AuthContext';
import { ThemeProvider } from './ThemeContext';
import { PrivacyProvider } from './PrivacyContext';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Assets from './pages/Assets';
import Liabilities from './pages/Liabilities';
import BankAccounts from './pages/BankAccounts';
import Insurances from './pages/Insurances';
import MutualFunds from './pages/MutualFunds';
import Equities from './pages/Equities';
import Security from './pages/Security';
import Layout from './components/Layout';
import Notices from './components/Notices';

// The saved session could not be checked (server unreachable or failing); the token is kept for a retry
function SessionError() {
  const { retrySession, logout } = useAuth();
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="max-w-sm w-full bg-red-50 border border-red-200 text-red-700 px-4 py-4 rounded-lg text-center space-y-3" role="alert">
        <p>Could not reach the server to restore your session.</p>
        <div className="flex gap-2 justify-center">
          <button onClick={retrySession} className="btn-primary">Retry</button>
          <button onClick={logout} className="btn-secondary">Sign out</button>
        </div>
      </div>
    </div>
  );
}

function PrivateRoute({ children }) {
  const { user, loading, sessionError } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (!user && sessionError) return <SessionError />;

  return user ? children : <Navigate to="/login" />;
}

function PublicRoute({ children }) {
  const { user, loading, sessionError } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (!user && sessionError) return <SessionError />;

  return user ? <Navigate to="/" /> : children;
}

function App() {
  return (
    <ThemeProvider>
      <PrivacyProvider>
        <AuthProvider>
          <BrowserRouter>
          <Routes>
            <Route path="/login" element={
              <PublicRoute>
                <Login />
              </PublicRoute>
            } />
            <Route path="/register" element={
              <PublicRoute>
                <Register />
              </PublicRoute>
            } />
            <Route path="/" element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }>
              <Route index element={<Dashboard />} />
              <Route path="assets" element={<Assets />} />
              <Route path="liabilities" element={<Liabilities />} />
              <Route path="equities" element={<Equities />} />
              <Route path="bank-accounts" element={<BankAccounts />} />
              <Route path="insurances" element={<Insurances />} />
              <Route path="mutual-funds" element={<MutualFunds />} />
              <Route path="security" element={<Security />} />
            </Route>
          </Routes>
          </BrowserRouter>
          <Notices />
        </AuthProvider>
      </PrivacyProvider>
    </ThemeProvider>
  );
}

export default App;
