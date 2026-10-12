// FastAPI puts a human-readable message in `detail`; validation errors (422) carry an array instead.
export const errorMessage = (err, fallback) => {
  const detail = err.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
};
