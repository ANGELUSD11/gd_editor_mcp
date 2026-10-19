// ------------------------------------------------------------------ level editor
const CLS = {
  array: '.?AVCCArray@cocos2d@@',
  layer: '.?AVCCLayer@cocos2d@@',
  editorLayer: '.?AVLevelEditorLayer@@',
  editorUI: '.?AVEditorUI@@',
  uiLayer: '.?AVUILayer@@',
  level: '.?AVGJGameLevel@@',
  settings: '.?AVLevelSettingsObject@@',
};

let OBJ_OFF = null;           // offset of m_objects in LevelEditorLayer (calibrated at runtime)
const SAVE_FNS = new Map();   // getSaveString per vtable

function findEditor() {
  const scene = C.getRunningScene(C.sharedDirector());
  if (scene.isNull()) return null;
  let lel = null;
  let eui = null;
  for (const c of children(scene)) {
    const n = rtti(c);
    if (n === CLS.editorLayer) lel = c;
    else if (n === CLS.editorUI) eui = c;
  }
  if (lel === null) return null;
  if (eui === null) eui = children(lel).find(c => rtti(c) === CLS.editorUI) || null;
  return { scene, lel, eui };
}

function requireEditor() {
  if (!READY) fail('UNSUPPORTED', 'The addresses do not match this GD version: ' + JSON.stringify(INIT_REPORT));
  const ed = findEditor();
  if (ed === null) fail('NOT_IN_EDITOR', 'No level is open in the editor.');
  if (ed.eui === null) fail('NOT_IN_EDITOR', 'The editor UI (EditorUI) was not found.');
  return ed;
}

// ------------------------------------------------------------------ open level
function levelOf(ed) {
  const p = ed.lel.add(offset('LevelEditorLayer::m_level')).readPointer();
  return rtti(p) === CLS.level ? p : findField(ed.lel, CLS.level, 0x100, 0x8000);
}

function settingsOf(ed) {
  const p = ed.lel.add(offset('LevelEditorLayer::m_levelSettings')).readPointer();
  return rtti(p) === CLS.settings ? p : findField(ed.lel, CLS.settings, 0x100, 0x8000);
}

// GJGameLevel: m_levelName is the first of 7 consecutive std::string fields.
function levelNameOffset(level) {
  for (let off = 0x100; off < 0x800; off += 8) {
    let ok = true;
    for (let i = 0; i < 7 && ok; i++) ok = validStr(level.add(off + 32 * i));
    if (ok) return off;
  }
  return null;
}

function levelInfo(ed) {
  const level = levelOf(ed);
  if (level.isNull()) return { id: null, name: null };
  const nameOff = levelNameOffset(level);
  return { id: level.toString(), name: nameOff === null ? null : readStr(level.add(nameOff)) };
}

// Operations that modify the level are only allowed on the level validated with check_ready.
function checkGuard(ed, guard) {
  if (!guard) fail('NOT_ARMED', 'The level has not been validated yet.');
  const id = levelInfo(ed).id;
  if (id !== guard) fail('LEVEL_CHANGED', 'The open level is not the one that was validated.');
}

// ------------------------------------------------------------------ objects
function isGameObject(p) {
  const n = rtti(p);
  return n !== null && /Object@@$/.test(n) && n !== '.?AVUndoObject@@' && n !== '.?AVCCObject@cocos2d@@';
}

// GameObject arrays hanging from LevelEditorLayer: [{off, p, n}]
function objectArrays(lel) {
  const out = [];
  for (let off = 0x100; off < 0x8000; off += 8) {
    let p;
    try {
      p = lel.add(off).readPointer();
    } catch (e) {
      break;
    }
    if (p.isNull() || rtti(p) !== CLS.array) continue;
    const n = C.count(p);
    if (n > 0 && !(isGameObject(C.objectAtIndex(p, 0)) && isGameObject(C.objectAtIndex(p, n - 1)))) continue;
    out.push({ off, p, n });
  }
  return out;
}

function arrayContains(arr, obj) {
  for (let i = C.count(arr) - 1; i >= 0; i--) if (C.objectAtIndex(arr, i).equals(obj)) return true;
  return false;
}

