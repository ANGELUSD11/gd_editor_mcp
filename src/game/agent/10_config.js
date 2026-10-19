// ------------------------------------------------------------------ address table
// Signature of every game function the agent uses: name in the version table -> [return, arguments].
const SIGNATURES = {
  createObjectsFromString: ['LevelEditorLayer::createObjectsFromString', 'pointer', ['pointer', 'pointer', 'int', 'int']],
  createObjectsFromSetup: ['LevelEditorLayer::createObjectsFromSetup', 'void', ['pointer', 'pointer']],
  levelSettingsUpdated: ['LevelEditorLayer::levelSettingsUpdated', 'void', ['pointer']],
  selectObjects: ['EditorUI::selectObjects', 'void', ['pointer', 'pointer', 'int']],
  deselectAll: ['EditorUI::deselectAll', 'void', ['pointer']],
  getSelectedObjects: ['EditorUI::getSelectedObjects', 'pointer', ['pointer']],
  onDeleteSelected: ['EditorUI::onDeleteSelected', 'void', ['pointer', 'pointer']],
  onPlaytest: ['EditorUI::onPlaytest', 'void', ['pointer', 'pointer']],
  onStopPlaytest: ['EditorUI::onStopPlaytest', 'void', ['pointer', 'pointer']],
  updateButtons: ['EditorUI::updateButtons', 'void', ['pointer']],
  moveGamelayer: ['EditorUI::moveGamelayer', 'void', ['pointer', 'pointer']],
  updateZoom: ['EditorUI::updateZoom', 'void', ['pointer', 'float']],
  createBackground: ['GJBaseGameLayer::createBackground', 'void', ['pointer', 'int']],
  createGroundLayer: ['GJBaseGameLayer::createGroundLayer', 'void', ['pointer', 'int', 'int']],
  createMiddleground: ['GJBaseGameLayer::createMiddleground', 'void', ['pointer', 'int']],
  lsoGetSaveString: ['LevelSettingsObject::getSaveString', 'pointer', ['pointer', 'pointer']],
  getAudioFileName: ['GJGameLevel::getAudioFileName', 'pointer', ['pointer', 'pointer']],
  gdNew: ['operator new', 'pointer', ['uint64']],
};
const REQUIRED_OFFSETS = ['LevelEditorLayer::LevelSettingsDelegate', 'LevelEditorLayer::m_level',
  'LevelSettingsObject::m_songOffset',
  'LevelEditorLayer::m_levelSettings', 'GJGameLevel::m_audioTrack', 'GJGameLevel::m_songID'];

let CFG = null;
let G = null;
let READY = false;
let INIT_REPORT = null;

function rvaPtr(rva) { return exe.base.add(ptr(rva)); }
function offset(name) { return ptr(CFG.offsets[name]).toInt32(); }

// Checks that the table matches this executable: byte fingerprint of every function and the vtable.
function initCfg(cfg) {
  CFG = cfg;
  const rep = { ok: true, problems: [] };
  for (const [key, [name]] of Object.entries(SIGNATURES)) {
    if (!cfg.functions[name]) {
      rep.problems.push({ name, problem: 'missing from the table (' + key + ')' });
    }
  }
  for (const name of REQUIRED_OFFSETS) {
    if (!(cfg.offsets && cfg.offsets[name])) rep.problems.push({ name, problem: 'missing offset' });
  }
  for (const [name, f] of Object.entries(cfg.functions)) {
    const got = hex(rvaPtr(f.rva).readByteArray(f.bytes.length / 2));
    if (got !== f.bytes) rep.problems.push({ name, problem: 'different bytes', expected: f.bytes, got });
  }
  const slot = cfg.slots['GameObject::getSaveString'];
  const vfn = rvaPtr(cfg.vtables.GameObject).add(slot * 8).readPointer();
  if (!vfn.equals(rvaPtr(cfg.functions['GameObject::getSaveString'].rva))) {
    rep.problems.push({ name: 'vtable GameObject::getSaveString', problem: 'different slot' });
  }
  rep.ok = rep.problems.length === 0;
  if (rep.ok) {
    G = {};
    for (const [key, [name, ret, args]] of Object.entries(SIGNATURES)) G[key] = nf(rvaPtr(cfg.functions[name].rva), ret, args);
  }
  READY = rep.ok;
  INIT_REPORT = rep;
  return rep;
}
