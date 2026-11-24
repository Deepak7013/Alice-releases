'use strict';
// ALICE's two bundled local voices: Heart (US English) and Fable (British).
// They share one Kokoro model and a trimmed two-speaker voice table.
// The model can also be downloaded once as a repair path.
//
// Lines are synthesized one at a time in order; the renderer plays line N
// while line N+1 is being made, so a streamed reply sounds continuous. stop()
// drops everything queued and whatever the worker is in the middle of.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const https = require('https');
const { spawn, execFile } = require('child_process');

// The sherpa-onnx packaging of hexgrad's Kokoro-82M v1.0 (Apache-2.0 weights).
// The bundled ONNX metadata and voices.bin contain only these two profiles:
// Heart is speaker 0 and Fable is speaker 1.
const MODELS = {
  // Both selected voices share this compacted package. No unused voice profile
  // files are downloaded at runtime.
  'kokoro-v1_0': { folder: 'kokoro-multi-lang-v1_0', bytes: 356930405 },
};
const VOICES = {
  heart: { model: 'kokoro-v1_0', speaker: 0, label: 'Heart (US female)', speed: 1.0 },
  fable: { model: 'kokoro-v1_0', speaker: 1, label: 'Fable (British)', speed: 1.0 },
};
const DEFAULT_VOICE = 'heart';
// The worker goes away after 30 quiet minutes (the model is ~300 MB in
// memory). At five, the first line after a short break paid the reload.
const IDLE_UNLOAD_MS = 30 * 60 * 1000;

function sha256File(file) {
  return new Promise((resolve, reject) => {
    const h = crypto.createHash('sha256');
    fs.createReadStream(file).on('data', (d) => h.update(d)).on('end', () => resolve(h.digest('hex'))).on('error', reject);
  });
}

function download(url, file, onProgress, redirects = 0) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { 'User-Agent': 'nus-companion' } }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location && redirects < 5) { res.resume(); download(res.headers.location, file, onProgress, redirects + 1).then(resolve, reject); return; }
      if (res.statusCode !== 200) { res.resume(); reject(new Error('download failed: HTTP ' + res.statusCode)); return; }
      const total = Number(res.headers['content-length']) || 0;
      let got = 0;
      const out = fs.createWriteStream(file + '.part');
      res.on('data', (chunk) => { got += chunk.length; if (onProgress) onProgress(got, total); });
      res.pipe(out);
      out.on('finish', () => { fs.rename(file + '.part', file, (e) => (e ? reject(e) : resolve(file))); });
      out.on('error', reject);
      res.on('error', reject);
    });
    req.on('error', reject);
  });
}

// Unpacking the voice. Windows ships its own tar (System32, libarchive), which reads .tar.bz2
// and takes C:\ paths. A plain "tar" is whichever comes first on the PATH, and on a PC with Git
// or MSYS ahead of System32 that is GNU tar, which reads "C:" as the name of another computer:
// "Cannot connect to C: resolve failed", and the voice never installs (found 2026-11-11 on a
// first-run walk started from a Git shell; one user reported "voice would not download" with
// no cause found). So Windows' own tar is called by its full path; the PATH's tar is the
// fallback, first as it is, then told that C: is local.
function tarAttempts({ platform = process.platform, env = process.env, exists = fs.existsSync } = {}) {
  const tries = [];
  if (platform === 'win32') {
    const own = path.join(env.SystemRoot || env.windir || 'C:\\Windows', 'System32', 'tar.exe');
    if (exists(own)) tries.push({ file: own, extra: [] });
  }
  tries.push({ file: 'tar', extra: [] });
  if (platform === 'win32') tries.push({ file: 'tar', extra: ['--force-local'] });
  return tries;
}
function extract(archive, into, { run = execFile, attempts = tarAttempts() } = {}) {
  fs.mkdirSync(into, { recursive: true });
  const one = (t) => new Promise((resolve, reject) => {
    run(t.file, [...t.extra, '-xjf', archive, '-C', into], { windowsHide: true, timeout: 600000 }, (e, _out, err) => (e ? reject(new Error('extract failed: ' + String(err || e.message).slice(0, 200))) : resolve()));
  });
  return attempts.reduce((before, t) => before.catch(() => one(t)), Promise.reject(new Error('extract failed: no tar')));
}

