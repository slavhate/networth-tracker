// Save a Blob as a file through a temporary object URL.
export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // Revoke later: some browsers (Safari) cancel the download if the URL disappears right after the click
  setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
}

// Save a value as a pretty-printed JSON file.
export function downloadJson(data, filename) {
  downloadBlob(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }), filename);
}
