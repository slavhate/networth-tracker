// How often the dashboard saves an automatic snapshot; `phrase` completes a sentence such as
// "A snapshot is saved automatically once a month".
export const SNAPSHOT_FREQUENCIES = [
  { value: 'weekly', label: 'Weekly', phrase: 'every week' },
  { value: 'fortnightly', label: 'Every 2 weeks', phrase: 'every 2 weeks' },
  { value: 'monthly', label: 'Monthly', phrase: 'once a month' },
  { value: 'quarterly', label: 'Quarterly', phrase: 'once a quarter' },
];

const DEFAULT_SNAPSHOT_FREQUENCY = 'monthly';

// Unknown or missing values (older responses) fall back to the default
export const snapshotFrequency = (value) =>
  SNAPSHOT_FREQUENCIES.find((f) => f.value === value)
  || SNAPSHOT_FREQUENCIES.find((f) => f.value === DEFAULT_SNAPSHOT_FREQUENCY);
