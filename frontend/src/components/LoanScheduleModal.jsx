import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { liabilitiesAPI } from '../api';
import { errorMessage } from '../utils/errors';
import { formatMonthYear } from '../utils/dates';

export default function LoanScheduleModal({ liability, formatCurrency, onClose }) {
  const [schedule, setSchedule] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    liabilitiesAPI.schedule(liability.id)
      .then((response) => { if (!cancelled) setSchedule(response.data); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, 'Failed to load the schedule')); });
    return () => { cancelled = true; };
  }, [liability.id]);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-gray-800 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{liability.name} — repayment schedule</h2>
            {schedule?.payoff_date && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Paid off by {formatMonthYear(schedule.payoff_date)} · {formatCurrency(schedule.interest_remaining)} interest left
              </p>
            )}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg text-gray-500 dark:text-gray-400">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-6">
          {error && <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400 px-4 py-3 rounded-lg text-sm">{error}</div>}
          {!error && !schedule && <p className="text-sm text-gray-500 dark:text-gray-400">Loading…</p>}
          {schedule && schedule.rows.length === 0 && (
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {schedule.payoff_date ? 'This loan is paid off.' : 'The payoff is too far out to project.'}
            </p>
          )}
          {schedule && schedule.rows.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="font-medium pb-2">Year</th>
                  <th className="font-medium pb-2 text-right">Paid</th>
                  <th className="font-medium pb-2 text-right">Interest</th>
                  <th className="font-medium pb-2 text-right">Principal</th>
                  <th className="font-medium pb-2 text-right">Balance at year end</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-gray-100">
                {schedule.rows.map((row) => (
                  <tr key={row.year} className="border-t border-gray-100 dark:border-gray-700">
                    <td className="py-1.5">{row.year}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.paid)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.interest)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.principal)}</td>
                    <td className="py-1.5 text-right">{formatCurrency(row.closing_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
