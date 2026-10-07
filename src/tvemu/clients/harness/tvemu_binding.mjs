// What a JavaScript client binding imports: steps, and the emulator's management API.
//
// The counterpart of tvemu_binding.py for clients installed from npm. It is copied beside
// the binding into the client's own workspace, uses only Node's standard library, and talks
// to the emulator the way any test would: over /api/v1.
//
//   import { Harness } from './tvemu_binding.mjs';
//
//   await Harness.main(async (harness) => {
//     await harness.step('press Home', 'key', async () => {
//       await client.keypress(Keys.HOME);
//       await harness.wait((state) => state.counts.Home === 1, 'Home counted');
//     });
//   });
//
// Each step is appended to the results file as one JSON line with the event ids it covers,
// exactly as the Python harness writes it, so the runner judges both the same way.
import { appendFileSync } from 'node:fs';

const DETAIL_LIMIT = 400;

export class Abort extends Error {}

export class Harness {
  constructor() {
    const env = process.env;
    this.deviceHost = env.TVEMU_DEVICE_HOST;
    this.devicePort = Number(env.TVEMU_DEVICE_PORT);
    this.profile = env.TVEMU_PROFILE;
    this.apiUrl = env.TVEMU_API.replace(/\/$/, '');
    this.workspace = env.TVEMU_WORKSPACE;
    this.results = env.TVEMU_RESULTS;
  }

  // -- the management API --------------------------------------------------------------------

  async call(method, path, body) {
    const init = { method };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { 'Content-Type': 'application/json' };
    }
    const response = await fetch(`${this.apiUrl}${path}`, init);
    if (!response.ok) throw new Error(`${method} ${path} answered ${response.status}`);
    const text = await response.text();
    if (path.endsWith('/export')) {
      return text.split('\n').filter((line) => line.trim()).map((line) => JSON.parse(line));
    }
    return JSON.parse(text);
  }

  state() { return this.call('GET', '/api/v1/state'); }

  async events(since = 0) {
    const events = await this.call('GET', '/api/v1/events/export');
    return events.filter((event) => Number(event.id || 0) > since);
  }

  action(name, data = {}) { return this.call('POST', `/api/v1/actions/${name}`, data); }

  settings(patch) { return this.call('PATCH', '/api/v1/settings', patch); }

  async lastEventId() {
    const events = (await this.state()).events || [];
    return events.length ? Number(events[events.length - 1].id) : 0;
  }

  // Poll the emulator's state until `predicate` holds for it.
  async wait(predicate, label, timeout = 5000) {
    const deadline = Date.now() + timeout;
    for (;;) {
      const state = await this.state();
      if (predicate(state)) return state;
      if (Date.now() >= deadline) throw new Error(`timed out waiting for ${label}`);
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }

  // -- steps ---------------------------------------------------------------------------------

  write(record) {
    appendFileSync(this.results, `${JSON.stringify(record)}\n`, 'utf8');
  }

  async step(name, action, body, { required = false } = {}) {
    const first = await this.lastEventId();
    const started = Date.now();
    const record = { name, action, status: 'ok', detail: '' };
    try {
      await body(record);
    } catch (error) {       // the step's verdict, not the binding's crash
      record.status = 'fail';
      record.detail = `${error?.name || 'Error'}: ${error?.message ?? error}`.slice(0, DETAIL_LIMIT);
    }
    record.events = [first, await this.lastEventId()];
    record.duration_ms = Date.now() - started;
    if (required && record.status === 'fail') record.required = true;
    this.write(record);
    if (record.required) throw new Abort(name);
  }

  // The client has no way to do this; a fact about the client, not a failure.
  notOffered(name, action, reason) {
    this.write({ name, action, status: 'not-offered', detail: reason, events: [0, 0], duration_ms: 0 });
  }

  static async main(body) {
    const harness = new Harness();
    try {
      await body(harness);
    } catch (error) {
      if (error instanceof Abort) {
        console.error(`stopped after required step ${error.message}`);
        process.exit(1);
      }
      throw error;
    }
  }
}

export function assert(condition, message) {
  if (!condition) throw Object.assign(new Error(message), { name: 'AssertionError' });
}
