'use strict';
// Daily version notice for ALICE releases. The repo is a build setting so
// development copies do not contact ALICE or another publisher by default.
const DAY_MS = 86400000;
const TIMEOUT_MS = 8000;
const REPO_RE = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/;
const TAG_RE = /^alice-v(\d+)\.(\d+)\.(\d+)$/;

function cleanRepo(repo) { return REPO_RE.test(String(repo || '')) ? String(repo) : ''; }
function releasesPage(repo) { const r = cleanRepo(repo); return r ? 'https://github.com/' + r + '/releases' : null; }
function listUrl(repo) { const r = cleanRepo(repo); return r ? 'https://api.github.com/repos/' + r + '/releases?per_page=20' : null; }

function parse(version) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)/.exec(String(version || '').trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}
function newer(a, b) {
  const x = parse(a), y = parse(b);
  if (!x || !y) return false;
  for (let i = 0; i < 3; i++) { if (x[i] !== y[i]) return x[i] > y[i]; }
  return false;
}

function newestAlice(releases, repo) {
  const r = cleanRepo(repo);
  if (!r) return null;
  let best = null;
  for (const release of Array.isArray(releases) ? releases : []) {
    const match = TAG_RE.exec(String(release && release.tag_name || ''));
    if (!match || release.draft) continue;
    const version = match[1] + '.' + match[2] + '.' + match[3];
    if (!best || newer(version, best.version)) {
      const tag = release.tag_name;
      best = { version, tag, url: 'https://github.com/' + r + '/releases/tag/' + tag, notes: String(release.body || '').slice(0, 2000), publishedAt: release.published_at || null };
    }
  }
  return best;
}

function createUpdateCheck({ current, repo, store, fetchImpl = global.fetch, now = () => Date.now(), log = () => {} }) {
  const ownerRepo = cleanRepo(repo);
  function state() {
    const saved = (store.get && store.get('updateCheck')) || {};
    const available = ownerRepo && saved.version && newer(saved.version, current)
      ? { version: saved.version, url: saved.url, publishedAt: saved.publishedAt } : null;
    return { current, checkedAt: saved.checkedAt || null, available, dismissed: saved.dismissed === saved.version, configured: !!ownerRepo };
  }

  async function check(force = false) {
    if (!ownerRepo) return state();
    const saved = (store.get && store.get('updateCheck')) || {};
    if (!force && saved.checkedAt && now() - saved.checkedAt < DAY_MS) return state();
    try {
      const res = await fetchImpl(listUrl(ownerRepo), { headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'ALICE/' + current }, signal: typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(TIMEOUT_MS) : undefined });
      if (!res.ok) throw new Error('GitHub answered ' + res.status);
      const best = newestAlice(await res.json(), ownerRepo);
      const next = { checkedAt: now(), version: best ? best.version : null, url: best ? best.url : null, publishedAt: best ? best.publishedAt : null, dismissed: saved.dismissed || null };
      store.set('updateCheck', next);
      if (best && newer(best.version, current)) log('new ALICE version available: ' + best.version + ' (current ' + current + ')');
    } catch (error) {
      log('update check failed: ' + error.message);
      store.set('updateCheck', { ...saved, checkedAt: now() });
    }
    return state();
  }

  function adopt(info) {
    const saved = (store.get && store.get('updateCheck')) || {};
    store.set('updateCheck', { checkedAt: now(), version: info && info.version || null, url: info && info.url || releasesPage(ownerRepo), publishedAt: null, dismissed: saved.dismissed || null });
    return state();
  }
  function dismiss() { const saved = (store.get && store.get('updateCheck')) || {}; store.set('updateCheck', { ...saved, dismissed: saved.version || null }); return state(); }
  return { check, state, dismiss, adopt, RELEASES_PAGE: releasesPage(ownerRepo), repo: ownerRepo };
}

module.exports = { createUpdateCheck, newestAlice, newer, parse, cleanRepo, releasesPage, listUrl };