// m_objects: calibrated with a freshly created object (calibrate); until then, the largest array.
function objectsArray(lel, calibrate) {
  if (calibrate) {
    const best = objectArrays(lel).filter(c => arrayContains(c.p, calibrate)).sort((a, b) => b.n - a.n)[0];
    if (best) OBJ_OFF = best.off;
  }
  if (OBJ_OFF !== null) {
    const a = lel.add(OBJ_OFF).readPointer();
    if (rtti(a) === CLS.array) return a;
    OBJ_OFF = null;
  }
  const best = objectArrays(lel).sort((a, b) => b.n - a.n)[0];
  return best ? best.p : NULLP;
}

function objSaveString(obj, lel) {
  const f = obj.readPointer().add(CFG.slots['GameObject::getSaveString'] * 8).readPointer();
  if (f.compare(exe.base) < 0 || f.compare(exe.base.add(exe.size)) >= 0) throw new Error('vtable inesperada');
  const key = f.toString();
  let fn = SAVE_FNS.get(key);
  if (fn === undefined) {
    fn = nf(f, 'pointer', ['pointer', 'pointer', 'pointer']);
    SAVE_FNS.set(key, fn);
  }
  const ret = Memory.alloc(32);
  fn(obj, ret, lel);
  return readStr(ret);
}

function parseHead(s) {
  const p = s.split(',', 12);
  const r = { id: 0, x: 0, y: 0 };
  for (let i = 0; i + 1 < p.length; i += 2) {
    if (p[i] === '1') r.id = +p[i + 1];
    else if (p[i] === '2') r.x = +p[i + 1];
    else if (p[i] === '3') r.y = +p[i + 1];
  }
  return r;
}

// Internal editor collision blocks (ID 1816 with block ID >= 10000): not the user's objects.
function isInternal(h, s) {
  if (h.id !== 1816) return false;
  const m = /(^|,)80,(\d+)/.exec(s);
  return m !== null && +m[2] >= 10000;
}

function matches(h, f) {
  if (!f) return true;
  if (f.x_min != null && h.x < f.x_min) return false;
  if (f.x_max != null && h.x > f.x_max) return false;
  if (f.y_min != null && h.y < f.y_min) return false;
  if (f.y_max != null && h.y > f.y_max) return false;
  if (f.ids != null && f.ids.length && f.ids.indexOf(h.id) < 0) return false;
  return true;
}

// User objects matching the filter: [{o, s, h}]
function collect(ed, filter) {
  const out = [];
  for (const o of arrayItems(objectsArray(ed.lel))) {
    const s = objSaveString(o, ed.lel);
    const h = parseHead(s);
    if (!isInternal(h, s) && matches(h, filter)) out.push({ o, s, h });
  }
  return out;
}

function selectList(ed, objs) {
  G.deselectAll(ed.eui);
  if (objs.length) G.selectObjects(ed.eui, toArray(objs), 1);
  G.updateButtons(ed.eui);
}

// Deletes through the editor's delete button (it stays in the undo history).
function deleteList(ed, objs) {
  if (objs.length === 0) return 0;
  G.deselectAll(ed.eui);
  G.selectObjects(ed.eui, toArray(objs), 1);
  G.onDeleteSelected(ed.eui, NULLP);
  G.updateButtons(ed.eui);
  return objs.length;
}

// ------------------------------------------------------------------ level settings
function settingsString(ed) {
  const lso = settingsOf(ed);
  if (lso.isNull()) return '';
  const ret = Memory.alloc(32);
  G.lsoGetSaveString(lso, ret);
  return readStr(ret);
}

function audioFileName(level) {
  const ret = Memory.alloc(32);
  G.getAudioFileName(level, ret);
  return readStr(ret);
}

function headerValue(header, key) {
  const parts = header.split(',');
  for (let i = 0; i + 1 < parts.length; i += 2) if (parts[i] === key) return parts[i + 1];
  return null;
}

function requireLevel(ed) {
  const level = levelOf(ed);
  if (level.isNull()) fail('NOT_IN_EDITOR', 'The open level (GJGameLevel) was not found.');
  return level;
}

function songOffsetPtr(ed) {
  const lso = settingsOf(ed);
  if (lso.isNull()) fail('NOT_IN_EDITOR', 'The level settings (LevelSettingsObject) were not found.');
  return lso.add(offset('LevelSettingsObject::m_songOffset'));
}

function audioState(ed) {
  const level = requireLevel(ed);
  return {
    song_id: level.add(offset('GJGameLevel::m_songID')).readS32(),
    audio_track: level.add(offset('GJGameLevel::m_audioTrack')).readS32(),
    audio_file: audioFileName(level),
    song_offset: songOffsetPtr(ed).readFloat(),
  };
}

