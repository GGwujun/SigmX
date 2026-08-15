const test = require('node:test');
const assert = require('node:assert/strict');

const { parseResearchDeepLink } = require('../deep-link');

test('accepts only one opaque research handoff token', () => {
  assert.equal(parseResearchDeepLink('sigmx://research/sxrh_0123456789abcdef0123456789abcdef0123456789abcdef'), 'sxrh_0123456789abcdef0123456789abcdef0123456789abcdef');
  for (const value of [
    'https://research/sxrh_0123456789abcdef0123456789abcdef0123456789abcdef',
    'sigmx://other/sxrh_0123456789abcdef0123456789abcdef0123456789abcdef',
    'sigmx://research/sxrh_short',
    'sigmx://research/sxrh_0123456789abcdef0123456789abcdef0123456789abcdef?token=secret',
    'sigmx://research/sxrh_0123456789abcdef0123456789abcdef0123456789abcdef/extra',
  ]) assert.equal(parseResearchDeepLink(value), null);
});
