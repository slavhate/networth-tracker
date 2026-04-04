import { useState, useEffect } from 'react';
import { equitiesAPI, exchangeAPI } from '../api';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  TrendingUp,
  TrendingDown,
  RefreshCw,
  BarChart3
} from 'lucide-react';

const MARKETS = [
  { value: 'NSE', label: 'NSE (India)', color: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400' },
  { value: 'BSE', label: 'BSE (India)', color: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-400' },
  { value: 'NASDAQ', label: 'NASDAQ (US)', color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400' },
];

// Default rate (fallback)
const DEFAULT_USD_TO_INR = 83.5;

const getMarketInfo = (value) => MARKETS.find(m => m.value === value) || MARKETS[0];

const formatCurrency = (value, market = 'NSE') => {
  if (market === 'NASDAQ') {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  }
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

export default function Equities() {
  const [equities, setEquities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [usdToInr, setUsdToInr] = useState(DEFAULT_USD_TO_INR);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingEquity, setEditingEquity] = useState(null);
  const [formData, setFormData] = useState({
    symbol: '',
    company_name: '',
    market: 'NSE',
    quantity: '',
    avg_buy_price: '',
    current_price: '',
    notes: ''
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchEquities = async (refresh = false) => {
    try {
      if (refresh) setRefreshing(true);
      else setLoading(true);
      const response = await equitiesAPI.getAll(refresh);
      setEquities(response.data);
    } catch (err) {
      setError('Failed to load equities');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const fetchExchangeRate = async () => {
    try {
      const response = await exchangeAPI.getRate();
      if (response.data?.usd_to_inr) {
        setUsdToInr(response.data.usd_to_inr);
      }
    } catch (err) {
      // Use default rate if API fails
      console.warn('Failed to fetch exchange rate, using default');
    }
  };

  useEffect(() => {
    fetchEquities(true); // Refresh prices on initial load
    fetchExchangeRate();  // Get current exchange rate
  }, []);

  const handleRefreshPrices = () => {
    fetchEquities(true);
  };

  const openModal = (equity = null) => {
    if (equity) {
      setEditingEquity(equity);
      setFormData({
        symbol: equity.symbol,
        company_name: equity.company_name || '',
        market: equity.market,
        quantity: equity.quantity.toString(),
        avg_buy_price: equity.avg_buy_price.toString(),
        current_price: equity.current_price ? equity.current_price.toString() : '',
        notes: equity.notes || ''
      });
    } else {
      setEditingEquity(null);
      setFormData({
        symbol: '',
        company_name: '',
        market: 'NSE',
        quantity: '',
        avg_buy_price: '',
        current_price: '',
        notes: ''
      });
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingEquity(null);
    setFormData({
      symbol: '',
      company_name: '',
      market: 'NSE',
      quantity: '',
      avg_buy_price: '',
      current_price: '',
      notes: ''
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = {
        symbol: formData.symbol.toUpperCase(),
        company_name: formData.company_name || null,
        market: formData.market,
        quantity: parseInt(formData.quantity),
        avg_buy_price: parseFloat(formData.avg_buy_price),
        current_price: formData.current_price ? parseFloat(formData.current_price) : null,
        notes: formData.notes || null
      };

      if (editingEquity) {
        await equitiesAPI.update(editingEquity.id, data);
      } else {
        await equitiesAPI.create(data);
      }

      closeModal();
      fetchEquities(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save equity');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this holding?')) return;

    try {
      await equitiesAPI.delete(id);
      fetchEquities();
    } catch (err) {
      setError('Failed to delete equity');
    }
  };

  // Calculate totals in INR (convert NASDAQ USD to INR)
  const totalInvestedINR = equities.reduce((sum, e) => {
    const amount = e.market === 'NASDAQ' ? e.invested_amount * usdToInr : e.invested_amount;
    return sum + amount;
  }, 0);
  const totalCurrentValueINR = equities.reduce((sum, e) => {
    const amount = e.market === 'NASDAQ' ? e.current_value * usdToInr : e.current_value;
    return sum + amount;
  }, 0);
  const totalGainLossINR = totalCurrentValueINR - totalInvestedINR;
  const overallReturnPercent = totalInvestedINR > 0 ? ((totalCurrentValueINR - totalInvestedINR) / totalInvestedINR) * 100 : 0;

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Equities</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Track your stock portfolio with live prices</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={handleRefreshPrices} 
            disabled={refreshing}
            className="btn-secondary flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Refreshing...' : 'Refresh Prices'}
          </button>
          <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Stock
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-blue-100 font-medium">Invested</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(totalInvestedINR)}</p>
              <p className="text-xs text-blue-200 mt-0.5">All markets in INR</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <BarChart3 className="w-5 h-5" />
            </div>
          </div>
        </div>

        <div className="card bg-gradient-to-r from-green-500 to-green-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 font-medium">Current Value</p>
              <p className="text-xl font-bold mt-1">{formatCurrency(totalCurrentValueINR)}</p>
              <p className="text-xs text-green-200 mt-0.5">USD @ ₹{usdToInr.toFixed(2)}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              <TrendingUp className="w-5 h-5" />
            </div>
          </div>
        </div>

        <div className={`card ${totalGainLossINR >= 0 ? 'bg-gradient-to-r from-emerald-500 to-emerald-600' : 'bg-gradient-to-r from-red-500 to-red-600'} text-white`}>
          <div className="flex items-center justify-between">
            <div>
              <p className={`${totalGainLossINR >= 0 ? 'text-emerald-100' : 'text-red-100'} font-medium`}>
                {totalGainLossINR >= 0 ? 'Profit' : 'Loss'}
              </p>
              <p className="text-xl font-bold mt-1">{formatCurrency(Math.abs(totalGainLossINR))}</p>
            </div>
            <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
              {totalGainLossINR >= 0 ? <TrendingUp className="w-5 h-5" /> : <TrendingDown className="w-5 h-5" />}
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
              <BarChart3 className="w-5 h-5" />
            </div>
          </div>
        </div>
      </div>

      {/* Equities List */}
      {equities.length === 0 ? (
        <div className="card text-center py-12">
          <BarChart3 className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">No stocks yet</h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Add your stock holdings to track live prices</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Your First Stock
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {equities.map((equity) => {
            const marketInfo = getMarketInfo(equity.market);
            const isPositive = equity.gain_loss >= 0;
            
            return (
              <div key={equity.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-start gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${marketInfo.color}`}>
                    <span className="font-bold text-sm">{equity.symbol.substring(0, 3)}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-white">{equity.symbol}</h3>
                      <span className={`px-2 py-0.5 rounded text-xs ${marketInfo.color}`}>{equity.market}</span>
                    </div>
                    {equity.company_name && (
                      <p className="text-sm text-gray-500 dark:text-gray-400">{equity.company_name}</p>
                    )}
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm mt-2">
                      <span className="text-gray-500 dark:text-gray-400">
                        Qty: <span className="text-gray-900 dark:text-white font-medium">{equity.quantity}</span>
                      </span>
                      <span className="text-gray-500 dark:text-gray-400">
                        Avg: <span className="text-gray-900 dark:text-white font-medium">{formatCurrency(equity.avg_buy_price, equity.market)}</span>
                      </span>
                      <span className="text-gray-500 dark:text-gray-400">
                        LTP: <span className="text-gray-900 dark:text-white font-medium">{formatCurrency(equity.current_price, equity.market)}</span>
                      </span>
                    </div>
                    {equity.notes && (
                      <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">{equity.notes}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(equity.current_value, equity.market)}</p>
                    <p className={`text-sm font-medium flex items-center justify-end gap-1 ${isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {isPositive ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                      {formatCurrency(Math.abs(equity.gain_loss), equity.market)} ({formatPercent(equity.gain_loss_percent)})
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      Invested: {formatCurrency(equity.invested_amount, equity.market)}
                    </p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => openModal(equity)}
                      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(equity.id)}
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
                {editingEquity ? 'Edit Stock' : 'Add New Stock'}
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
                <label className="label">Stock Symbol (SCRIP)</label>
                <input
                  type="text"
                  className="input uppercase"
                  placeholder="e.g., TCS, INFY, AAPL"
                  value={formData.symbol}
                  onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Enter the stock ticker symbol</p>
              </div>

              <div>
                <label className="label">Stock Market</label>
                <select
                  className="input"
                  value={formData.market}
                  onChange={(e) => setFormData({ ...formData, market: e.target.value })}
                >
                  {MARKETS.map((market) => (
                    <option key={market.value} value={market.value}>
                      {market.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Company Name (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., Tata Consultancy Services"
                  value={formData.company_name}
                  onChange={(e) => setFormData({ ...formData, company_name: e.target.value })}
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Will be auto-filled if available</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Quantity</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0"
                    min="1"
                    step="1"
                    value={formData.quantity}
                    onChange={(e) => setFormData({ ...formData, quantity: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="label">Avg. Buy Price</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    value={formData.avg_buy_price}
                    onChange={(e) => setFormData({ ...formData, avg_buy_price: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div>
                <label className="label">
                  Current Price / LTP (Optional)
                  <span className="text-xs text-gray-400 ml-2">Leave empty to auto-fetch</span>
                </label>
                <input
                  type="number"
                  className="input"
                  placeholder="Auto-fetch from market"
                  min="0"
                  step="0.01"
                  value={formData.current_price}
                  onChange={(e) => setFormData({ ...formData, current_price: e.target.value })}
                />
              </div>

              <div>
                <label className="label">Notes (Optional)</label>
                <textarea
                  className="input"
                  rows="2"
                  placeholder="e.g., Long-term investment, sector info..."
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingEquity ? 'Update' : 'Add Stock')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
