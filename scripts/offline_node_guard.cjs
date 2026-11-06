// Process-local guard for the reviewed Node -e fixtures, not a hostile-code sandbox.
'use strict';
const deny = () => { throw new Error('Offline fixture access denied'); };
for (const [name, methods] of Object.entries({
  'node:net': ['connect', 'createConnection'],
  'node:tls': ['connect'],
  'node:http': ['request', 'get'],
  'node:https': ['request', 'get'],
  'node:dns': ['lookup', 'resolve'],
  'node:dgram': ['createSocket'],
  'node:child_process': ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync', 'fork'],
  'node:fs': ['readFile', 'readFileSync', 'writeFile', 'writeFileSync', 'appendFile', 'appendFileSync', 'open', 'openSync', 'createReadStream', 'createWriteStream', 'readdir', 'readdirSync'],
  'node:worker_threads': ['Worker'],
})) {
  const mod = require(name);
  for (const method of methods) mod[method] = deny;
}
const promises = require('node:fs/promises');
for (const method of ['readFile', 'writeFile', 'appendFile', 'open', 'readdir']) promises[method] = deny;
globalThis.fetch = deny;
