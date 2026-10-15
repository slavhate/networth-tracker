import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { dashboardAPI, goalAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import AnimatedNumber from '../components/AnimatedNumber';
import SnapshotDialog from '../components/SnapshotDialog';
import { formatDate, formatMonthYear, todayIso } from '../utils/dates';
import { categoryLabel } from '../utils/assetCategories';
import { ASSET_CLASSES } from '../utils/assetClasses';
import { snapshotFrequency } from '../utils/snapshotFrequencies';
import { 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  CreditCard,
  PieChart,
  BarChart3,
  RefreshCw,
  Camera,
  Target,
  Edit2,
  X,
  CalendarClock,
  Layers
} from 'lucide-react';
import {
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  AreaChart,
  Area
} from 'recharts';

const COLORS = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

const formatCurrencyRaw = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

// The x-axis label of a snapshot on the history charts
const snapshotDateLabel = (timestamp) =>
  new Date(timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' });

export default function Dashboard() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [snapshotDialogOpen, setSnapshotDialogOpen] = useState(false);
  const [goal, setGoal] = useState(null);
  const [goalModalOpen, setGoalModalOpen] = useState(false);
  const [goalInput, setGoalInput] = useState('');
  const [goalSaving, setGoalSaving] = useState(false);
  const [allocationView, setAllocationView] = useState(() => {
    try {
      return localStorage.getItem('allocationView') === 'holding' ? 'holding' : 'class';
    } catch {
      return 'class';
    }
  });

  const changeAllocationView = (view) => {
    setAllocationView(view);
    try {
      localStorage.setItem('allocationView', view);
    } catch {
      // storage unavailable (private mode, blocked) - the choice just won't persist
    }
  };

  const fetchDashboard = async () => {
    try {
      setLoading(true);
      const [metricsResponse, goalResponse] = await Promise.all([
        dashboardAPI.getMetrics(),
        goalAPI.get()
      ]);
      setMetrics(metricsResponse.data);
      setGoal(goalResponse.data);
      setError('');
      updateLastUpdated();
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const closeSnapshotDialog = () => setSnapshotDialogOpen(false);

  const snapshotFrequencyChanged = (settings) => {
    setMetrics((current) => ({
      ...current,
      snapshot_frequency: settings.frequency,
      next_snapshot_on: settings.next_snapshot_on
    }));
  };

  // A manual snapshot adds a history point and can move the next automatic date
  const snapshotSaved = () => {
    setSnapshotDialogOpen(false);
    fetchDashboard();
  };

  const openGoalModal = () => {
    setGoalInput(goal?.target_amount ? (goal.target_amount / 10000000).toString() : '10');
    setGoalModalOpen(true);
  };

  const handleGoalSave = async () => {
    try {
      setGoalSaving(true);
      const targetAmount = parseFloat(goalInput) * 10000000; // Convert crores to rupees
      const response = await goalAPI.update({ target_amount: targetAmount });
      setGoal(response.data);
      setGoalModalOpen(false);
    } catch (err) {
      setError('Failed to update goal');
    } finally {
      setGoalSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
        {error}
      </div>
    );
  }

  const netWorthPositive = metrics?.net_worth >= 0;

  const autoSnapshot = snapshotFrequency(metrics?.snapshot_frequency);

  // Format currency with privacy mode support
  const formatCurrency = (value) => {
    if (privacyMode) return '₹ ••••••';
    return formatCurrencyRaw(value);
  };

  // Value-axis tick, e.g. ₹250k; hidden in privacy mode like every other amount
  const formatAxisAmount = (value) => (privacyMode ? '••' : `₹${(value / 1000).toFixed(0)}k`);

  // Latest snapshot from an earlier calendar month (history is newest first)
  const thisMonth = todayIso().slice(0, 7);
  const previousSnapshot = (metrics?.net_worth_history || []).find((s) => s.timestamp.slice(0, 7) < thisMonth);
  const netWorthChange = previousSnapshot ? metrics.net_worth - previousSnapshot.net_worth : null;
  const netWorthChangePercent = previousSnapshot && previousSnapshot.net_worth !== 0
    ? (netWorthChange / Math.abs(previousSnapshot.net_worth)) * 100 : null;

  // Prepare chart data
  const assetChartData = allocationView === 'class'
    ? ASSET_CLASSES
        .filter((c) => (metrics?.assets_by_class?.[c.key] || 0) > 0)
        .map((c) => ({ name: c.label, value: metrics.assets_by_class[c.key], color: c.color }))
    : Object.entries(metrics?.assets_by_category || {}).map(([name, value], index) => ({
        name: categoryLabel(name),
        value,
        color: COLORS[index % COLORS.length]
      }));

  const liabilityChartData = Object.entries(metrics?.liabilities_by_category || {}).map(([name, value]) => ({
    name: categoryLabel(name),
    value
  }));

  const historyData = [...(metrics?.net_worth_history || [])].reverse().map((snapshot) => ({
    date: snapshotDateLabel(snapshot.timestamp),
    netWorth: snapshot.net_worth,
    assets: snapshot.total_assets,
    liabilities: snapshot.total_liabilities
  }));

  // Snapshots without a breakdown (older ones) are skipped; unknown class keys are ignored
  const allocationHistory = [...(metrics?.net_worth_history || [])].reverse()
    .filter((s) => s.assets_by_class)
    .map((s) => ({
      date: snapshotDateLabel(s.timestamp),
      ...Object.fromEntries(ASSET_CLASSES.map((c) => [c.key, s.assets_by_class[c.key] || 0])),
    }));
  // Only classes that appear in at least one plotted snapshot get an area (and a legend entry)
  const plottedClasses = ASSET_CLASSES.filter((c) => allocationHistory.some((point) => point[c.key] > 0));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Track your financial health</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={fetchDashboard}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={() => setSnapshotDialogOpen(true)}
            aria-haspopup="dialog"
            className="btn-primary flex items-center gap-2"
          >
            <Camera className="w-4 h-4" />
            Save Snapshot
          </button>
        </div>
      </div>

      {snapshotDialogOpen && (
        <SnapshotDialog
          frequency={autoSnapshot.value}
          nextSnapshotOn={metrics?.next_snapshot_on}
          lastSnapshotOn={metrics?.net_worth_history?.[0]?.timestamp.slice(0, 10)}
          onClose={closeSnapshotDialog}
          onFrequencyChanged={snapshotFrequencyChanged}
          onSaved={snapshotSaved}
        />
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Net Worth */}
        <div className={`stat-card border-l-4 ${netWorthPositive ? 'border-l-green-500' : 'border-l-red-500'}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Net Worth</p>
              <p className={`text-2xl font-bold mt-1 ${netWorthPositive ? 'text-green-600' : 'text-red-600'}`}>
                <AnimatedNumber 
                  value={metrics?.net_worth || 0} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
              {netWorthChange != null && (
                <p className={`text-xs mt-1 ${netWorthChange >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {netWorthChange >= 0 ? '▲' : '▼'} {formatCurrency(Math.abs(netWorthChange))}
                  {netWorthChangePercent != null && <> ({privacyMode ? '••' : `${Math.abs(netWorthChangePercent).toFixed(1)}%`})</>} since {formatMonthYear(previousSnapshot.timestamp.slice(0, 10))}
                </p>
              )}
            </div>
            <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${netWorthPositive ? 'bg-green-100' : 'bg-red-100'}`}>
              {netWorthPositive ? (
                <TrendingUp className="w-6 h-6 text-green-600" />
              ) : (
                <TrendingDown className="w-6 h-6 text-red-600" />
              )}
            </div>
          </div>
        </div>

        {/* Total Assets */}
        <div className="stat-card border-l-4 border-l-primary-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Assets</p>
              <p className="text-2xl font-bold mt-1 text-gray-900 dark:text-white">
                <AnimatedNumber 
                  value={metrics?.total_assets || 0} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{metrics?.asset_count || 0} assets</p>
            </div>
            <div className="w-12 h-12 bg-primary-100 dark:bg-primary-900/50 rounded-xl flex items-center justify-center">
              <Wallet className="w-6 h-6 text-primary-600 dark:text-primary-400" />
            </div>
          </div>
        </div>

        {/* Total Liabilities */}
        <div className="stat-card border-l-4 border-l-orange-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Liabilities</p>
              <p className="text-2xl font-bold mt-1 text-gray-900 dark:text-white">
                <AnimatedNumber 
                  value={metrics?.total_liabilities || 0} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{metrics?.liability_count || 0} liabilities</p>
            </div>
            <div className="w-12 h-12 bg-orange-100 dark:bg-orange-900/50 rounded-xl flex items-center justify-center">
              <CreditCard className="w-6 h-6 text-orange-600 dark:text-orange-400" />
            </div>
          </div>
        </div>

        {/* Debt-to-Asset Ratio */}
        <div className="stat-card border-l-4 border-l-purple-500">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Debt-to-Asset Ratio</p>
              <p className="text-2xl font-bold mt-1 text-gray-900 dark:text-white">
                <AnimatedNumber 
                  value={metrics?.debt_to_asset_ratio || 0} 
                  formatter={(v) => `${v.toFixed(1)}%`}
                />
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                {(metrics?.debt_to_asset_ratio || 0) < 50 ? 'Healthy' : 'High'}
              </p>
            </div>
            <div className="w-12 h-12 bg-purple-100 dark:bg-purple-900/50 rounded-xl flex items-center justify-center">
              <BarChart3 className="w-6 h-6 text-purple-600 dark:text-purple-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Net Worth Goal Card */}
      {(() => {
        const goalTarget = goal?.target_amount || 100000000;
        const currentNetWorth = Math.max(0, metrics?.net_worth || 0);
        const progress = Math.min((currentNetWorth / goalTarget) * 100, 100);
        const remaining = Math.max(0, goalTarget - currentNetWorth);
        const goalInCrores = (goalTarget / 10000000).toFixed(1);
        
        // Milestones
        const milestones = [
          { percent: 25, label: '25%' },
          { percent: 50, label: '50%' },
          { percent: 75, label: '75%' },
          { percent: 100, label: '100%' }
        ];
        const nextMilestone = milestones.find(m => m.percent > progress) || milestones[milestones.length - 1];
        const achievedMilestones = milestones.filter(m => progress >= m.percent).length;
        
        return (
          <div className="card bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white px-6 py-5">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
              {/* Left: Goal Info */}
              <div className="lg:col-span-3 flex items-center gap-4">
                <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center shrink-0">
                  <Target className="w-8 h-8" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-lg">{goal?.name || 'Net Worth Goal'}</h3>
                    <button
                      onClick={openGoalModal}
                      className="p-1.5 bg-white/20 rounded-lg hover:bg-white/30 transition-colors"
                      title="Edit Goal"
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-white/80 text-sm">Target: ₹{goalInCrores} Crore</p>
                  <p className="text-white/60 text-xs mt-0.5">
                    {achievedMilestones > 0 ? `${achievedMilestones} milestone${achievedMilestones > 1 ? 's' : ''} achieved` : 'Start your journey'}
                  </p>
                </div>
              </div>

              {/* Center: Progress Bar with Milestones */}
              <div className="lg:col-span-6">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-white/80">Progress</span>
                  <span className="font-bold text-lg">{progress.toFixed(1)}%</span>
                </div>
                {/* Progress bar with milestone markers */}
                <div className="relative">
                  <div className="w-full bg-white/20 rounded-full h-5 overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-white/90 to-white rounded-full transition-all duration-500 ease-out relative"
                      style={{ width: `${progress}%` }}
                    >
                      {progress > 5 && (
                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-purple-600 text-xs font-bold">
                          {formatCurrency(currentNetWorth)}
                        </span>
                      )}
                    </div>
                  </div>
                  {/* Milestone markers */}
                  <div className="absolute top-0 left-0 right-0 h-5 pointer-events-none">
                    {milestones.map((m) => (
                      <div 
                        key={m.percent}
                        className="absolute top-0 h-full flex flex-col items-center"
                        style={{ left: `${m.percent}%`, transform: 'translateX(-50%)' }}
                      >
                        <div className={`w-1 h-full ${progress >= m.percent ? 'bg-white/60' : 'bg-white/30'}`} />
                      </div>
                    ))}
                  </div>
                </div>
                {/* Milestone labels */}
                <div className="relative mt-1.5">
                  {milestones.map((m) => (
                    <span 
                      key={m.percent}
                      className={`absolute text-xs transform -translate-x-1/2 ${progress >= m.percent ? 'text-white font-medium' : 'text-white/50'}`}
                      style={{ left: `${m.percent}%` }}
                    >
                      {m.label}
                    </span>
                  ))}
                </div>
              </div>

              {/* Right: Stats */}
              <div className="lg:col-span-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <p className="text-white/70 text-xs uppercase tracking-wide">Current</p>
                    <p className="font-bold text-sm mt-0.5">{formatCurrency(currentNetWorth)}</p>
                  </div>
                  <div className="bg-white/10 rounded-xl p-3 text-center">
                    <p className="text-white/70 text-xs uppercase tracking-wide">Remaining</p>
                    <p className="font-bold text-sm mt-0.5">{formatCurrency(remaining)}</p>
                  </div>
                </div>
                {progress < 100 && (
                  <p className="text-white/60 text-xs text-center mt-2">
                    Next milestone: <span className="text-white font-medium">{nextMilestone.label}</span> ({formatCurrency(goalTarget * nextMilestone.percent / 100)})
                  </p>
                )}
                {progress >= 100 && (
                  <p className="text-white text-xs text-center mt-2 font-medium">
                    Goal Achieved! Set a new target.
                  </p>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Goal Edit Modal, on <body> so the space-y margin can't shift the fixed overlay */}
      {goalModalOpen && createPortal(
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-sm">
            <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Set Net Worth Goal</h2>
              <button onClick={() => setGoalModalOpen(false)} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="label">Target Amount (in Crores ₹)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="e.g., 10"
                  min="0.1"
                  step="0.1"
                  value={goalInput}
                  onChange={(e) => setGoalInput(e.target.value)}
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  = {formatCurrency(parseFloat(goalInput || 0) * 10000000)}
                </p>
              </div>
              <div className="flex gap-3 pt-4">
                <button onClick={() => setGoalModalOpen(false)} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button onClick={handleGoalSave} disabled={goalSaving || !goalInput} className="btn-primary flex-1">
                  {goalSaving ? 'Saving...' : 'Save Goal'}
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Deposits maturing */}
      {metrics?.maturities?.length > 0 && (
        <div className="card border-l-4 border-l-amber-500">
          <div className="flex items-center gap-2 mb-3">
            <CalendarClock className="w-5 h-5 text-amber-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Deposits maturing</h2>
          </div>
          <ul className="space-y-2">
            {metrics.maturities.map((m) => {
              const label = `${m.bank_name} ${m.account_type.toUpperCase()}`;
              return (
                <li key={m.id} className="text-sm">
                  {m.days_to_maturity <= 0 ? (
                    <span className="text-red-600 dark:text-red-400 font-medium">
                      {label} matured on {formatDate(m.maturity_date)} — update or renew it
                    </span>
                  ) : (
                    <span className="text-gray-700 dark:text-gray-300">
                      {label} matures in {m.days_to_maturity} day{m.days_to_maturity === 1 ? '' : 's'}
                      {m.maturity_value != null && <> ({formatCurrency(m.maturity_value)})</>}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Asset Allocation */}
        <div className="card">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <PieChart className="w-5 h-5 text-primary-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Asset Allocation</h2>
            </div>
            <div className="inline-flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-600 p-0.5">
              {[
                { view: 'class', label: 'By asset class' },
                { view: 'holding', label: 'By holding' }
              ].map(({ view, label }) => (
                <button
                  key={view}
                  type="button"
                  onClick={() => changeAllocationView(view)}
                  aria-pressed={allocationView === view}
                  className={`text-xs px-2.5 py-1 rounded-md ${
                    allocationView === view
                      ? 'bg-primary-600 text-white'
                      : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {assetChartData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <RechartsPieChart>
                  <Pie
                    data={assetChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={2}
                    dataKey="value"
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    labelLine={false}
                  >
                    {assetChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => formatCurrency(value)} />
                </RechartsPieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-400">
              <p>No assets yet. Add some to see the breakdown.</p>
            </div>
          )}
        </div>

        {/* Liability Breakdown */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-5 h-5 text-orange-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Liability Breakdown</h2>
          </div>
          {liabilityChartData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={liabilityChartData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
                  <XAxis type="number" tickFormatter={formatAxisAmount} />
                  <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value) => formatCurrency(value)} />
                  <Bar dataKey="value" fill="#f97316" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-64 flex items-center justify-center text-gray-400">
              <p>No liabilities yet. That's great!</p>
            </div>
          )}
        </div>
      </div>

      {/* Net Worth History */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-5 h-5 text-green-600" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Net Worth History</h2>
        </div>
        {historyData.length > 0 ? (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={historyData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={formatAxisAmount} />
                <Tooltip formatter={(value) => formatCurrency(value)} />
                <Legend />
                <Line
                  type="monotone" 
                  dataKey="assets" 
                  stroke="#0ea5e9" 
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name="Assets"
                />
                <Line 
                  type="monotone" 
                  dataKey="liabilities" 
                  stroke="#f97316" 
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name="Liabilities"
                />
                <Line 
                  type="monotone" 
                  dataKey="netWorth" 
                  stroke="#22c55e" 
                  strokeWidth={3}
                  dot={{ r: 5 }}
                  name="Net Worth"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-72 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <p>No history yet.</p>
              <p className="text-sm mt-1">A snapshot is saved automatically {autoSnapshot.phrase} when you open the dashboard; use Save Snapshot to add one now or change how often.</p>
            </div>
          </div>
        )}
      </div>

      {/* Allocation History */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-primary-600" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Allocation History</h2>
        </div>
        {allocationHistory.length >= 2 ? (
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={allocationHistory}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tickFormatter={formatAxisAmount} />
                <Tooltip formatter={(value) => formatCurrency(value)} />
                <Legend />
                {plottedClasses.map((c) => (
                  <Area
                    key={c.key}
                    type="monotone"
                    dataKey={c.key}
                    name={c.label}
                    stackId="1"
                    stroke={c.color}
                    fill={c.color}
                    fillOpacity={0.6}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-72 flex items-center justify-center text-gray-400">
            <p className="text-center">Allocation history appears once two snapshots have a breakdown.</p>
          </div>
        )}
      </div>
    </div>
  );
}
