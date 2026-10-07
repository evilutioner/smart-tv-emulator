// roku-client (npm) against the Roku emulator, through the library's public API only.
//
// The Node.js ECP client: device-info, apps, active app and media player queries, keys
// pressed, held and released, text, launches, the chained command builder, icons and search.
import { RokuClient, Keys } from 'roku-client';

import { Harness, assert } from './tvemu_binding.mjs';

// roku-client's constant for each navigation key, and the ECP key it sends.
const KEYS = [
  [Keys.HOME, 'Home'], [Keys.UP, 'Up'], [Keys.DOWN, 'Down'], [Keys.LEFT, 'Left'],
  [Keys.RIGHT, 'Right'], [Keys.SELECT, 'Select'], [Keys.BACK, 'Back'], [Keys.PLAY, 'Play'],
  [Keys.REVERSE, 'Rev'], [Keys.FORWARD, 'Fwd'], [Keys.INSTANT_REPLAY, 'InstantReplay'],
  [Keys.INFO, 'Info'], [Keys.BACKSPACE, 'Backspace'], [Keys.ENTER, 'Enter'],
];
const TEXT = 'tvemu42';

const count = (state, key) => state.counts[key] || 0;
const heldKey = (state, key) => JSON.stringify(state.held_keys).includes(key);

await Harness.main(async (harness) => {
  const roku = new RokuClient(`http://${harness.deviceHost}:${harness.devicePort}`);
  let info;

  await harness.step('device-info and the app list', 'identify', async () => {
    info = await roku.info();
    const expected = (await harness.state()).device;
    assert(info.modelNumber === expected.model_number, `model ${info.modelNumber}`);
    assert(info.softwareVersion === expected.software_version, `version ${info.softwareVersion}`);
    assert((await roku.apps()).length > 0, 'no applications parsed');
  }, { required: true });

  const isTv = info.isTv === true;

  await harness.step('active app and media player state', 'query-state', async () => {
    // The home screen is an <app> with no id, which this client reports as no app at all.
    await roku.active();
    const media = await roku.mediaPlayer();
    assert(media && typeof media.state === 'string', `media ${JSON.stringify(media)}`);
  });

  await harness.step('navigation and playback keys', 'key', async () => {
    for (const [key, name] of KEYS) {
      const before = count(await harness.state(), name);
      await roku.keypress(key);
      await harness.wait((state) => count(state, name) === before + 1, `${name} counted`);
    }
  });

  await harness.step('long key press, held then released', 'key-long', async () => {
    await roku.keydown(Keys.LEFT);
    await harness.wait((state) => heldKey(state, 'Left'), 'Left held');
    await roku.keyup(Keys.LEFT);
    await harness.wait((state) => !heldKey(state, 'Left'), 'Left released');
  });

  await harness.step(`text ${JSON.stringify(TEXT)}`, 'text', async () => {
    const since = await harness.lastEventId();
    await roku.text(TEXT);
    const arrived = (await harness.events(since))
      .filter((event) => event.kind === 'command' && event.status === 200)
      .map((event) => event.operation);
    const wanted = [...TEXT].map((char) => `keypress/Lit_${char}`);
    assert(JSON.stringify(arrived) === JSON.stringify(wanted), `arrived ${arrived}`);
  });

  await harness.step('volume up, down and mute', 'volume', async () => {
    for (const [key, name] of [[Keys.VOLUME_UP, 'VolumeUp'], [Keys.VOLUME_DOWN, 'VolumeDown'],
      [Keys.VOLUME_MUTE, 'VolumeMute']]) {
      const before = count(await harness.state(), name);
      await roku.keypress(key);
      await harness.wait((state) => count(state, name) === before + 1, `${name} counted`);
    }
  });

  await harness.step('chained commands', 'key', async () => {
    const before = count(await harness.state(), 'Down');
    await roku.command().down(2).select().send();
    await harness.wait((state) => count(state, 'Down') === before + 2, 'two Down counted');
  });

  await harness.step('power off and on', 'power', async () => {
    await roku.keypress(Keys.POWER_OFF);
    await harness.wait((state) => state.power === false, 'power off');
    await roku.keypress(Keys.POWER_ON);
    await harness.wait((state) => state.power === true, 'power on');
  });

  await harness.step('standby reported by device-info', 'query-state', async () => {
    await roku.keypress(Keys.POWER_OFF);
    await harness.wait((state) => state.power === false, 'power off');
    try {
      const mode = (await roku.info()).powerMode;
      assert(mode !== 'PowerOn', `powerMode ${mode}`);
    } finally {
      await roku.keypress(Keys.POWER_ON);
    }
  });

  await harness.step('launch an application', 'launch', async () => {
    const since = await harness.lastEventId();
    await roku.launch('12');
    const launches = (await harness.events(since)).filter((event) => event.kind === 'application');
    assert(launches.length && launches.at(-1).status === 200, JSON.stringify(launches));
  });

  if (isTv) {
    await harness.step('tune a broadcast channel', 'launch', async () => {
      const since = await harness.lastEventId();
      await roku.launchDtv('1.1');
      const launches = (await harness.events(since)).filter((event) => event.kind === 'application');
      assert(launches.length && launches.at(-1).status === 200, JSON.stringify(launches));
    });
  }

  await harness.step("an application's icon", 'query-state', async () => {
    await roku.icon('12');
  });

  await harness.step('search for a keyword', 'search', async () => {
    await roku.search('tvemu');
  });
});
