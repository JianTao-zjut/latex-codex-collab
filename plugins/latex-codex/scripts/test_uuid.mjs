import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {randomUUID} from './vendor/latex-uuid.mjs';

assert.equal(randomUUID({randomUUID: () => 'native-id'}), 'native-id');
// Simulate insecure HTTP: randomUUID is absent, but secure random bytes remain available.
const insecure = {getRandomValues: bytes => webcrypto.getRandomValues(bytes)};
const ids = Array.from({length:1000}, () => randomUUID(insecure));
assert.equal(new Set(ids).size, ids.length);
for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
assert.equal(randomUUID({getRandomValues: bytes => bytes.fill(0)}), '00000000-0000-4000-8000-000000000000');
assert.throws(() => randomUUID({}), /Web Crypto is unavailable/);
for (const file of ['latex-chat.mjs','latex-history.mjs','latex-themes.mjs']) {
  const source = readFileSync(new URL('./vendor/'+file,import.meta.url),'utf8');
  assert.ok(source.includes("from './latex-uuid.mjs'"));
  assert.ok(!source.includes('crypto.randomUUID('));
}
console.log('UUID compatibility checks passed.');