// Sets a Newgrounds/library song (songId > 0) or an official track (songId = 0). Verified with getAudioFileName
// ("...\<id>.mp3" for custom songs); reverted if the game does not report the expected file.
function setAudio(ed, songId, track) {
  const level = requireLevel(ed);
  const pSong = level.add(offset('GJGameLevel::m_songID'));
  const pTrack = level.add(offset('GJGameLevel::m_audioTrack'));
  const old = [pSong.readS32(), pTrack.readS32()];
  pSong.writeS32(songId);
  pTrack.writeS32(songId ? 0 : track);
  const file = audioFileName(level);
  const base = file.replace(/^.*[\\/]/, '');
  const ok = songId ? base.indexOf(String(songId) + '.') === 0 : base.length > 0 && !/^\d+\./.test(base);
  if (!ok) {
    pSong.writeS32(old[0]);
    pTrack.writeS32(old[1]);
    fail('UNSUPPORTED', 'The game did not accept the song (audio file: "' + file + '").');
  }
}

// Writes the song offset (header kA13) and verifies it by reading the level header back.
function setSongOffset(ed, value) {
  const p = songOffsetPtr(ed);
  const old = p.readFloat();
  p.writeFloat(value);
  const got = parseFloat(headerValue(settingsString(ed), 'kA13'));
  if (!(Math.abs(got - value) < 0.002)) {
    p.writeFloat(old);
    fail('UNSUPPORTED', 'The song offset could not be verified (header: ' + got + ').');
  }
}

// levelSettingsUpdated belongs to the LevelSettingsDelegate interface: this = LEL + subobject offset.
function refreshSettings(ed) {
  const dthis = ed.lel.add(offset('LevelEditorLayer::LevelSettingsDelegate'));
  const expected = rvaPtr(CFG.functions['LevelEditorLayer::levelSettingsUpdated'].rva);
  if (!dthis.readPointer().readPointer().equals(expected)) return false;
  G.levelSettingsUpdated(dthis);
  return true;
}

// Background, ground and middleground from the header (as the Level Settings window does).
function applyArt(ed, header) {
  const kv = {};
  const parts = header.split(',');
  for (let i = 0; i + 1 < parts.length; i += 2) kv[parts[i]] = parts[i + 1];
  const art = {
    bg: Math.max(1, parseInt(kv.kA6 || '1', 10) || 1),
    ground: Math.max(1, parseInt(kv.kA7 || '1', 10) || 1),
    line: Math.max(1, parseInt(kv.kA17 || '1', 10) || 1),
    mg: parseInt(kv.kA25 || '0', 10) || 0,
  };
  G.createBackground(ed.lel, art.bg);
  G.createGroundLayer(ed.lel, art.ground, art.line);
  if (art.mg > 0) G.createMiddleground(ed.lel, art.mg);
  return art;
}

// ------------------------------------------------------------------ camera and UI
// Layer moved/scaled by the editor camera: the first CCLayer ancestor of an object.
// Also returns the offset between node and level coordinates (in 2.2091 nodes are +90 on Y).
function objectLayer(ed) {
  for (const o of arrayItems(objectsArray(ed.lel))) {
    const s = objSaveString(o, ed.lel);
    const h = parseHead(s);
    if (isInternal(h, s)) continue;
    let n = C.getParent(o);
    for (let i = 0; i < 6 && !n.isNull() && !n.equals(ed.lel); i++) {
      if (rtti(n) === CLS.layer) {
        const [nx, ny] = pos(o);
        return { layer: n, dx: nx - h.x, dy: ny - h.y };
      }
      n = C.getParent(n);
    }
  }
  return null;
}

// Hides the editor buttons (for a capture); returns the nodes that must be shown again.
function hideEditorUI(ed) {
  const hidden = [];
  for (const n of [ed.eui].concat(children(ed.lel).filter(c => rtti(c) === CLS.uiLayer))) {
    if (n !== null && C.isVisible(n)) {
      C.setVisible(n, 0);
      hidden.push(n);
    }
  }
  return hidden;
}

function describe(node, depth, maxDepth, maxKids) {
  const kids = children(node);
  const [x, y] = pos(node);
  const d = { cls: rtti(node), x, y, scale: C.getScale(node), n_children: kids.length };
  if (depth < maxDepth) d.children = kids.slice(0, maxKids).map(k => describe(k, depth + 1, maxDepth, maxKids));
  return d;
}
