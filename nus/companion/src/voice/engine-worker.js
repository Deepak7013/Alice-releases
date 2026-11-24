'use strict';

// Isolate Kokoro's native runtime so speech generation cannot block Electron's
// main process. Only Heart and Fable profiles are present in the bundled model.
const path = require('path');
const { OfflineTts } = require('sherpa-onnx-node');

let tts = null;
let sampleRate = 24000;
let stopped = false;

process.on('message', (message) => {
  if (!message) return;
  if (message.type === 'load') {
    try {
      const dir = String(message.dir || '');
      tts = new OfflineTts({
        model: {
          kokoro: {
            model: path.join(dir, 'model.onnx'),
            voices: path.join(dir, 'voices.bin'),
            tokens: path.join(dir, 'tokens.txt'),
            dataDir: path.join(dir, 'espeak-ng-data'),
            lexicon: [path.join(dir, 'lexicon-us-en.txt'), path.join(dir, 'lexicon-gb-en.txt')].join(','),
          },
        },
        numThreads: Math.max(1, Math.min(4, Number(message.threads) || 4)),
        provider: 'cpu',
      });
      sampleRate = tts.sampleRate || 24000;
      process.send({ type: 'ready', sampleRate, model: 'Kokoro Heart + Fable' });
    } catch (error) {
      process.send({ type: 'error', message: String(error && error.message || error) });
    }
    return;
  }
  if (message.type === 'stop') { stopped = true; return; }
  if (message.type !== 'say' || !tts) return;
  const id = message.id;
  stopped = false;
  try {
    const result = tts.generate({
      text: String(message.text || ''),
      sid: Math.max(0, Math.min(1, Number(message.speaker) || 0)),
      speed: Number(message.speed) > 0 ? Number(message.speed) : 1,
      // Electron disallows the native addon's zero-copy external ArrayBuffer.
      // Ask sherpa-onnx for an ordinary owned buffer before sending PCM onward.
      enableExternalBuffer: false,
    });
    if (stopped) { stopped = false; return; }
    const floats = result.samples || [];
    const pcm = Buffer.allocUnsafe(floats.length * 2);
    for (let i = 0; i < floats.length; i++) {
      const value = Math.max(-1, Math.min(1, Number(floats[i]) || 0));
      pcm.writeInt16LE(Math.round(value < 0 ? value * 32768 : value * 32767), i * 2);
    }
    // Buffers use external memory and Electron's advanced IPC serializer rejects
    // them in a forked worker. Base64 is a portable payload for these short clips.
    process.send({ type: 'audio', id, sampleRate: result.sampleRate || sampleRate, pcm: pcm.toString('base64'), secs: floats.length / (result.sampleRate || sampleRate) });
  } catch (error) {
      process.send({ type: 'error', id, message: String(error && error.message || error), stack: String(error && error.stack || '') });
  }
});

process.send({ type: 'hello' });
