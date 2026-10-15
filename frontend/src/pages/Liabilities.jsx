import { useState, useEffect } from 'react';
import { liabilitiesAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import AnimatedNumber from '../components/AnimatedNumber';
import { formatShortINR } from '../utils/indianNumbers';
import PageError from '../components/PageError';
import AmountHint from '../components/AmountHint';
import LoanScheduleModal from '../components/LoanScheduleModal';
import ItemTile, { ItemTileGrid, TileAction } from '../components/ItemTile';
import {
  Plus,
  X,
  CreditCard,
  Home,
  Car,
  GraduationCap,
  Wallet,
  HelpCircle,
  Percent,
  CalendarDays
} from 'lucide-react';
import { errorMessage } from '../utils/errors';
import { todayIso, formatDate, formatMonthYear } from '../utils/dates';
import { emiForTenure } from '../utils/loans';

const CATEGORIES = [
  { value: 'mortgage', label: 'Mortgage', icon: Home, color: 'bg-purple-100 text-purple-600' },
  { value: 'car_loan', label: 'Car Loan', icon: Car, color: 'bg-orange-100 text-orange-600' },
  { value: 'student_loan', label: 'Student Loan', icon: GraduationCap, color: 'bg-blue-100 text-blue-600' },
  { value: 'credit_card', label: 'Credit Card', icon: CreditCard, color: 'bg-red-100 text-red-600' },
  { value: 'personal_loan', label: 'Personal Loan', icon: Wallet, color: 'bg-indigo-100 text-indigo-600' },
  { value: 'other', label: 'Other', icon: HelpCircle, color: 'bg-gray-100 text-gray-600' },
];

const getCategoryInfo = (value) => CATEGORIES.find(c => c.value === value) || CATEGORIES[5];

const formatCurrencyRaw = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

const emptyForm = () => ({
  name: '', amount: '', category: 'credit_card', interest_rate: '', description: '',
  emi: '', balance_date: todayIso(), tenure_months: '',
});

export default function Liabilities() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [liabilities, setLiabilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingLiability, setEditingLiability] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  // Editing a loan with an EMI: the balance fields start as the saved balance and date. The first rate, EMI or tenure
  // change moves them to the last EMI date and the outstanding then ('moved'), so the change isn't applied back to the
  // old date and a tenure counts the months left from there. Once the user sets the balance or its date themselves
  // ('typed'), theirs stands.
  const [anchorState, setAnchorState] = useState('stored');
  // The EMI came from a tenure the user typed, so it follows later balance and rate changes.
  const [tenureDriven, setTenureDriven] = useState(false);
  const [scheduleFor, setScheduleFor] = useState(null);
  const [error, setError] = useState('');
  const [pageError, setPageError] = useState(null);   // a list load or delete failure, shown on the page
  const [loaded, setLoaded] = useState(false);       // the list has loaded at least once
  const [submitting, setSubmitting] = useState(false);

  const fetchLiabilities = async () => {
    try {
      setLoading(true);
      const response = await liabilitiesAPI.getAll();
      setLiabilities(response.data);
      setLoaded(true);
      setPageError(null);
      updateLastUpdated();
    } catch (err) {
      setPageError({ message: errorMessage(err, 'Failed to load liabilities'), retry: true });
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
        description: liability.description || '',
        emi: liability.emi?.toString() ?? '',
        balance_date: liability.balance_date || todayIso(),
        tenure_months: liability.tenure_months?.toString() ?? ''
      });
    } else {
      setEditingLiability(null);
      setFormData(emptyForm());
    }
    setAnchorState('stored');
    setTenureDriven(false);
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingLiability(null);
    setFormData(emptyForm());
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
        description: formData.description || null,
        emi: formData.emi === '' ? null : parseFloat(formData.emi),
        balance_date: formData.balance_date || null,
        tenure_months: formData.tenure_months === '' ? null : parseInt(formData.tenure_months, 10)
      };

      if (editingLiability) {
        await liabilitiesAPI.update(editingLiability.id, data);
      } else {
        await liabilitiesAPI.create(data);
      }

      closeModal();
      fetchLiabilities();
    } catch (err) {
      setError(errorMessage(err, 'Failed to save liability'));
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
      setPageError({ message: errorMessage(err, 'Failed to delete liability'), retry: false });
    }
  };

  const formatCurrency = (value) => {
    if (privacyMode) return '₹ ••••••';
    return formatCurrencyRaw(value);
  };

  // Fill the EMI from a tenure, using the balance and rate already entered.
  const fillEmiFromTenure = (form) => {
    const principal = parseFloat(form.amount);
    const months = parseInt(form.tenure_months, 10);
    if (!(principal > 0) || !(months > 0)) return form;
    const emi = emiForTenure(principal, parseFloat(form.interest_rate) || 0, months);
    return Number.isFinite(emi) ? { ...form, emi: emi.toString() } : form;
  };

  // On the first rate, EMI or tenure change to a loan with an EMI, start from the last EMI date at the balance outstanding then.
  const reanchor = (form) => {
    if (anchorState !== 'stored' || !editingLiability?.amortized || !editingLiability.last_emi_date) return form;
    setAnchorState('moved');
    return { ...form, amount: editingLiability.outstanding.toString(), balance_date: editingLiability.last_emi_date };
  };

  const totalLiabilities = liabilities.reduce((sum, liability) => sum + liability.outstanding, 0);
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

      <PageError
        message={pageError?.message}
        onRetry={pageError?.retry ? fetchLiabilities : undefined}
        onDismiss={() => setPageError(null)}
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card bg-gradient-to-r from-orange-500 to-red-500 text-white">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-orange-100 font-medium">Total Liabilities</p>
              <p className="text-3xl font-bold mt-1">
                <AnimatedNumber 
                  value={totalLiabilities} 
                  formatter={formatShortINR}
                  privacyMask={!loaded ? '—' : privacyMode ? '₹ ••••••' : null}
                  title={loaded && !privacyMode ? formatCurrencyRaw(totalLiabilities) : undefined}
                />
              </p>
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
                <AnimatedNumber 
                  value={avgInterestRate || 0} 
                  formatter={(v) => v ? `${v.toFixed(1)}%` : 'N/A'}
                  privacyMask={loaded ? null : '—'}
                />
              </p>
            </div>
            <div className="w-16 h-16 bg-purple-100 dark:bg-purple-900/50 rounded-2xl flex items-center justify-center">
              <Percent className="w-8 h-8 text-purple-600 dark:text-purple-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Liabilities List */}
      {liabilities.length === 0 ? loaded && (
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
        <ItemTileGrid>
          {liabilities.map((liability) => {
            const categoryInfo = getCategoryInfo(liability.category);

            return (
              <ItemTile
                key={liability.id}
                icon={categoryInfo.icon}
                iconColor={categoryInfo.color}
                title={liability.name}
                subtitle={categoryInfo.label}
                badges={liability.interest_rate != null && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300">
                    {liability.interest_rate}% APR
                  </span>
                )}
                itemLabel={liability.name}
                actions={liability.amortized && !liability.emi_too_low && (
                  <TileAction label="Repayment schedule" onClick={() => setScheduleFor(liability)}>
                    <CalendarDays className="w-4 h-4" />
                  </TileAction>
                )}
                onEdit={() => openModal(liability)}
                onDelete={() => handleDelete(liability.id)}
                amountLabel="Outstanding"
                amount={formatCurrency(liability.outstanding)}
                amountValue={liability.outstanding}
                amountClassName="text-red-600 dark:text-red-400"
                privacyMode={privacyMode}
              >
                {liability.amortized && (
                  liability.emi_too_low ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <span>EMI {formatCurrency(liability.emi)}</span>
                      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300">
                        EMI doesn't cover the interest
                      </span>
                    </div>
                  ) : (
                    <>
                      <p>
                        <span className="font-medium text-gray-700 dark:text-gray-200">EMI {formatCurrency(liability.emi)}</span>
                        {liability.payoff_date && <> · paid off by {formatMonthYear(liability.payoff_date)}</>}
                      </p>
                      {liability.payoff_date && (
                        <p>{formatCurrency(liability.interest_remaining)} interest left</p>
                      )}
                      {liability.next_emi_interest != null && liability.next_emi_principal != null && (
                        <p>
                          Next EMI: {formatCurrency(liability.next_emi_interest)} interest + {formatCurrency(liability.next_emi_principal)} principal
                        </p>
                      )}
                    </>
                  )
                )}
                {liability.description && (
                  <p className="text-sm text-gray-400 dark:text-gray-500 line-clamp-2" title={liability.description}>{liability.description}</p>
                )}
              </ItemTile>
            );
          })}
        </ItemTileGrid>
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
                <label className="label">Balance (₹)</label>
                <input
                  type="number"
                  className="input"
                  placeholder="0.00"
                  min="0"
                  step="any"
                  value={formData.amount}
                  onChange={(e) => {
                    const next = { ...formData, amount: e.target.value, balance_date: todayIso() };
                    setAnchorState('typed');
                    setFormData(tenureDriven ? fillEmiFromTenure(next) : next);
                  }}
                  required
                />
                <AmountHint value={formData.amount} />
              </div>

              <div>
                <label className="label">Balance as of</label>
                <input
                  type="date"
                  className="input"
                  value={formData.balance_date}
                  onChange={(e) => {
                    setAnchorState('typed');
                    setFormData({ ...formData, balance_date: e.target.value });
                  }}
                />
              </div>
              {anchorState === 'moved' && (
                <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                  Rate, EMI and tenure changes apply from {formatDate(editingLiability.last_emi_date)}: the balance there is the outstanding on that date.
                </p>
              )}

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
                  step="any"
                  value={formData.interest_rate}
                  onChange={(e) => {
                    const next = reanchor({ ...formData, interest_rate: e.target.value });
                    setFormData(tenureDriven ? fillEmiFromTenure(next) : next);
                  }}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">EMI ₹/month (Optional)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="e.g., 52000"
                    min="0.01"
                    step="any"
                    value={formData.emi}
                    onChange={(e) => {
                      setTenureDriven(false);
                      setFormData(reanchor({ ...formData, emi: e.target.value, tenure_months: '' }));
                    }}
                  />
                  <AmountHint value={formData.emi} />
                </div>
                <div>
                  <label className="label">…or tenure (months)</label>
                  <input
                    type="number"
                    className="input"
                    placeholder="e.g., 240"
                    min="1"
                    max="600"
                    step="1"
                    value={formData.tenure_months}
                    onChange={(e) => {
                      const tenure_months = e.target.value;
                      setTenureDriven(true);
                      // Re-anchor first, so the EMI comes from the outstanding over the months left from the last EMI date.
                      const next = reanchor({ ...formData, tenure_months });
                      // The tenure filled the EMI, so emptying the tenure empties it again.
                      setFormData(tenure_months === '' ? { ...next, emi: '' } : fillEmiFromTenure(next));
                    }}
                  />
                </div>
              </div>
              <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                With an EMI, the balance goes down every month from the date above. Enter a tenure to work out the EMI.
              </p>

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

      {scheduleFor && (
        <LoanScheduleModal
          liability={scheduleFor}
          formatCurrency={formatCurrency}
          onClose={() => setScheduleFor(null)}
        />
      )}
    </div>
  );
}
