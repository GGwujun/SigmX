'use strict';

const TOKEN = /^sxrh_[0-9a-f]{48}$/;

function parseResearchDeepLink(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'sigmx:' || url.hostname !== 'research') return null;
    if (url.search || url.hash) return null;
    const parts = url.pathname.split('/').filter(Boolean);
    if (parts.length !== 1 || !TOKEN.test(parts[0])) return null;
    return parts[0];
  } catch {
    return null;
  }
}

module.exports = { parseResearchDeepLink };
