import { useState, useEffect } from 'react';
import { bankAccountsAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import AnimatedNumber from '../components/AnimatedNumber';
import PageError from '../components/PageError';
import AmountHint from '../components/AmountHint';
import { 
  Plus, 
  Edit2, 
  Trash2, 
  X, 
  Building2,
  Landmark,
  PiggyBank,
  Banknote,
  Clock,
  CalendarClock
} from 'lucide-react';
import { errorMessage } from '../utils/errors';
import { formatDate } from '../utils/dates';

const ACCOUNT_TYPES = [
  { value: 'savings', label: 'Savings Account', icon: PiggyBank, color: 'bg-green-100 text-green-600 dark:bg-green-900/50 dark:text-green-400' },
  { value: 'current', label: 'Current Account', icon: Banknote, color: 'bg-blue-100 text-blue-600 dark:bg-blue-900/50 dark:text-blue-400' },
  { value: 'salary', label: 'Salary Account', icon: Building2, color: 'bg-purple-100 text-purple-600 dark:bg-purple-900/50 dark:text-purple-400' },
  { value: 'fd', label: 'Fixed Deposit', icon: Clock, color: 'bg-orange-100 text-orange-600 dark:bg-orange-900/50 dark:text-orange-400' },
  { value: 'rd', label: 'Recurring Deposit', icon: CalendarClock, color: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/50 dark:text-indigo-400' },
];

const DEPOSIT_TYPES = ['fd', 'rd'];

const emptyForm = () => ({
  bank_name: '', account_number: '', account_type: 'savings', balance: '', branch: '', ifsc_code: '',
  interest_rate: '', start_date: '', maturity_date: '', monthly_deposit: '',
});

const balanceLabel = (type) => (type === 'fd' ? 'Principal (₹)' : type === 'rd' ? 'Deposited so far (₹)' : 'Balance (₹)');

const getAccountTypeInfo = (value) => ACCOUNT_TYPES.find(t => t.value === value) || ACCOUNT_TYPES[0];

const formatCurrencyRaw = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

// Show only the last 4 digits; a number of 4 characters or fewer would be shown whole, so it is masked fully
const maskAccountNumber = (num) => {
  if (!num) return num;
  if (num.length <= 4) return '••••';
  return '••••' + num.slice(-4);
};

export default function BankAccounts() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  const [error, setError] = useState('');
  const [pageError, setPageError] = useState(null);   // a list load or delete failure, shown on the page
  const [loaded, setLoaded] = useState(false);       // the list has loaded at least once
  const [submitting, setSubmitting] = useState(false);

  const fetchAccounts = async () => {
    try {
      setLoading(true);
      const response = await bankAccountsAPI.getAll();
      setAccounts(response.data);
      setLoaded(true);
      setPageError(null);
      updateLastUpdated();
    } catch (err) {
      setPageError({ message: errorMessage(err, 'Failed to load bank accounts'), retry: true });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const openModal = (account = null) => {
    if (account) {
      setEditingAccount(account);
      setFormData({
        bank_name: account.bank_name,
        account_number: account.account_number,
        account_type: account.account_type,
        balance: account.balance.toString(),
        branch: account.branch || '',
        ifsc_code: account.ifsc_code || '',
        interest_rate: account.interest_rate?.toString() ?? '',
        start_date: account.start_date || '',
        maturity_date: account.maturity_date || '',
        monthly_deposit: account.monthly_deposit?.toString() ?? ''
      });
    } else {
      setEditingAccount(null);
      setFormData(emptyForm());
    }
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingAccount(null);
    setFormData(emptyForm());
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const isDeposit = DEPOSIT_TYPES.includes(formData.account_type);
      const optionalNumber = (v) => (v === '' ? null : parseFloat(v));
      const data = {
        bank_name: formData.bank_name,
        account_number: formData.account_number,
        account_type: formData.account_type,
        balance: parseFloat(formData.balance),
        branch: formData.branch || null,
        ifsc_code: formData.ifsc_code || null,
        interest_rate: isDeposit ? optionalNumber(formData.interest_rate) : null,
        start_date: isDeposit ? formData.start_date || null : null,
        maturity_date: isDeposit ? formData.maturity_date || null : null,
        monthly_deposit: formData.account_type === 'rd' ? optionalNumber(formData.monthly_deposit) : null
      };

      if (editingAccount) {
        await bankAccountsAPI.update(editingAccount.id, data);
      } else {
        await bankAccountsAPI.create(data);
      }

      closeModal();
      fetchAccounts();
    } catch (err) {
      setError(errorMessage(err, 'Failed to save bank account'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this bank account?')) return;

    try {
      await bankAccountsAPI.delete(id);
      fetchAccounts();
    } catch (err) {
      setPageError({ message: errorMessage(err, 'Failed to delete bank account'), retry: false });
    }
  };

  const formatCurrency = (value) => {
    if (privacyMode) return '₹ ••••••';
    return formatCurrencyRaw(value);
  };

  const totalBalance = accounts.reduce((sum, account) => sum + account.current_value, 0);

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
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Bank Accounts</h1>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Manage your bank accounts and track balances</p>
        </div>
        <button onClick={() => openModal()} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Account
        </button>
      </div>

      <PageError
        message={pageError?.message}
        onRetry={pageError?.retry ? fetchAccounts : undefined}
        onDismiss={() => setPageError(null)}
      />

      {/* Summary Card */}
      <div className="card bg-gradient-to-r from-blue-500 to-blue-600 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-blue-100 font-medium">Total Bank Balance</p>
            <p className="text-3xl font-bold mt-1">
              <AnimatedNumber 
                value={totalBalance} 
                formatter={formatCurrencyRaw}
                privacyMask={!loaded ? '—' : privacyMode ? '₹ ••••••' : null}
              />
            </p>
            {loaded && <p className="text-blue-100 text-sm mt-1">{accounts.length} account{accounts.length !== 1 ? 's' : ''}</p>}
          </div>
          <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
            <Landmark className="w-8 h-8" />
          </div>
        </div>
      </div>

      {/* Accounts List */}
      {accounts.length === 0 ? loaded && (
        <div className="card text-center py-12">
          <Landmark className="w-16 h-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white">No bank accounts yet</h3>
          <p className="text-gray-500 dark:text-gray-400 mt-1">Add your bank accounts to track balances</p>
          <button onClick={() => openModal()} className="btn-primary mt-4">
            <Plus className="w-4 h-4 inline mr-2" />
            Add Your First Account
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {accounts.map((account) => {
            const typeInfo = getAccountTypeInfo(account.account_type);
            const TypeIcon = typeInfo.icon;
            
            return (
              <div key={account.id} className="card hover:shadow-md transition-shadow">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${typeInfo.color}`}>
                    <TypeIcon className="w-6 h-6" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 dark:text-white">{account.bank_name}</h3>
                    <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
                      <span>{typeInfo.label}</span>
                      <span>•</span>
                      <span>{maskAccountNumber(account.account_number)}</span>
                    </div>
                    {account.branch && (
                      <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">{account.branch}</p>
                    )}
                    {account.days_to_maturity != null && (
                      account.matured ? (
                        <p className="text-xs font-medium text-red-600 dark:text-red-400 mt-1">
                          Matured on {formatDate(account.maturity_date)} — update or renew it
                        </p>
                      ) : (
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                          Matures in {account.days_to_maturity} day{account.days_to_maturity === 1 ? '' : 's'} ({formatDate(account.maturity_date)})
                          {account.maturity_value != null && <> · {formatCurrency(account.maturity_value)}</>}
                        </p>
                      )
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-lg font-bold text-gray-900 dark:text-white">{formatCurrency(account.current_value)}</p>
                    {account.ifsc_code && (
                      <p className="text-xs text-gray-400 dark:text-gray-500">IFSC: {account.ifsc_code}</p>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => openModal(account)}
                      className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(account.id)}
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
                {editingAccount ? 'Edit Bank Account' : 'Add New Bank Account'}
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
                <label className="label">Bank Name</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., HDFC Bank"
                  value={formData.bank_name}
                  onChange={(e) => setFormData({ ...formData, bank_name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Account Number</label>
                <input
                  type="text"
                  className="input"
                  placeholder="Enter account number"
                  value={formData.account_number}
                  onChange={(e) => setFormData({ ...formData, account_number: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="label">Account Type</label>
                <select
                  className="input"
                  value={formData.account_type}
                  onChange={(e) => setFormData({ ...formData, account_type: e.target.value })}
                >
                  {ACCOUNT_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">{balanceLabel(formData.account_type)}</label>
                <input
                  type="number"
                  className="input"
                  placeholder="0.00"
                  min="0"
                  step="any"
                  value={formData.balance}
                  onChange={(e) => setFormData({ ...formData, balance: e.target.value })}
                  required
                />
                <AmountHint value={formData.balance} />
              </div>

              {DEPOSIT_TYPES.includes(formData.account_type) && (
                <>
                  {formData.account_type === 'rd' && (
                    <div>
                      <label className="label">Monthly deposit (₹)</label>
                      <input type="number" className="input" placeholder="e.g., 5000" min="0.01" step="any"
                        value={formData.monthly_deposit}
                        onChange={(e) => setFormData({ ...formData, monthly_deposit: e.target.value })} />
                      <AmountHint value={formData.monthly_deposit} />
                    </div>
                  )}
                  <div>
                    <label className="label">Interest rate (% p.a.)</label>
                    <input type="number" className="input" placeholder="e.g., 7.1" min="0" max="100" step="any"
                      value={formData.interest_rate}
                      onChange={(e) => setFormData({ ...formData, interest_rate: e.target.value })} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Start date</label>
                      <input type="date" className="input" value={formData.start_date}
                        onChange={(e) => setFormData({ ...formData, start_date: e.target.value })} />
                    </div>
                    <div>
                      <label className="label">Maturity date</label>
                      <input type="date" className="input" value={formData.maturity_date} min={formData.start_date || undefined}
                        onChange={(e) => setFormData({ ...formData, maturity_date: e.target.value })} />
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                    Interest compounds quarterly, as banks quote FD and RD rates.
                  </p>
                </>
              )}

              <div>
                <label className="label">Branch (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., MG Road Branch"
                  value={formData.branch}
                  onChange={(e) => setFormData({ ...formData, branch: e.target.value })}
                />
              </div>

              <div>
                <label className="label">IFSC Code (Optional)</label>
                <input
                  type="text"
                  className="input"
                  placeholder="e.g., HDFC0001234"
                  value={formData.ifsc_code}
                  onChange={(e) => setFormData({ ...formData, ifsc_code: e.target.value.toUpperCase() })}
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button type="button" onClick={closeModal} className="btn-secondary flex-1">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="btn-primary flex-1">
                  {submitting ? 'Saving...' : (editingAccount ? 'Update' : 'Add Account')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
