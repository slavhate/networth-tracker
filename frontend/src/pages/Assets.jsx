import { useState, useEffect, useRef } from 'react';
import { assetsAPI, npsAPI } from '../api';
import { usePrivacy } from '../PrivacyContext';
import AnimatedNumber from '../components/AnimatedNumber';
import { formatShortINR } from '../utils/indianNumbers';
import PageError from '../components/PageError';
import AmountHint from '../components/AmountHint';
import NpsSchemesEditor, { schemeRowsError } from '../components/NpsSchemesEditor';
import NpsSchemeLines from '../components/NpsSchemeLines';
import ItemTile, { ItemTileGrid } from '../components/ItemTile';
import {
  Plus,
  X,
  Wallet
} from 'lucide-react';
import { errorMessage } from '../utils/errors';
import { todayIso, formatDate } from '../utils/dates';
import { ASSET_CATEGORIES, assetCategoryInfo } from '../utils/assetCategories';

// Suggested yearly change when a category is picked; the user can change or clear it.
const SUGGESTED_YEARLY_CHANGE = { vehicles: '-15', real_estate: '5' };

// Suggested yearly interest for the provident-fund categories (the current declared rates).
const SUGGESTED_INTEREST = { epf: '8.25', ppf: '7.1' };

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const emptyForm = () => ({
  name: '', value: '', category: 'cash', description: '', annual_change_rate: '', valuation_date: todayIso(),
  monthly_contribution: '', interest_rate: '', quantity: '', unit_price: '',
  yearly_contribution: '', yearly_contribution_month: '3', nps_schemes: [],
});

const formatCurrencyRaw = (value) => {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
};