// electron: process.execPath runs the worker with ELECTRON_RUN_AS_NODE (the
// native addon is N-API, so it loads in Electron's Node as it does in Node).
// Fable ships inside the installer (Pranav, 2026-11-11: "the first word it says should already have
// the fable voice ... it doesn't need the step of downloading the voice anymore"): electron-builder
// copies vendor/voice/<folder> to resources/voice/<folder>. A dev run reads vendor/voice. The
// download in install() stays only as a repair path for an install whose bundled copy is missing.
function bundledRoots() {
  const out = [];
  if (process.resourcesPath) out.push(path.join(process.resourcesPath, 'voice'));
  out.push(path.join(__dirname, '..', '..', '..', 'vendor', 'voice'));
  return out;
}
function hasModel(d) { return fs.existsSync(path.join(d, 'voices.bin')) && (fs.existsSync(path.join(d, 'model.onnx')) || fs.existsSync(path.join(d, 'model.int8.onnx'))); }

function createVoice({ userData, settings, log = () => {}, spawnFn = spawn, executable = process.execPath, now = () => Date.now(), onState = () => {}, bundled = bundledRoots() }) {
  const root = path.join(userData, 'voice');
  let worker = null, ready = null, seq = 0, idleTimer = null, loading = null;
  const pending = new Map();      // id -> { resolve, reject, at }
  let downloading = null;         // { got, total, voice }

  // Only Heart and Fable are selectable local voices. Speech stays silent if
  // local synthesis is unavailable; ALICE never switches to Windows voices.
  function voiceName() { const s = settings.get(); if (s && (s.voice === 'heart' || s.voice === 'fable')) return String(s.voice); return DEFAULT_VOICE; }
  function wanted() { return VOICES[voiceName()] || null; }
  // The bundled copy when it is there, else a downloaded one in the profile.
  function modelDir(v) {
    const folder = MODELS[v.model].folder;
    for (const r of bundled || []) { const d = path.join(r, folder); if (hasModel(d)) return d; }
    return path.join(root, folder);
  }
  function installed(v) { return hasModel(modelDir(v)); }

  // Earlier ALICE/ALICE installs could leave all 54 Kokoro profiles and the
  // downloaded archive in userData. Once the two-profile bundled model is
  // verified, remove only that legacy speech-model folder/archive. This does
  // not touch settings, transcripts, or any other user data.
  function pruneLegacyVoices() {
    const bundledModel = (bundled || []).map(r => path.join(r, MODELS['kokoro-v1_0'].folder)).find(hasModel);
    if (!bundledModel) return;
    const legacy = path.join(root, MODELS['kokoro-v1_0'].folder);
    if (path.resolve(legacy) !== path.resolve(bundledModel) && fs.existsSync(legacy)) {
      try { fs.rmSync(legacy, { recursive: true, force: true }); log('removed legacy Kokoro package with unused voice profiles'); } catch (e) { log('legacy voice cleanup skipped: ' + e.message); }
    }
    for (const name of ['kokoro-multi-lang-v1_0.tar.bz2', 'kokoro-multi-lang-v1_0.tar.bz2.part']) {
      const file = path.join(root, name);
      try { if (fs.existsSync(file)) fs.unlinkSync(file); } catch (_) { /* optional cleanup */ }
    }
  }
  pruneLegacyVoices();

  function status() {
    const v = wanted();
    return {
      voice: voiceName(), label: v ? v.label : 'System voice', available: Object.keys(VOICES),
      installed: v ? installed(v) : false, ready: Boolean(v && installed(v) && worker && ready && ready.ok),
      downloading: downloading ? { got: downloading.got, total: downloading.total } : null,
      modelBytes: v ? MODELS[v.model].bytes : 0,
    };
  }
  function announce() { try { onState(status()); } catch (_) { /* a listener, never a failure */ } }

  // The one-time download for the chosen voice. Resolves to status().
  async function install(name) {
    const v = VOICES[name || DEFAULT_VOICE];
    if (!v) throw new Error('unknown voice');
    if (installed(v)) return status();
    throw new Error('The bundled voice files are missing. Repair or reinstall ALICE to restore Heart and Fable.');
  }

  function ensureWorker() {
    const v = wanted();
    if (!v || !installed(v)) return null;
    if (worker) return loading || Promise.resolve(worker);
    const env = { ...process.env, ELECTRON_RUN_AS_NODE: '1' };
    // The worker exchanges JSON-safe strings and numbers (PCM is base64). JSON
    // IPC also avoids Electron's advanced serializer rejecting external buffers
    // returned by the native Kokoro addon.
    const w = spawnFn(executable, [path.join(__dirname, 'engine-worker.js')], { env, windowsHide: true, stdio: ['ignore', 'ignore', 'ignore', 'ipc'], serialization: 'json' });
    worker = w; ready = null;
    loading = new Promise((resolve, reject) => {
      const t0 = now();
      const fail = (e) => { if (worker === w) { worker = null; ready = null; loading = null; } for (const p of pending.values()) p.reject(e); pending.clear(); announce(); reject(e); };
      w.on('error', (e) => fail(e));
      w.on('exit', () => fail(new Error('voice worker exited')));
      w.on('message', (m) => {
        if (!m) return;
        if (m.type === 'hello') { w.send({ type: 'load', dir: modelDir(v), speaker: v.speaker, threads: 4 }); return; }
        if (m.type === 'ready') { ready = { ok: true, sampleRate: m.sampleRate, ms: m.ms }; loading = null; log('voice ready in ' + (now() - t0) + 'ms (' + m.model + ')'); announce(); resolve(w); return; }
        if (m.type === 'audio') { const p = pending.get(m.id); if (p) { pending.delete(m.id); const pcm = Buffer.isBuffer(m.pcm) ? Buffer.from(m.pcm) : Buffer.from(String(m.pcm || ''), 'base64'); p.resolve({ sampleRate: m.sampleRate, pcm, ms: m.ms, secs: m.secs }); } touch(); return; }
        if (m.type === 'error') { const p = m.id != null ? pending.get(m.id) : null; if (p) { pending.delete(m.id); p.reject(new Error(m.message + (m.stack ? '\n' + m.stack : ''))); } else if (!ready) fail(new Error(m.message + (m.stack ? '\n' + m.stack : ''))); else log('voice: ' + m.message); }
      });
    });
    return loading;
  }

  function touch() { clearTimeout(idleTimer); idleTimer = setTimeout(() => { if (worker && !pending.size) { log('voice idle, unloading'); close(); } }, IDLE_UNLOAD_MS); if (idleTimer.unref) idleTimer.unref(); }

  // Warm the voice (load the model) ahead of the first line.
  async function warm() { try { await ensureWorker(); } catch (e) { log('voice warm failed: ' + e.message); } }

  // One line -> { sampleRate, pcm (Int16 LE bytes), ms, secs }. Rejects when the
  // voice is off, not installed, or the line was cut off by stop().
  let stopSeq = 0;
  async function synth(text) {
    const v = wanted();
    if (!v) throw new Error('No bundled ALICE local voice is selected. Choose Heart or Fable in Settings.');
    const gen = stopSeq;
    const w = await ensureWorker();
    if (!w) throw new Error('voice not installed');
    if (gen !== stopSeq) throw new Error('stopped');       // a stop() landed while the model was loading
    const id = ++seq;
    touch();
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject, at: now() });
      try { w.send({ type: 'say', id, text: String(text || ''), speaker: v.speaker, speed: v.speed }); } catch (e) { pending.delete(id); reject(e); }
    });
  }

  function stop() {
    stopSeq++;
    for (const p of pending.values()) p.reject(new Error('stopped'));
    pending.clear();
    if (worker) { try { worker.send({ type: 'stop' }); } catch (_) { /* gone */ } }
  }

  function close() { stop(); clearTimeout(idleTimer); if (worker) { try { worker.kill(); } catch (_) { /* gone */ } worker = null; ready = null; loading = null; } }

  // One instance is made before the sign-in window (to load Fable while the person signs in) and
  // handed to the companion, which sets its own listener here.
  function setOnState(fn) { onState = typeof fn === 'function' ? fn : () => {}; announce(); }
  return { status, install, warm, synth, stop, close, setOnState, modelDir: () => { const v = wanted(); return v ? modelDir(v) : ''; }, idle: () => !pending.size, VOICES, MODELS };
}

module.exports = { createVoice, bundledRoots, VOICES, MODELS, DEFAULT_VOICE, IDLE_UNLOAD_MS, sha256File, extract, tarAttempts, download };
