import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { useTheme } from '../ThemeContext';
import { usePrivacy } from '../PrivacyContext';
import { exportAPI } from '../api';
import { 
  LayoutDashboard, 
  Wallet, 
  CreditCard, 
  LogOut, 
  Menu,
  X,
  Sun,
  Moon,
  Landmark,
  Shield,
  TrendingUp,
  BarChart3,
  Eye,
  EyeOff,
  Clock,
  Download,
  User
} from 'lucide-react';
import { useState } from 'react';

const formatLastUpdated = (date) => {
  if (!date) return 'Never';
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  }).format(new Date(date));
};

export default function Layout() {
  const { user, logout } = useAuth();
  const { darkMode, toggleDarkMode } = useTheme();
  const { privacyMode, togglePrivacyMode, lastUpdated } = usePrivacy();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const handleExport = async () => {
    try {
      setExporting(true);
      const response = await exportAPI.download();
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `networth_backup_${new Date().toISOString().slice(0,10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
    } finally {
      setExporting(false);
    }
  };

  const navItems = [
    { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
    { to: '/assets', icon: Wallet, label: 'Assets' },
    { to: '/liabilities', icon: CreditCard, label: 'Liabilities' },
    { to: '/equities', icon: BarChart3, label: 'Equities' },
    { to: '/bank-accounts', icon: Landmark, label: 'Bank Accounts' },
    { to: '/insurances', icon: Shield, label: 'Insurances' },
    { to: '/mutual-funds', icon: TrendingUp, label: 'Mutual Funds' },
  ];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex">
      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-30 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-3xl">💰</span>
          <span className="font-bold text-xl text-gray-900 dark:text-white">NetWorth</span>
        </div>
        <div className="flex items-center gap-2">
          <button 
            onClick={togglePrivacyMode}
            className={`p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 ${privacyMode ? 'text-amber-500' : 'text-gray-600 dark:text-gray-300'}`}
            title={privacyMode ? 'Show values' : 'Hide values'}
          >
            {privacyMode ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
          </button>
          <button 
            onClick={toggleDarkMode}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
          >
            {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
          </button>
          <button 
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
          >
            {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transform transition-transform duration-200 ease-in-out
        lg:relative lg:translate-x-0 lg:flex-shrink-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="h-full flex flex-col">
          {/* Logo */}
          <div className="p-6 border-b border-gray-100 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-primary-100 dark:bg-primary-900 rounded-xl flex items-center justify-center">
                  <span className="text-2xl">💰</span>
                </div>
                <div>
                  <h1 className="font-bold text-lg text-gray-900 dark:text-white">NetWorth</h1>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Tracker</p>
                </div>
              </div>
              <button 
                onClick={toggleDarkMode}
                className="hidden lg:flex p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
                title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
              >
                {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
              </button>
            </div>
          </div>

          {/* Privacy Toggle */}
          <div className="px-4 pt-4 pb-2">
            <button
              onClick={togglePrivacyMode}
              className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors duration-150 ${
                privacyMode 
                  ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800' 
                  : 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
              }`}
            >
              {privacyMode ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              <span className="font-medium">{privacyMode ? 'Privacy On' : 'Privacy Off'}</span>
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 pt-2 space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) => `
                  flex items-center gap-3 px-4 py-3 rounded-lg transition-colors duration-150
                  ${isActive 
                    ? 'bg-primary-50 dark:bg-primary-900/50 text-primary-700 dark:text-primary-300' 
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white'}
                `}
              >
                <item.icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </NavLink>
            ))}
          </nav>

          {/* User Section */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700 space-y-3">
            {/* Last Updated */}
            <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <Clock className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" />
              <div className="text-xs text-gray-500 dark:text-gray-400 min-w-0">
                <span className="font-medium">Last updated</span>
                <p className="truncate">{formatLastUpdated(lastUpdated)}</p>
              </div>
            </div>

            {/* User Info */}
            <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
              <div className="w-9 h-9 bg-primary-100 dark:bg-primary-900/50 rounded-full flex items-center justify-center flex-shrink-0">
                <User className="w-4 h-4 text-primary-600 dark:text-primary-400" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm text-gray-900 dark:text-white truncate">{user?.username}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">{user?.email}</p>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={handleExport}
                disabled={exporting}
                className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800 transition-colors duration-150 disabled:opacity-50"
                title="Export data for backup"
              >
                <Download className={`w-4 h-4 ${exporting ? 'animate-bounce' : ''}`} />
                <span>{exporting ? 'Exporting...' : 'Backup'}</span>
              </button>
              <button
                onClick={handleLogout}
                className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/50 border border-red-200 dark:border-red-800 transition-colors duration-150"
              >
                <LogOut className="w-4 h-4" />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="flex-1 min-h-screen pt-16 lg:pt-0">
        <div className="p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
