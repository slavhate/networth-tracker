// FastAPI puts a human-readable message in `detail`; validation errors (422) carry an array of
// { loc, msg } objects instead, shown here as "field: message; field: message".
export const errorMessage = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d) => {
        const field = Array.isArray(d?.loc) ? d.loc.filter((part) => part !== 'body').join('.') : '';
        const msg = typeof d?.msg === 'string' ? d.msg : 'Invalid value';
        return field ? `${field}: ${msg}` : msg;
      })
      .join('; ');
  }
  return fallback;
};
