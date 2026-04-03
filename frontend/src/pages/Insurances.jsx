import { useState, useEffect } from 'react';
import { insurancesAPI } from '../api';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  Shield,
  Heart,
  Car,
  Home,
  Briefcase,
  HelpCircle,
  Calendar,
  AlertCircle
} from 'lucide-react';

const INSURANCE_TYPES = [
  { value: 'life', label: 'Life Insurance', icon: Heart, color: 'bg-red-100 text-red-600 dark:bg-red-900/50 dark:text-red-400' },
  { value: 'health', label: 'Health Insurance', icon: Shield, color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400' },
  { value: 'vehicle', label: 'Vehicle Insurance', icon: Car, color: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400' },
  { value: 'home', label: 'Home Insurance', icon: Home, color: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-400' },
  { value: 'term', label: 'Term Insurance', icon: Briefcase, color: 'bg-orange-100 text-orange-600 dark:bg-orange-900/50 dark:text-orange-400' },
  { value: 'other', label: 'Other Insurance', icon: HelpCircle, color: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400' },
];

const getInsuranceTypeInfo = (value) => INSURANCE_TYPES.find(t => t.value === value) || INSURANCE_TYPES[5];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const formatDate = (dateStr) => {
  if (!dateStr) return '';
  return new Date(dateStr).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  });
};

const getDaysUntilExpiry = (dateStr) => {
  if (!dateStr) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const expiry = new Date(dateStr);
  expiry.setHours(0, 0, 0, 0);
  const diffTime = expiry - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return diffDays;
};

const getExpiryStatus = (dateStr) => {
  const days = getDaysUntilExpiry(dateStr);
  if (days === null) return { label: '', color: '' };
  if (days < 0) return { label: 'Expired', color: 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30' };
  if (days <= 30) return { label: `Expires in ${days} days`, color: 'text-orange-600 dark:text-orange-400 bg-orange-100 dark:bg-orange-900/30' };
  if (days <= 90) return { label: `Expires in ${days} days`, color: 'text-yellow-600 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30' };
  return { label: formatDate(dateStr), color: 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30' };
};

export default function Insurances() {
  const [insurances, setInsurances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingInsurance, setEditingInsurance] = useState(null);
  const [formData, setFormData] = useState({
    policy_name: '',
    insurance_type: 'health',
    provider: '',
    policy_number: '',
    premium: '',
    sum_assured: '',
    start_date: '',
    end_date: '',
    notes: ''
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchInsurances = async () => {
    try {
      setLoading(true);
      const response = await insurancesAPI.getAll();
      setInsurances(response.data);
    } catch (err) {
      setError('Failed to load insurances');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInsurances();
  }, []);

  const openModal = (insurance = null) => {
    if (insurance) {
      setEditingInsurance(insurance);
      setFormData({
        policy_name: insurance.policy_name,
        insurance_type: insurance.insurance_type,
        provider: insurance.provider,
        policy_number: insurance.policy_number || '',
        premium: insurance.premium.toString(),
        sum_assured: insurance.sum_assured.toString(),
        start_date: insurance.start_date || '',
        end_date: insurance.end_date || '',
        notes: insurance.notes || ''
      });
    } else {
      setEditingInsurance(null);
      setFormData({
        policy_name: '',
        insurance_type: 'health',
        provider: '',
        policy_number: '',
        premium: '',
        sum_assured: '',
        start_date: '',
        end_date: '',
        notes: ''
      });
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingInsurance(null);
    setFormData({
      policy_name: '',
      insurance_type: 'health',
      provider: '',
      policy_number: '',
      premium: '',
      sum_assured: '',
      start_date: '',
      end_date: '',
      notes: ''
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = {
        policy_name: formData.policy_name,
        insurance_type: formData.insurance_type,
        provider: formData.provider,
        policy_number: formData.policy_number || null,
        premium: parseFloat(formData.premium),
        sum_assured: parseFloat(formData.sum_assured),
        start_date: formData.start_date || null,
        end_date: formData.end_date || null,
        notes: formData.notes || null
      };

      if (editingInsurance) {
        await insurancesAPI.update(editingInsurance.id, data);
      } else {
        await insurancesAPI.create(data);
      }

      closeModal();
      fetchInsurances();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save insurance');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this insurance policy?')) return;

    try {
      await insurancesAPI.delete(id);
      fetchInsurances();
    } catch (err) {
      setError('Failed to delete insurance');
    }
  };

  const totalPremium = insurances.reduce((sum, ins) => sum + ins.premium, 0);
  const totalCoverage = insurances.reduce((sum, ins) => sum + ins.sum_assured, 0);
  const expiringCount = insurances.filter(ins => {
    const days = getDaysUntilExpiry(ins.end_date);
    return days !== null && days >= 0 && days <= 90;
  }).length;

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Insurances</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Manage your insurance policies</p>
        </div>
        <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Insurance
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card bg-gradient-to-r from-green-500 to-green-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-green-100 font-medium">Total Coverage</p>
              <p className="text-2xl font-bold mt-1">{formatCurrency(totalCoverage)}</p>
            </div>
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <Shield className="w-6 h-6" />
            </div>
          </div>
        </div>

        <div className="card bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-blue-100 font-medium">Annual Premium</p>
              <p className="text-2xl font-bold mt-1">{formatCurrency(totalPremium)}</p>
            </div>
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <Calendar className="w-6 h-6" />
            </div>
          </div>
        </div>

        <div className="card bg-gradient-to-r from-orange-500 to-orange-600 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-orange-100 font-medium">Expiring Soon</p>
              <p className="text-2xl font-bold mt-1">{expiringCount}</p>
              <p className="text-orange-100 text-sm">within 90 days</p>
            </div>
            <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
              <AlertCircle className="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      {/* Insurance List */}
      {insurances.length === 0 ? (
        <div className="card text-center py-12">
          <Shield className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">No insurance policies yet</h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Add your insurance policies to track coverage</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Your First Policy
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {insurances.map((insurance) => {
            const typeInfo = getInsuranceTypeInfo(insurance.insurance_type);
            const TypeIcon = typeInfo.icon;
            const expiryStatus = getExpiryStatus(insurance.end_date);
            
            return (
              <div key={insurance.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-start gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${typeInfo.color}`}>
                    <TypeIcon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-900 dark:text-white">{insurance.policy_name}</h3>
                      {expiryStatus.label && (
                        <span className={`text-xs px-2 py-1 rounded-full ${expiryStatus.color}`}>
                          {expiryStatus.label}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500 dark:text-gray-400 mt-1">
                      <span>{typeInfo.label}</span>
                      <span>•</span>
                      <span>{insurance.provider}</span>
                      {insurance.policy_number && (
                        <>
                          <span>•</span>
                          <span>Policy: {insurance.policy_number}</span>
                        </>
                      )}
                    </div>
                    {insurance.notes && (
                      <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">{insurance.notes}</p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(insurance.sum_assured)}</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Premium: {formatCurrency(insurance.premium)}/yr</p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <button
                      onClick={() => openModal(insurance)}
                      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(insurance.id)}
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
                {editingInsurance ? 'Edit Insurance Policy' : 'Add New Insurance Policy'}
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
                <label className="label">Policy Name</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., Family Health Insurance"
                  value={formData.policy_name}
                  onChange={(e) => setFormData({ ...formData, policy_name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Insurance Type</label>
                <select
                  className="input"
                  value={formData.insurance_type}
                  onChange={(e) => setFormData({ ...formData, insurance_type: e.target.value })}
                >
                  {INSURANCE_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">Provider</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., LIC, HDFC Ergo"
                  value={formData.provider}
                  onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Policy Number (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="Enter policy number"
                  value={formData.policy_number}
                  onChange={(e) => setFormData({ ...formData, policy_number: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Premium (₹/year)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0"
                    min="0"
                    step="1"
                    value={formData.premium}
                    onChange={(e) => setFormData({ ...formData, premium: e.target.value })}
                    required
                  />
                </div>
                <div>
                  <label className="label">Sum Assured (₹)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="0"
                    min="0"
                    step="1"
                    value={formData.sum_assured}
                    onChange={(e) => setFormData({ ...formData, sum_assured: e.target.value })}
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="label">Start Date (Optional)</label>
                  <input
                    type="date"
                    className="input"
                    value={formData.start_date}
                    onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  />
                </div>
                <div>
                  <label className="label">End Date (Optional)</label>
                  <input
                    type="date"
                    className="input"
                    value={formData.end_date}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  />
                </div>
              </div>

              <div>
                <label className="label">Notes (Optional)</label>
                <textarea
                  className="input"
                  rows="2"
                  placeholder="Additional details..."
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingInsurance ? 'Update' : 'Add Policy')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
