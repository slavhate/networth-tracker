import { useState, useEffect, useRef } from 'react';
import { mutualFundsAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import AnimatedNumber from '../components/AnimatedNumber';
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
import { errorMessage } from '../utils/errors';
import { todayIso, formatDate } from '../utils/dates';

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

// A SIP amount keeps its paise (₹2,500.50); whole rupees show without decimals
const formatSipAmount = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
};

const emptyForm = () => ({
  fund_name: '',
  amc: '',
  category: 'equity',
  invested_amount: '',
  current_value: '',
  units: '',
  current_nav: '',
  folio_number: '',
  sip_amount: '',
  sip_frequency: 'monthly',
  sip_day: '',
  sip_start_date: '',
  sip_end_date: '',
  holdings_date: todayIso()
});

export default function MutualFunds() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [funds, setFunds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingFund, setEditingFund] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  // The API's current value for a SIP fund includes its installments, so an edit sends it only once the user types one;
  // otherwise it is left out and the stored value stands. (A change to the SIP's amount, frequency or day is applied
  // from today by the server, which folds the installments so far into the units and invested amount.)
  const [currentValueTouched, setCurrentValueTouched] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const backgroundRefresh = useRef(false);
  const openFundId = useRef(null); // the fund the edit form is open on, read by the background refresh

  const fetchFunds = async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const response = await mutualFundsAPI.getAll(refresh);
      setFunds(response.data);
      if (!refresh) refreshStaleSips(response.data);
      updateLastUpdated();
    } catch (err) {
      setError('Failed to load mutual funds');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // SIP funds not priced today are refreshed one at a time after the list loads, so their installments count at the
  // NAV of their day; failures are quiet and the card keeps what it showed. A response is dropped while the edit form
  // is open on that fund, or when the copy on screen was saved after it (an edit that landed during the refresh).
  const refreshStaleSips = async (list) => {
    if (backgroundRefresh.current) return;
    backgroundRefresh.current = true;
    try {
      for (const fund of list) {
        if (!(fund.sip_amount > 0) || fund.sip_priced_through === todayIso()) continue;
        try {
          const response = await mutualFundsAPI.refreshNav(fund.id);
          const refreshed = response.data.fund;
          if (response.data.status === 'success' && refreshed && openFundId.current !== fund.id) {
            setFunds((current) => current.map((f) => (
              f.id === fund.id && !(f.updated_at > refreshed.updated_at) ? refreshed : f
            )));
          }
        } catch (err) {
          // quiet: the next load tries again
        }
      }
    } finally {
      backgroundRefresh.current = false;
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
        current_nav: fund.current_nav?.toString() || '',
        folio_number: fund.folio_number || '',
        sip_amount: fund.sip_amount?.toString() ?? '',
        sip_frequency: fund.sip_frequency || 'monthly',
        sip_day: fund.sip_day?.toString() ?? '',
        sip_start_date: fund.sip_start_date || '',
        sip_end_date: fund.sip_end_date || '',
        holdings_date: fund.sip_amount > 0 && fund.holdings_date ? fund.holdings_date : todayIso()
      });
    } else {
      setEditingFund(null);
      setFormData(emptyForm());
    }
    openFundId.current = fund ? fund.id : null;
    setCurrentValueTouched(false);
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    openFundId.current = null;
    setModalOpen(false);
    setEditingFund(null);
    setFormData(emptyForm());
  };

  const editingSip = editingFund != null && editingFund.sip_amount > 0;

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
        units: formData.units ? parseFloat(formData.units) : 0,
        current_nav: formData.current_nav ? parseFloat(formData.current_nav) : null,
        folio_number: formData.folio_number || null,
        sip_amount: formData.sip_amount === '' ? null : parseFloat(formData.sip_amount),
        sip_frequency: formData.sip_amount === '' ? null : formData.sip_frequency,
        sip_day: formData.sip_amount === '' || formData.sip_frequency === 'weekly' || formData.sip_day === ''
          ? null : parseInt(formData.sip_day, 10),
        sip_start_date: formData.sip_amount === '' ? null : (formData.sip_start_date || null),
        sip_end_date: formData.sip_amount === '' ? null : (formData.sip_end_date || null),
        holdings_date: formData.sip_amount === '' ? null : (formData.holdings_date || null)
      };
      // An edit leaves an untouched current value out, so the stored one stands
      if (!editingFund || currentValueTouched) {
        data.current_value = formData.current_value ? parseFloat(formData.current_value) : null;
      }

      if (editingFund) {
        await mutualFundsAPI.update(editingFund.id, data);
      } else {
        await mutualFundsAPI.create(data);
      }

      closeModal();
      fetchFunds();
    } catch (err) {
      setError(errorMessage(err, 'Failed to save mutual fund'));
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

  // A SIP fund's invested amount counts its installments; the other fields are what was entered
  const investedOf = (fund) => fund.total_invested ?? fund.invested_amount;
  const unitsOf = (fund) => fund.total_units ?? fund.units;

  const sipSummary = (fund) => {
    const frequency = fund.sip_frequency || 'monthly';
    const day = frequency !== 'weekly' && fund.sip_day ? ` on day ${fund.sip_day}` : '';
    const since = fund.sip_start_date ? ` · since ${formatDate(fund.sip_start_date)}` : '';
    const priced = fund.sip_priced_through ? ` · priced to ${formatDate(fund.sip_priced_through)}` : '';
    const amount = privacyMode ? '₹ ••••••' : formatSipAmount(fund.sip_amount);
    return `SIP ${amount} ${frequency}${day}${since}${priced}`;
  };

  const totalInvested = funds.reduce((sum, fund) => sum + investedOf(fund), 0);
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
              <p className="text-xl font-bold mt-1">
                <AnimatedNumber 
                  value={totalInvested} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
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
              <p className="text-xl font-bold mt-1">
                <AnimatedNumber 
                  value={totalCurrentValue} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
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
              <p className="text-xl font-bold mt-1">
                <AnimatedNumber 
                  value={Math.abs(totalReturns)} 
                  formatter={formatCurrencyRaw}
                  privacyMask={privacyMode ? '₹ ••••••' : null}
                />
              </p>
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
              <p className="text-xl font-bold mt-1">
                <AnimatedNumber 
                  value={overallReturnPercent} 
                  formatter={(v) => formatPercent(v)}
                />
              </p>
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
            const invested = investedOf(fund);
            const units = unitsOf(fund);
            const returnAmount = currentVal - invested;
            const returnPercent = invested > 0
              ? ((currentVal - invested) / invested) * 100
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
                        Invested: <span className="text-gray-900 dark:text-white font-medium">{formatCurrency(invested)}</span>
                      </span>
                      {units > 0 && (
                        <span className="text-gray-500 dark:text-gray-400">
                          Units: <span className="text-gray-900 dark:text-white font-medium">{units.toFixed(3)}</span>
                        </span>
                      )}
                      {fund.avg_nav > 0 && !(fund.sip_amount > 0) && (
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
                    {fund.sip_amount > 0 && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{sipSummary(fund)}</p>
                    )}
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
                    step="any"
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
                    step="any"
                    value={formData.current_value}
                    onChange={(e) => {
                      setCurrentValueTouched(true);
                      setFormData({ ...formData, current_value: e.target.value });
                    }}
                  />
                </div>
              </div>

              <div>
                <label className="label">Units</label>
                <input
                  type="number"
                  className="input"
                  placeholder="0.000"
                  min="0"
                  step="any"
                  value={formData.units}
                  onChange={(e) => setFormData({ ...formData, units: e.target.value })}
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Avg NAV will be auto-calculated: Invested Amount ÷ Units
                </p>
              </div>

              <div>
                <label className="label">Current NAV <span className="text-gray-400 font-normal">- Optional (auto-fetched)</span></label>
                <input
                  type="number"
                  className="input"
                  placeholder="Leave empty to fetch from internet"
                  min="0"
                  step="any"
                  value={formData.current_nav}
                  onChange={(e) => setFormData({ ...formData, current_nav: e.target.value })}
                />
              </div>

              <div className="space-y-4 pt-4 border-t dark:border-gray-700">
                <p className="text-sm font-semibold text-gray-900 dark:text-white">
                  SIP <span className="text-gray-400 font-normal">(Optional)</span>
                </p>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="label">SIP amount (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0"
                      min="0"
                      step="any"
                      value={formData.sip_amount}
                      onChange={(e) => setFormData({ ...formData, sip_amount: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label">Frequency</label>
                    <select
                      className="input"
                      value={formData.sip_frequency}
                      onChange={(e) => setFormData({ ...formData, sip_frequency: e.target.value })}
                    >
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                    </select>
                  </div>
                </div>

                {formData.sip_frequency !== 'weekly' && (
                  <div>
                    <label className="label">SIP date (day of month)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g., 5"
                      min="1"
                      max="31"
                      step="1"
                      value={formData.sip_day}
                      onChange={(e) => setFormData({ ...formData, sip_day: e.target.value })}
                    />
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="label">First SIP date</label>
                    <input
                      type="date"
                      className="input"
                      value={formData.sip_start_date}
                      onChange={(e) => setFormData({ ...formData, sip_start_date: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="label">Last SIP date <span className="text-gray-400 font-normal">(Optional)</span></label>
                    <input
                      type="date"
                      className="input"
                      value={formData.sip_end_date}
                      onChange={(e) => setFormData({ ...formData, sip_end_date: e.target.value })}
                    />
                  </div>
                </div>

                <div>
                  <label className="label">Units and invested amount as of</label>
                  <input
                    type="date"
                    className="input"
                    value={formData.holdings_date}
                    onChange={(e) => setFormData({ ...formData, holdings_date: e.target.value })}
                  />
                </div>
                {editingSip && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                    Changing the SIP amount, frequency or day applies from today: installments so far stay in your holding.
                  </p>
                )}

                <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                  Each SIP installment after the 'as of' date buys units at that day's NAV (from mfapi.in); until NAVs are fetched, installments count at cost.
                </p>
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
