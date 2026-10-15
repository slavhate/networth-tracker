import { createContext, useContext, useState, useEffect } from 'react';

const PrivacyContext = createContext(null);

export function PrivacyProvider({ children }) {
  // Storage can be unavailable or hold a corrupt value (manual edit, extension); fall back to defaults
  const [privacyMode, setPrivacyMode] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('privacyMode'));
      // Default to true (privacy on) if not set
      return typeof saved === 'boolean' ? saved : true;
    } catch {
      return true;
    }
  });

  const [lastUpdated, setLastUpdated] = useState(() => {
    try {
      const saved = localStorage.getItem('lastUpdated');
      const date = saved ? new Date(saved) : null;
      return date && !Number.isNaN(date.getTime()) ? date : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('privacyMode', JSON.stringify(privacyMode));
    } catch {
      // storage unavailable - the choice just won't persist
    }
  }, [privacyMode]);

  const togglePrivacyMode = () => setPrivacyMode(!privacyMode);

  const updateLastUpdated = () => {
    const now = new Date();
    setLastUpdated(now);
    try {
      localStorage.setItem('lastUpdated', now.toISOString());
    } catch {
      // storage unavailable
    }
  };

  return (
    <PrivacyContext.Provider value={{
      privacyMode,
      togglePrivacyMode,
      lastUpdated,
      updateLastUpdated
    }}>
      {children}
    </PrivacyContext.Provider>
  );
}

export function usePrivacy() {
  const context = useContext(PrivacyContext);
  if (!context) {
    throw new Error('usePrivacy must be used within a PrivacyProvider');
  }
  return context;
}
