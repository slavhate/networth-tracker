import { useState, useEffect } from 'react';
import { assetsAPI } from '../api';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  Wallet,
  Banknote,
  Building,
  Car,
  PiggyBank,
  Bitcoin,
  HelpCircle
} from 'lucide-react';

const CATEGORIES = [
  { value: 'cash', label: 'Cash & Savings', icon: Banknote, color: 'bg-green-100 text-green-600' },
  { value: 'investments', label: 'Investments', icon: PiggyBank, color: 'bg-blue-100 text-blue-600' },
  { value: 'real_estate', label: 'Real Estate', icon: Building, color: 'bg-purple-100 text-purple-600' },
  { value: 'vehicles', label: 'Vehicles', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'retirement', label: 'Retirement', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  { value: 'crypto', label: 'Cryptocurrency', icon: Bitcoin, color: 'bg-yellow-100 text-yellow-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

const getCategoryInfo = (value) => CATEGORIES.find(c => c.value === value) || CATEGORIES[6];

const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

export default function Assets() {
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    value: '',
    category: 'cash',
    description: ''
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchAssets = async () => {
    try {
      setLoading(true);
      const response = await assetsAPI.getAll();
      setAssets(response.data);
    } catch (err) {
      setError('Failed to load assets');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssets();
  }, []);

  const openModal = (asset = null) => {
    if (asset) {
      setEditingAsset(asset);
      setFormData({
        name: asset.name,
        value: asset.value.toString(),
        category: asset.category,
        description: asset.description || ''
      });
    } else {
      setEditingAsset(null);
      setFormData({ name: '', value: '', category: 'cash', description: '' });
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingAsset(null);
    setFormData({ name: '', value: '', category: 'cash', description: '' });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const data = {
        name: formData.name,
        value: parseFloat(formData.value),
        category: formData.category,
        description: formData.description || null
      };

      if (editingAsset) {
        await assetsAPI.update(editingAsset.id, data);
      } else {
        await assetsAPI.create(data);
      }

      closeModal();
      fetchAssets();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save asset');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this asset?')) return;

    try {
      await assetsAPI.delete(id);
      fetchAssets();
    } catch (err) {
      setError('Failed to delete asset');
    }
  };

  const totalAssets = assets.reduce((sum, asset) => sum + asset.value, 0);

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Assets</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Manage your assets and track their value</p>
        </div>
        <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Asset
        </button>
      </div>

      {/* Summary Card */}
      <div className="card bg-gradient-to-r from-primary-500 to-primary-600 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-primary-100 font-medium">Total Assets Value</p>
            <p className="text-3xl font-bold mt-1">{formatCurrency(totalAssets)}</p>
          </div>
          <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
            <Wallet className="w-8 h-8" />
          </div>
        </div>
      </div>

      {/* Assets List */}
      {assets.length === 0 ? (
        <div className="card text-center py-12">
          <Wallet className="w-16 h-16 mx-auto text-gray-300 mb-4" />
          <h3 className="text-lg font-medium text-gray-900">No assets yet</h3>
          <p className="text-gray-500 mt-1">Start by adding your first asset</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Your First Asset
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {assets.map((asset) => {
            const categoryInfo = getCategoryInfo(asset.category);
            const CategoryIcon = categoryInfo.icon;
            
            return (
              <div key={asset.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${categoryInfo.color}`}>
                    <CategoryIcon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{asset.name}</h3>
                    <p className="text-sm text-gray-500">{categoryInfo.label}</p>
                    {asset.description && (
                      <p className="text-sm text-gray-400 truncate mt-1">{asset.description}</p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(asset.value)}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => openModal(asset)}
                      className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-gray-700"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(asset.id)}
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
                {editingAsset ? 'Edit Asset' : 'Add New Asset'}
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
                <label className="label">Asset Name</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., Savings Account"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Value (₹)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="0.00"
                  min="0"
                  step="0.01"
                  value={formData.value}
                  onChange={(e) => setFormData({ ...formData, value: e.target.value })}
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
                <label className="label">Description (Optional)</label>
                <textarea
                  className="input min-h-[80px]"
                  placeholder="Add notes about this asset..."
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingAsset ? 'Update' : 'Add Asset')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
