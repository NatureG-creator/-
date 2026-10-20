import test from 'node:test';
import assert from 'node:assert/strict';
import {viewerOptions} from '../apdl_viewer.mjs';

test('viewer selects current result and escapes task names',()=>{
 const jobs=[{id:'a',name:'<script>&"'},{id:'b',name:'构件B'}];
 const options=viewerOptions(jobs,'b');
 assert.equal(options.selected.id,'b');
 assert.match(options.html,/value="b" selected/);
 assert.doesNotMatch(options.html,/<script>/);
 assert.match(options.html,/&lt;script&gt;/);
});
test('empty and missing preferred tasks have sensible defaults',()=>{
 assert.equal(viewerOptions([],'b').selected,undefined);
 assert.equal(viewerOptions([{id:'a',name:'A'}],'b').selected.id,'a');
});
