import { useState, useEffect } from 'react';
import { mutualFundsAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  TrendingUp,
  TrendingDown,
  BarChart3,
  LineChart,
  PieChart,
  Target,
  Wallet,
  RefreshCw,
  Info
} from 'lucide-react';

const FUND_CATEGORIES = [
  { value: 'equity', label: 'Equity', icon: TrendingUp, color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400' },
  { value: 'debt', label: 'Debt', icon: LineChart, color: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400' },
  { value: 'hybrid', label: 'Hybrid', icon: PieChart, color: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-400' },
  { value: 'index', label: 'Index Fund', icon: BarChart3, color: 'bg-orange-100 text-orange-600 dark:bg-orange-900/50 dark:text-orange-400' },
  { value: 'elss', label: 'ELSS (Tax Saver)', icon: Target, color: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400' },
  { value: 'liquid', label: 'Liquid Fund', icon: Wallet, color: 'bg-teal-100 text-teal-600 dark:bg-teal-900/50 dark:text-teal-400' },
];

const getCategoryInfo = (value) => FUND_CATEGORIES.find(c => c.value === value) || FUND_CATEGORIES[0];

const formatCurrencyRaw = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatPercent = (value) => {
  if (value === null || value === undefined) return '-';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};

export default function MutualFunds() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [funds, setFunds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingFund, setEditingFund] = useState(null);
  const [formData, setFormData] = useState({
    fund_name: '',
    amc: '',
    category: 'equity',
    invested_amount: '',
    current_value: '',
    units: '',
    avg_nav: '',
    current_nav: '',
    folio_number: ''
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchFunds = async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const response = await mutualFundsAPI.getAll(refresh);
      setFunds(response.data);
      updateLastUpdated();
    } catch (err) {
      setError('Failed to load mutual funds');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchFunds();
  }, []);

  const handleRefreshNav = () => {
    fetchFunds(true);
  };

  const openModal = (fund = null) => {
    if (fund) {
      setEditingFund(fund);
      setFormData({
        fund_name: fund.fund_name,
        amc: fund.amc,
        category: fund.category,
        invested_amount: fund.invested_amount.toString(),
        current_value: fund.current_value?.toString() || '',
        units: fund.units?.toString() || '',
        avg_nav: fund.avg_nav?.toString() || '',
        current_nav: fund.current_nav?.toString() || '',
        folio_number: fund.folio_number || ''
      });
    } else {
      setEditingFund(null);
      setFormData({
        fund_name: '',
        amc: '',
        category: 'equity',
        invested_amount: '',
        current_value: '',
        units: '',
        avg_nav: '',
        current_nav: '',
        folio_number: ''
      });
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingFund(null);
    setFormData({
      fund_name: '',
      amc: '',
      category: 'equity',
      invested_amount: '',
      current_value: '',
      units: '',
      avg_nav: '',
      current_nav: '',
      folio_number: ''
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = {
        fund_name: formData.fund_name,
        amc: formData.amc,
        category: formData.category,
        invested_amount: parseFloat(formData.invested_amount),
        current_value: formData.current_value ? parseFloat(formData.current_value) : null,
        units: formData.units ? parseFloat(formData.units) : 0,
        avg_nav: formData.avg_nav ? parseFloat(formData.avg_nav) : 0,
        current_nav: formData.current_nav ? parseFloat(formData.current_nav) : null,
        folio_number: formData.folio_number || null
      };

      if (editingFund) {
        await mutualFundsAPI.update(editingFund.id, data);
      } else {
        await mutualFundsAPI.create(data);
      }

      closeModal();
      fetchFunds();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save mutual fund');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this mutual fund?')) return;

    try {
      await mutualFundsAPI.delete(id);
      fetchFunds();
    } catch (err) {
      setError('Failed to delete mutual fund');
    }
  };

  const formatCurrency = (value) => {
    if (privacyMode) return '₹ ••••••';
    return formatCurrencyRaw(value);
  };

  const totalInvested = funds.reduce((sum, fund) => sum + fund.invested_amount, 0);
  const totalCurrentValue = funds.reduce((sum, fund) => sum + (fund.current_value || 0), 0);
  const totalReturns = totalCurrentValue - totalInvested;
  const overallReturnPercent = totalInvested > 0 ? ((totalCurrentValue - totalInvested) / totalInvested) * 100 : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Mutual Funds</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Track your mutual fund investments</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleRefreshNav} 
            disabled={refreshing}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing...' : 'Refresh NAV'}
          </button>
          <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Fund
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-blue-100 font-medium">Invested</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(totalInvested)}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <Wallet className="w-5 h-5" />
            </div>
          </div>
        </div>

        <div className="card bg-gradient-to-r from-green-500 to-green-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 font-medium">Current Value</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(totalCurrentValue)}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <BarChart3 className="w-5 h-5" />
            </div>
          </div>
        </div>

        <div className={`card ${totalReturns >= 0 ? 'bg-gradient-to-r from-emerald-500 to-emerald-600' : 'bg-gradient-to-r from-red-500 to-red-600'} text-white`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`${totalReturns >= 0 ? 'text-emerald-100' : 'text-red-100'} font-medium`}>Returns</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(Math.abs(totalReturns))}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              {totalReturns >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
            </div>
          </div>
        </div>

        <div className={`card ${overallReturnPercent >= 0 ? 'bg-gradient-to-r from-purple-500 to-purple-600' : 'bg-gradient-to-r from-orange-500 to-orange-600'} text-white`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`${overallReturnPercent >= 0 ? 'text-purple-100' : 'text-orange-100'} font-medium`}>Return %</p>
              <p className="text-xl font-bold mt-1">{formatPercent(overallReturnPercent)}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <Target className="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>

      {/* Funds List */}
      {funds.length === 0 ? (
        <div className="card text-center py-12">
          <TrendingUp className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">No mutual funds yet</h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Add your mutual fund investments to track performance</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Your First Fund
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {funds.map((fund) => {
            const categoryInfo = getCategoryInfo(fund.category);
            const CategoryIcon = categoryInfo.icon;
            const currentVal = fund.current_value || 0;
            const returnAmount = currentVal - fund.invested_amount;
            const returnPercent = fund.invested_amount > 0 
              ? ((currentVal - fund.invested_amount) / fund.invested_amount) * 100 
              : 0;
            const isPositive = returnAmount >= 0;
            
            return (
              <div key={fund.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-start gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${categoryInfo.color}`}>
                    <CategoryIcon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{fund.fund_name}</h3>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500 dark:text-gray-400 mt-1">
                      <span>{fund.amc}</span>
                      <span>•</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${categoryInfo.color}`}>{categoryInfo.label}</span>
                      {fund.folio_number && (
                        <>
                          <span>•</span>
                          <span>Folio: {fund.folio_number}</span>
                        </>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm mt-2">
                      <span className="text-gray-500 dark:text-gray-400">
                        Invested: <span className="text-gray-900 dark:text-white font-medium">{formatCurrency(fund.invested_amount)}</span>
                      </span>
                      {fund.units > 0 && (
                        <span className="text-gray-500 dark:text-gray-400">
                          Units: <span className="text-gray-900 dark:text-white font-medium">{fund.units.toFixed(3)}</span>
                        </span>
                      )}
                      {fund.avg_nav > 0 && (
                        <span className="text-gray-500 dark:text-gray-400">
                          Avg NAV: <span className="text-gray-900 dark:text-white font-medium">₹{fund.avg_nav.toFixed(2)}</span>
                        </span>
                      )}
                      {fund.current_nav > 0 && (
                        <span className="text-gray-500 dark:text-gray-400">
                          Current NAV: <span className="text-green-600 dark:text-green-400 font-medium">₹{fund.current_nav.toFixed(2)}</span>
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(currentVal)}</p>
                    <p className={`text-sm font-medium flex items-center justify-end gap-1 ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                      {formatCurrency(Math.abs(returnAmount))} ({formatPercent(returnPercent)})
                    </p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => openModal(fund)}
                      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(fund.id)}
                      className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingFund ? 'Edit Mutual Fund' : 'Add New Mutual Fund'}
              </h2>
              <button onClick={closeModal} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {error && (
                <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label">Fund Name</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., HDFC Flexi Cap Fund Direct Plan Growth"
                  value={formData.fund_name}
                  onChange={(e) => setFormData({ ...formData, fund_name: e.target.value })}
                  required
                />
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1 flex items-center gap-1">
                  <Info className="w-3 h-3" />
                  Enter exact fund name (with Direct/Regular & Growth/Dividend) for accurate NAV fetching
                </p>
              </div>

              <div>
                <label className="label">AMC (Fund House)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., SBI Mutual Fund"
                  value={formData.amc}
                  onChange={(e) => setFormData({ ...formData, amc: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Category</label>
                <select
                  className="input"
                  value={formData.category}
                  onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                >
                  {FUND_CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Invested Amount (₹)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0"
                    min="0"
                    step="1"
                    value={formData.invested_amount}
                    onChange={(e) => setFormData({ ...formData, invested_amount: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="label">Current Value (₹) <span className="text-gray-400 font-normal">- Optional</span></label>
                  <input
                    type="number"
                    className="input"
                    placeholder="Auto-calculated from Units × Current NAV"
                    min="0"
                    step="1"
                    value={formData.current_value}
                    onChange={(e) => setFormData({ ...formData, current_value: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Units</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0.000"
                    min="0"
                    step="0.001"
                    value={formData.units}
                    onChange={(e) => setFormData({ ...formData, units: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">Avg. NAV (Purchase NAV)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    value={formData.avg_nav}
                    onChange={(e) => setFormData({ ...formData, avg_nav: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <label className="label">Current NAV <span className="text-gray-400 font-normal">- Optional (auto-fetched)</span></label>
                <input
                  type="number"
                  className="input"
                  placeholder="Leave empty to fetch from internet"
                  min="0"
                  step="0.01"
                  value={formData.current_nav}
                  onChange={(e) => setFormData({ ...formData, current_nav: e.target.value })}
                />
              </div>

              <div>
                <label className="label">Folio Number (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="Enter folio number"
                  value={formData.folio_number}
                  onChange={(e) => setFormData({ ...formData, folio_number: e.target.value })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingFund ? 'Update' : 'Add Fund')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