export default function Assets() {
  const { privacyMode, updateLastUpdated } = usePrivacy();
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAsset, setEditingAsset] = useState(null);
  const [formData, setFormData] = useState(emptyForm);
  const [rateTouched, setRateTouched] = useState(false);
  const [interestTouched, setInterestTouched] = useState(false);
  // Editing a provident fund: the balance fields start as the saved balance and its date. The first contribution change
  // (or a switch to a category without contributions) moves them to today's value and today ('moved'), so the months
  // already passed keep the contribution they were credited with. Once the user sets the balance or its date
  // themselves ('typed'), theirs stands.
  const [anchorState, setAnchorState] = useState('stored');
  const [error, setError] = useState('');
  const [pageError, setPageError] = useState(null);   // a list load or delete failure, shown on the page
  const [loaded, setLoaded] = useState(false);       // the list has loaded at least once
  const [submitting, setSubmitting] = useState(false);
  const [npsSchemes, setNpsSchemes] = useState(null);       // the scheme list, once loaded
  const [npsSchemesError, setNpsSchemesError] = useState('');
  const [refreshingIds, setRefreshingIds] = useState([]);
  const [refreshErrors, setRefreshErrors] = useState({});   // asset id -> why its last manual NAV refresh failed
  const backgroundRefresh = useRef(false);

  const fetchAssets = async () => {
    try {
      setLoading(true);
      const response = await assetsAPI.getAll();
      setAssets(response.data);
      setLoaded(true);
      setPageError(null);
      refreshStaleNps(response.data);
      updateLastUpdated();
    } catch (err) {
      setPageError({ message: errorMessage(err, 'Failed to load assets'), retry: true });
    } finally {
      setLoading(false);
    }
  };

  // A manual refresh shows its failure on the asset's card and a success clears it; a quiet (background) refresh
  // neither sets nor clears a message.
  const refreshNav = async (id, { quiet = false } = {}) => {
    setRefreshingIds((ids) => [...ids, id]);
    try {
      const response = await assetsAPI.refreshNav(id);
      setAssets((list) => list.map((a) => (a.id === id ? response.data : a)));
      if (!quiet) {
        setRefreshErrors(({ [id]: _cleared, ...rest }) => rest);
      }
    } catch (err) {
      if (!quiet) {
        setRefreshErrors((errors) => ({ ...errors, [id]: errorMessage(err, 'Failed to refresh NAV') }));
      }
    } finally {
      setRefreshingIds((ids) => ids.filter((x) => x !== id));
    }
  };

  // NPS assets priced before today (or not at all) are refreshed one at a time after the list loads; failures are
  // quiet and the card keeps what it showed.
  const refreshStaleNps = async (list) => {
    if (backgroundRefresh.current) return;
    backgroundRefresh.current = true;
    try {
      for (const asset of list) {
        const stale = asset.category === 'nps' && asset.nps_schemes?.length
          && (!asset.nps_priced_through || asset.nps_priced_through < todayIso());
        if (stale) await refreshNav(asset.id, { quiet: true });
      }
    } finally {
      backgroundRefresh.current = false;
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
        description: asset.description || '',
        annual_change_rate: asset.annual_change_rate?.toString() ?? '',
        valuation_date: asset.valuation_date || todayIso(),
        monthly_contribution: asset.monthly_contribution?.toString() ?? '',
        interest_rate: asset.interest_rate?.toString() ?? '',
        quantity: asset.quantity?.toString() ?? '',
        unit_price: asset.unit_price?.toString() ?? '',
        yearly_contribution: asset.yearly_contribution?.toString() ?? '',
        yearly_contribution_month: asset.yearly_contribution_month?.toString() ?? '3',
        nps_schemes: (asset.nps_schemes || []).map((s) => ({
          scheme_code: s.scheme_code,
          scheme_name: s.scheme_name,
          allocation_pct: s.allocation_pct.toString(),
          units: s.units?.toString() ?? '',
        })),
      });
      setRateTouched(true);
      setInterestTouched(asset.interest_rate != null);
    } else {
      setEditingAsset(null);
      setFormData(emptyForm());
      setRateTouched(false);
      setInterestTouched(false);
    }
    setAnchorState('stored');
    setError('');
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setEditingAsset(null);
    setFormData(emptyForm());
  };

  const kind = assetCategoryInfo(formData.category).kind;
  const unit = assetCategoryInfo(formData.category).unit;

  // The scheme list is loaded the first time an NPS form opens, and kept for the rest of the visit.
  useEffect(() => {
    if (!modalOpen || kind !== 'nps' || npsSchemes) return;
    npsAPI.schemes()
      .then((response) => { setNpsSchemes(response.data); setNpsSchemesError(''); })
      .catch(() => setNpsSchemesError("The scheme list couldn't be loaded right now; existing options stay as they are."));
  }, [modalOpen, kind, npsSchemes]);

  const quantityValue = (() => {
    const q = parseFloat(formData.quantity);
    const p = parseFloat(formData.unit_price);
    return q > 0 && p >= 0 ? Math.round(q * p * 100) / 100 : null;
  })();
  const editingProvident = editingAsset != null && assetCategoryInfo(editingAsset.category).kind === 'provident';

  // The balance as the form shows it moves to what the asset is worth today, dated today.
  const todaysValueFields = () => ({ value: editingAsset.current_value.toString(), valuation_date: todayIso() });

  // On the first contribution change to a provident fund whose balance is dated before today, start from today's
  // value: replaying the months since the old date with the new contribution would rewrite them.
  const reanchorContribution = (form) => {
    if (anchorState !== 'stored' || !editingProvident) return form;
    if (!editingAsset.valuation_date || editingAsset.valuation_date >= todayIso()) return form;
    setAnchorState('moved');
    return { ...form, ...todaysValueFields() };
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      if (kind === 'nps') {
        const problem = schemeRowsError(formData.nps_schemes);
        if (problem) {
          setError(problem);
          setSubmitting(false);
          return;
        }
      }

      // Fields that don't apply to the chosen category are sent as null so a category change clears them.
      const num = (v) => (v === '' ? null : parseFloat(v));
      const data = {
        name: formData.name,
        category: formData.category,
        description: formData.description || null,
        value: kind === 'quantity' ? (quantityValue ?? 0) : parseFloat(formData.value),
        annual_change_rate: kind === 'provident' ? null : num(formData.annual_change_rate),
        valuation_date: formData.valuation_date || null,
        monthly_contribution: kind === 'provident' || kind === 'nps' ? num(formData.monthly_contribution) : null,
        yearly_contribution: kind === 'nps' ? num(formData.yearly_contribution) : null,
        yearly_contribution_month: kind === 'nps' && formData.yearly_contribution !== ''
          ? parseInt(formData.yearly_contribution_month, 10) : null,
        interest_rate: kind === 'provident' ? num(formData.interest_rate) : null,
        quantity: kind === 'quantity' ? num(formData.quantity) : null,
        unit_price: kind === 'quantity' ? num(formData.unit_price) : null,
        nps_schemes: kind === 'nps' && formData.nps_schemes.length
          ? formData.nps_schemes.map((r) => ({
            scheme_code: r.scheme_code,
            scheme_name: r.scheme_name,
            allocation_pct: parseFloat(r.allocation_pct),
            units: r.units === '' ? null : parseFloat(r.units),
          }))
          : null,
      };

      if (editingAsset) {
        await assetsAPI.update(editingAsset.id, data);
      } else {
        await assetsAPI.create(data);
      }

      closeModal();
      fetchAssets();
    } catch (err) {
      setError(errorMessage(err, 'Failed to save asset'));
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
      setPageError({ message: errorMessage(err, 'Failed to delete asset'), retry: false });
    }
  };

  const formatCurrency = (value) => {
    if (privacyMode) return '₹ ••••••';
    return formatCurrencyRaw(value);
  };

  const totalAssets = assets.reduce((sum, asset) => sum + asset.current_value, 0);

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

      <PageError
        message={pageError?.message}
        onRetry={pageError?.retry ? fetchAssets : undefined}
        onDismiss={() => setPageError(null)}
      />

      {/* Summary Card */}
      <div className="card bg-gradient-to-r from-primary-500 to-primary-600 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-primary-100 font-medium">Total Assets Value</p>
            <p className="text-3xl font-bold mt-1">
              <AnimatedNumber 
                value={totalAssets} 
                formatter={formatShortINR}
                privacyMask={!loaded ? '—' : privacyMode ? '₹ ••••••' : null}
                title={loaded && !privacyMode ? formatCurrencyRaw(totalAssets) : undefined}
              />
            </p>
          </div>
          <div className="w-16 h-16 bg-white/20 rounded-2xl flex items-center justify-center">
            <Wallet className="w-8 h-8" />
          </div>
        </div>
      </div>

      {/* Assets List */}
      {assets.length === 0 ? loaded && (
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
        <ItemTileGrid>
          {assets.map((asset) => {
            const categoryInfo = assetCategoryInfo(asset.category);

            return (
              <ItemTile
                key={asset.id}
                icon={categoryInfo.icon}
                iconColor={categoryInfo.color}
                title={asset.name}
                subtitle={categoryInfo.label}
                itemLabel={asset.name}
                onEdit={() => openModal(asset)}
                onDelete={() => handleDelete(asset.id)}
                amountLabel="Current value"
                amount={formatCurrency(asset.current_value)}
                amountValue={asset.current_value}
                privacyMode={privacyMode}
              >
                {categoryInfo.kind === 'provident' && asset.interest_rate != null && asset.valuation_date && (
                  <p>
                    {formatCurrency(asset.value)} on {formatDate(asset.valuation_date)} · +{formatCurrency(asset.monthly_contribution || 0)}/month at {asset.interest_rate}%
                  </p>
                )}
                {categoryInfo.kind === 'quantity' && asset.quantity != null && asset.unit_price != null && (
                  <p>
                    {privacyMode ? '••' : asset.quantity} {categoryInfo.unit} × {formatCurrency(asset.unit_price)}/{categoryInfo.unit === 'g' ? 'g' : 'unit'}
                  </p>
                )}
                {categoryInfo.kind === 'nps' && asset.valuation_date
                  && (asset.monthly_contribution > 0 || asset.yearly_contribution > 0 || asset.annual_change_rate != null) && (
                  <p>
                    {formatCurrency(asset.value)} on {formatDate(asset.valuation_date)}
                    {asset.monthly_contribution > 0 ? ` · +${formatCurrency(asset.monthly_contribution)}/month` : ''}
                    {asset.yearly_contribution > 0 ? ` · +${formatCurrency(asset.yearly_contribution)} every ${MONTHS[(asset.yearly_contribution_month || 3) - 1]}` : ''}
                    {asset.annual_change_rate != null ? ` · ${asset.annual_change_rate}%/yr expected` : ''}
                  </p>
                )}
                {categoryInfo.kind === 'nps' && asset.nps_schemes?.length > 0 && (
                  <NpsSchemeLines
                    asset={asset}
                    formatCurrency={formatCurrency}
                    privacyMode={privacyMode}
                    refreshing={refreshingIds.includes(asset.id)}
                    refreshError={refreshErrors[asset.id]}
                    onRefresh={(id) => refreshNav(id)}
                  />
                )}
                {categoryInfo.kind !== 'nps' && asset.annual_change_rate != null && asset.valuation_date && (
                  <p>
                    {formatCurrency(asset.value)} on {formatDate(asset.valuation_date)} · {asset.annual_change_rate > 0 ? '+' : ''}{asset.annual_change_rate}%/yr
                  </p>
                )}
                {asset.description && (
                  <p className="text-sm text-gray-400 dark:text-gray-500 line-clamp-2" title={asset.description}>{asset.description}</p>
                )}
              </ItemTile>
            );
          })}
        </ItemTileGrid>
      )}

      {/* Modal */}
      {modalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
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
                <label className="label">Category</label>
                <select
                  className="input"
                  value={formData.category}
                  onChange={(e) => {
                    const category = e.target.value;
                    // Leaving a provident fund or NPS keeps the value the user saw, not the balance it was anchored on.
                    const savedKind = editingAsset ? assetCategoryInfo(editingAsset.category).kind : null;
                    const keepsTodaysValue = anchorState === 'stored'
                      && (savedKind === 'provident' || savedKind === 'nps')
                      && assetCategoryInfo(category).kind !== savedKind;
                    if (keepsTodaysValue) setAnchorState('moved');
                    setFormData((f) => ({
                      ...f,
                      category,
                      ...(keepsTodaysValue ? todaysValueFields() : {}),
                      ...(rateTouched ? {} : { annual_change_rate: SUGGESTED_YEARLY_CHANGE[category] ?? '' }),
                      ...(interestTouched ? {} : { interest_rate: SUGGESTED_INTEREST[category] ?? '' }),
                    }));
                  }}
                >
                  {ASSET_CATEGORIES.map((cat) => (
                    <option key={cat.value} value={cat.value}>
                      {cat.label}
                    </option>
                  ))}
                </select>
              </div>

              {!kind && (
                <>
                  <div>
                    <label className="label">Value (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0"
                      step="0.01"
                      value={formData.value}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, value: e.target.value, valuation_date: todayIso() });
                      }}
                      required
                    />
                    <AmountHint value={formData.value} />
                  </div>

                  <div>
                    <label className="label">Value as of</label>
                    <input
                      type="date"
                      className="input"
                      value={formData.valuation_date}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, valuation_date: e.target.value });
                      }}
                    />
                  </div>
                </>
              )}

              {kind === 'provident' && (
                <>
                  <div>
                    <label className="label">Balance (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0"
                      step="0.01"
                      value={formData.value}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, value: e.target.value, valuation_date: todayIso() });
                      }}
                      required
                    />
                    <AmountHint value={formData.value} />
                  </div>

                  <div>
                    <label className="label">Balance as of</label>
                    <input
                      type="date"
                      className="input"
                      value={formData.valuation_date}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, valuation_date: e.target.value });
                      }}
                    />
                  </div>
                  {anchorState === 'moved' && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                      Contribution changes apply from today: the balance is today's value.
                    </p>
                  )}

                  <div>
                    <label className="label">Monthly contribution (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0"
                      step="any"
                      value={formData.monthly_contribution}
                      onChange={(e) => setFormData(reanchorContribution({ ...formData, monthly_contribution: e.target.value }))}
                    />
                    <AmountHint value={formData.monthly_contribution} />
                  </div>

                  <div>
                    <label className="label">Interest rate (% p.a.)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="e.g., 8.25"
                      min="0"
                      max="100"
                      step="any"
                      value={formData.interest_rate}
                      onChange={(e) => {
                        setInterestTouched(true);
                        setFormData({ ...formData, interest_rate: e.target.value });
                      }}
                      required
                    />
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                      Use the passbook or statement balance on the Balance as of date, including interest earned up to then; contributions count from the following month. Interest is added monthly on the running balance and credited every 31 March, as EPFO and PPF do. A rate change applies from the Balance as of date.
                    </p>
                  </div>
                </>
              )}

              {kind === 'nps' && (
                <>
                  <div>
                    <label className="label">Balance (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0"
                      step="0.01"
                      value={formData.value}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, value: e.target.value });
                      }}
                      required
                    />
                    <AmountHint value={formData.value} />
                  </div>

                  <div>
                    <label className="label">Balance as of (statement date)</label>
                    <input
                      type="date"
                      className="input"
                      max={todayIso()}
                      value={formData.valuation_date}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, valuation_date: e.target.value });
                      }}
                    />
                  </div>

                  <div>
                    <label className="label">Employer contribution ₹/month (Optional)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="From your salary"
                      min="0"
                      step="any"
                      value={formData.monthly_contribution}
                      onChange={(e) => setFormData({ ...formData, monthly_contribution: e.target.value })}
                    />
                    <AmountHint value={formData.monthly_contribution} />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="label">Own contribution ₹/year</label>
                      <input
                        type="number"
                        className="input"
                        placeholder="Optional"
                        min="0"
                        step="any"
                        value={formData.yearly_contribution}
                        onChange={(e) => setFormData({ ...formData, yearly_contribution: e.target.value })}
                      />
                      <AmountHint value={formData.yearly_contribution} />
                    </div>
                    <div>
                      <label className="label">Paid in</label>
                      <select
                        className="input"
                        value={formData.yearly_contribution_month}
                        onChange={(e) => setFormData({ ...formData, yearly_contribution_month: e.target.value })}
                      >
                        {MONTHS.map((month, i) => <option key={month} value={i + 1}>{month}</option>)}
                      </select>
                    </div>
                  </div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 !mt-1">
                    Contributions are counted on the 1st of each month from the month after the balance date.
                  </p>

                  <NpsSchemesEditor
                    rows={formData.nps_schemes}
                    onChange={(nps_schemes) => setFormData((f) => ({ ...f, nps_schemes }))}
                    schemes={npsSchemes}
                    schemesError={npsSchemesError}
                  />
                </>
              )}

              {kind === 'quantity' && (
                <>
                  <div>
                    <label className="label">Quantity ({unit === 'g' ? 'grams' : 'units'})</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0"
                      min="0.0001"
                      step="any"
                      value={formData.quantity}
                      onChange={(e) => setFormData({ ...formData, quantity: e.target.value, valuation_date: todayIso() })}
                      required
                    />
                  </div>

                  <div>
                    <label className="label">Price per {unit === 'g' ? 'gram' : 'unit'} (₹)</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="0.00"
                      min="0"
                      step="any"
                      value={formData.unit_price}
                      onChange={(e) => setFormData({ ...formData, unit_price: e.target.value, valuation_date: todayIso() })}
                      required
                    />
                  </div>

                  <div>
                    <label className="label">Price as of</label>
                    <input
                      type="date"
                      className="input"
                      value={formData.valuation_date}
                      onChange={(e) => {
                        setAnchorState('typed');
                        setFormData({ ...formData, valuation_date: e.target.value });
                      }}
                    />
                  </div>

                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Value: {formatCurrency(quantityValue ?? 0)}
                  </p>
                </>
              )}

              {kind !== 'provident' && (
                <div>
                  <label className="label">
                    {kind === 'nps' ? 'Expected return % per year (Optional)' : 'Yearly change % (Optional)'}
                  </label>
                  <input
                    type="number"
                    className="input"
                    placeholder={kind === 'nps' ? 'e.g., 10' : 'e.g., -15 for a car, 5 for property'}
                    min="-99"
                    max="100"
                    step="any"
                    value={formData.annual_change_rate}
                    onChange={(e) => {
                      setRateTouched(true);
                      setFormData({ ...formData, annual_change_rate: e.target.value });
                    }}
                  />
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                    {kind === 'nps'
                      ? "Used for the balance and contributions while NAVs aren't available."
                      : 'The value is adjusted every day at this yearly rate, starting from the date above.'}
                  </p>
                </div>
              )}

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
