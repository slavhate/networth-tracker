import { useState, useEffect } from 'react';
import { liabilitiesAPI } from '../api';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  CreditCard,
  Home,
  Car,
  GraduationCap,
  Wallet,
  HelpCircle,
  Percent
} from 'lucide-react';

const CATEGORIES = [
  { value: 'mortgage', label: 'Mortgage', icon: Home, color: 'bg-purple-100 text-purple-600' },
  { value: 'car_loan', label: 'Car Loan', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'student_loan', label: 'Student Loan', icon: GraduationCap, color: 'bg-blue-100 text-blue-600' },
  { value: 'credit_card', label: 'Credit Card', icon: CreditCard, color: 'bg-red-100 text-red-600' },
  { value: 'personal_loan', label: 'Personal Loan', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

const getCategoryInfo = (value) => CATEGORIES.find(c => c.value === value) || CATEGORIES[5];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

export default function Liabilities() {
  const [liabilities, setLiabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLiability, setEditingLiability] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    amount: '',
    category: 'credit_card',
    interest_rate: '',
    description: ''
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchLiabilities = async () => {
    try {
      setLoading(true);
      const response = await liabilitiesAPI.getAll();
      setLiabilities(response.data);
    } catch (err) {
      setError('Failed to load liabilities');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLiabilities();
  }, []);

  const openModal = (liability = null) => {
    if (liability) {
      setEditingLiability(liability);
      setFormData({
        name: liability.name,
        amount: liability.amount.toString(),
        category: liability.category,
        interest_rate: liability.interest_rate?.toString() || '',
        description: liability.description || ''
      });
    } else {
      setEditingLiability(null);
      setFormData({ name: '', amount: '', category: 'credit_card', interest_rate: '', description: '' });
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingLiability(null);
    setFormData({ name: '', amount: '', category: 'credit_card', interest_rate: '', description: '' });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = {
        name: formData.name,
        amount: parseFloat(formData.amount),
        category: formData.category,
        interest_rate: formData.interest_rate ? parseFloat(formData.interest_rate) : null,
        description: formData.description || null
      };

      if (editingLiability) {
        await liabilitiesAPI.update(editingLiability.id, data);
      } else {
        await liabilitiesAPI.create(data);
      }

      closeModal();
      fetchLiabilities();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save liability');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this liability?')) return;

    try {
      await liabilitiesAPI.delete(id);
      fetchLiabilities();
    } catch (err) {
      setError('Failed to delete liability');
    }
  };

  const totalLiabilities = liabilities.reduce((sum, liability) => sum + liability.amount, 0);
  const avgInterestRate = liabilities.length > 0
    ? liabilities.reduce((sum, l) => sum + (l.interest_rate || 0), 0) / liabilities.filter(l => l.interest_rate).length
    : 0;

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Liabilities</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Track your debts and obligations</p>
        </div>
        <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Liability
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card bg-gradient-to-r from-orange-500 to-red-500 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-orange-100 font-medium">Total Liabilities</p>
              <p className="text-3xl font-bold mt-1">{formatCurrency(totalLiabilities)}</p>
            </div>
            <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
              <CreditCard className="w-8 h-8" />
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-500 dark:text-gray-400 font-medium">Avg. Interest Rate</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white mt-1">
                {avgInterestRate ? `${avgInterestRate.toFixed(1)}%` : 'N/A'}
              </p>
            </div>
            <div className="w-16 h-16 bg-purple-100 dark:bg-purple-900/50 rounded-2xl flex items-center justify-center">
              <Percent className="w-8 h-8 text-purple-600 dark:text-purple-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Liabilities List */}
      {liabilities.length === 0 ? (
        <div className="card text-center py-12">
          <CreditCard className="w-16 h-16 mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900">No liabilities yet</h3>
          <p className="text-gray-500 mt-1">Great! You're debt-free, or add any debts to track them</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Liability
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {liabilities.map((liability) => {
            const categoryInfo = getCategoryInfo(liability.category);
            const CategoryIcon = categoryInfo.icon;
            
            return (
              <div key={liability.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${categoryInfo.color}`}>
                    <CategoryIcon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{liability.name}</h3>
                    <div className="flex items-center gap-3 text-sm text-gray-500">
                      <span>{categoryInfo.label}</span>
                      {liability.interest_rate && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                          {liability.interest_rate}% APR
                        </span>
                      )}
                    </div>
                    {liability.description && (
                      <p className="text-sm text-gray-400 truncate mt-1">{liability.description}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-red-600">{formatCurrency(liability.amount)}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => openModal(liability)}
                      className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(liability.id)}
                      className="p-2 rounded-lg hover:bg-red-50 text-gray-500 hover:text-red-600"
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
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md">
            <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                {editingLiability ? 'Edit Liability' : 'Add New Liability'}
              </h2>
              <button onClick={closeModal} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                  {error}
                </div>
              )}

              <div>
                <label className="label">Liability Name</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., Credit Card Balance"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Amount Owed (₹)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="0.00"
                  min="0"
                  step="0.01"
                  value={formData.amount}
                  onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
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
                  {CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Interest Rate % (Optional)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="e.g., 18.99"
                  min="0"
                  max="100"
                  step="0.01"
                  value={formData.interest_rate}
                  onChange={(e) => setFormData({ ...formData, interest_rate: e.target.value })}
                />
              </div>

              <div>
                <label className="label">Description (Optional)</label>
                <textarea
                  className="input min-h-[80px]"
                  placeholder="Add notes about this liability..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingLiability ? 'Update' : 'Add Liability')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
