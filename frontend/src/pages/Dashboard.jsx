import { useState, useEffect } from 'react';
import { dashboardAPI, goalAPI } from '../api';
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
  X
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
  Bar
} from 'recharts';

const COLORS = ['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatCategoryName = (name) => {
  return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
};

export default function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [goal, setGoal] = useState(null);
  const [goalModalOpen, setGoalModalOpen] = useState(false);
  const [goalInput, setGoalInput] = useState('');
  const [goalSaving, setGoalSaving] = useState(false);

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
    } catch (err) {
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const handleSnapshot = async () => {
    try {
      setSnapshotLoading(true);
      await dashboardAPI.createSnapshot();
      await fetchDashboard();
    } catch (err) {
      setError('Failed to create snapshot');
    } finally {
      setSnapshotLoading(false);
    }
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

  // Prepare chart data
  const assetChartData = Object.entries(metrics?.assets_by_category || {}).map(([name, value]) => ({
    name: formatCategoryName(name),
    value
  }));

  const liabilityChartData = Object.entries(metrics?.liabilities_by_category || {}).map(([name, value]) => ({
    name: formatCategoryName(name),
    value
  }));

  const historyData = [...(metrics?.net_worth_history || [])].reverse().map((snapshot) => ({
    date: new Date(snapshot.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    netWorth: snapshot.net_worth,
    assets: snapshot.total_assets,
    liabilities: snapshot.total_liabilities
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Track your financial health</p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={fetchDashboard}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button 
            onClick={handleSnapshot}
            disabled={snapshotLoading}
            className="btn-primary flex items-center gap-2"
          >
            <Camera className="w-4 h-4" />
            {snapshotLoading ? 'Saving...' : 'Save Snapshot'}
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Net Worth */}
        <div className={`stat-card border-l-4 ${netWorthPositive ? 'border-l-green-500' : 'border-l-red-500'}`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Net Worth</p>
              <p className={`text-2xl font-bold mt-1 ${netWorthPositive ? 'text-green-600' : 'text-red-600'}`}>
                {formatCurrency(metrics?.net_worth || 0)}
              </p>
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
                {formatCurrency(metrics?.total_assets || 0)}
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
                {formatCurrency(metrics?.total_liabilities || 0)}
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
                {metrics?.debt_to_asset_ratio || 0}%
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

      {/* Goal Edit Modal */}
      {goalModalOpen && (
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
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Asset Allocation */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <PieChart className="w-5 h-5 text-primary-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Asset Allocation</h2>
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
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
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
                  <XAxis type="number" tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`} />
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
                <YAxis tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`} />
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
              <p className="text-sm mt-1">Click "Save Snapshot" to start tracking your progress over time.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
