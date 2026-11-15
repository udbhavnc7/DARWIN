// Copies the recorded snapshots into the showcase build only, so the normal local build is unchanged.
import {cpSync, existsSync} from 'node:fs';

const source = new URL('../showcase/', import.meta.url);
if (!existsSync(source)) throw Error('frontend/showcase is missing. Run scripts/capture_showcase.py against a local stack first.');
cpSync(source, new URL('../dist/showcase/', import.meta.url), {recursive: true});
console.log('Copied showcase snapshots into dist/showcase');
