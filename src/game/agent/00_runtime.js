'use strict';
/*
 * Frida agent injected into GeometryDash.exe.
 *
 * The files in this folder are concatenated in alphabetical order and loaded as a single script:
 *   00_runtime.js     modules, cocos2d/OpenGL exports and memory helpers
 *   10_config.js      address table of the GD version and its verification
 *   20_mainthread.js  main-thread execution and frame capture
 *   30_editor.js      level editor operations
 *   90_rpc.js         API exposed to Python
 */

const exe = Process.getModuleByName('GeometryDash.exe');
const cc = Process.getModuleByName('libcocos2d.dll');
const gl = Process.getModuleByName('opengl32.dll');
const NULLP = ptr(0);

function nf(addr, ret, args) { return new NativeFunction(addr, ret, args); }
function ex(name) { return cc.getExportByName(name); }

// libcocos2d.dll exports (stable across GD versions: resolved by name).
const C = {
  sharedDirector: nf(ex('?sharedDirector@CCDirector@cocos2d@@SAPEAV12@XZ'), 'pointer', []),
  getRunningScene: nf(ex('?getRunningScene@CCDirector@cocos2d@@QEAAPEAVCCScene@2@XZ'), 'pointer', ['pointer']),
  getChildren: nf(ex('?getChildren@CCNode@cocos2d@@UEAAPEAVCCArray@2@XZ'), 'pointer', ['pointer']),
  getParent: nf(ex('?getParent@CCNode@cocos2d@@UEAAPEAV12@XZ'), 'pointer', ['pointer']),
  getPosition: nf(ex('?getPosition@CCNode@cocos2d@@UEAAAEBVCCPoint@2@XZ'), 'pointer', ['pointer']),
  getScale: nf(ex('?getScale@CCNode@cocos2d@@UEAAMXZ'), 'float', ['pointer']),
  getContentSize: nf(ex('?getContentSize@CCNode@cocos2d@@UEBAAEBVCCSize@2@XZ'), 'pointer', ['pointer']),
  isVisible: nf(ex('?isVisible@CCNode@cocos2d@@UEAA_NXZ'), 'uint8', ['pointer']),
  setVisible: nf(ex('?setVisible@CCNode@cocos2d@@UEAAX_N@Z'), 'void', ['pointer', 'int']),
  count: nf(ex('?count@CCArray@cocos2d@@QEBAIXZ'), 'uint', ['pointer']),
  objectAtIndex: nf(ex('?objectAtIndex@CCArray@cocos2d@@QEAAPEAVCCObject@2@I@Z'), 'pointer', ['pointer', 'uint']),
  arrayCreate: nf(ex('?create@CCArray@cocos2d@@SAPEAV12@XZ'), 'pointer', []),
  addObject: nf(ex('?addObject@CCArray@cocos2d@@QEAAXPEAVCCObject@2@@Z'), 'void', ['pointer', 'pointer']),
  sharedOpenGLView: nf(ex('?sharedOpenGLView@CCEGLView@cocos2d@@SAPEAV12@XZ'), 'pointer', []),
  getFrameSize: nf(ex('?getFrameSize@CCEGLViewProtocol@cocos2d@@UEBAAEBVCCSize@2@XZ'), 'pointer', ['pointer']),
};

const GL = {
  readPixels: nf(gl.getExportByName('glReadPixels'), 'void', ['int', 'int', 'int', 'int', 'uint', 'uint', 'pointer']),
  pixelStorei: nf(gl.getExportByName('glPixelStorei'), 'void', ['uint', 'int']),
  readBuffer: nf(gl.getExportByName('glReadBuffer'), 'void', ['uint']),
};

// Errors with a code: Python turns them into typed exceptions.
function fail(code, message) {
  throw new Error('[' + code + '] ' + message);
}

// ------------------------------------------------------------------ nodes and RTTI
function hex(buf) {
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

// MSVC class name (".?AVLevelEditorLayer@@") from an object's vtable.
function rtti(p) {
  try {
    if (p.isNull()) return null;
    const col = p.readPointer().sub(8).readPointer();
    if (col.readU32() !== 1) return null;
    const base = col.sub(col.add(20).readU32());
    return base.add(col.add(12).readU32()).add(16).readCString();
  } catch (e) {
    return null;
  }
}

function arrayItems(arr) {
  const out = [];
  if (arr.isNull()) return out;
  const n = C.count(arr);
  for (let i = 0; i < n; i++) out.push(C.objectAtIndex(arr, i));
  return out;
}

function toArray(ptrs) {
  const arr = C.arrayCreate();
  for (const p of ptrs) C.addObject(arr, p);
  return arr;
}

function children(node) { return arrayItems(C.getChildren(node)); }

function pos(node) {
  const p = C.getPosition(node);
  return [p.readFloat(), p.add(4).readFloat()];
}

// First pointer in [from, to) of base whose RTTI is cls.
function findField(base, cls, from, to) {
  for (let off = from; off < to; off += 8) {
    let p;
    try {
      p = base.add(off).readPointer();
    } catch (e) {
      break;
    }
    if (!p.isNull() && rtti(p) === cls) return p;
  }
  return NULLP;
}

// ------------------------------------------------------------------ std::string (MSVC x64)
// Layout: {union{char buf[16]; char* ptr}, size_t size, size_t capacity}; SSO when capacity == 15.
function utf8len(s) {
  return /^[\x00-\x7f]*$/.test(s) ? s.length : unescape(encodeURIComponent(s)).length;
}

// String backed by Frida memory: only for const& arguments the game never frees.
function makeStr(s) {
  const len = utf8len(s);
  const buf = Memory.allocUtf8String(s);
  const obj = Memory.alloc(32);
  if (len < 16) {
    Memory.copy(obj, buf, len + 1);
    obj.add(24).writeU64(15);
  } else {
    obj.writePointer(buf);
    obj.add(24).writeU64(len);
  }
  obj.add(16).writeU64(len);
  return { obj, buf };
}

// String whose buffer is allocated by GD (operator new, with MSVC's alignment for >= 4 KB),
// for when the game may modify or free it.
function makeGdStr(s) {
  const len = utf8len(s);
  const obj = Memory.alloc(32);
  if (len < 16) {
    Memory.copy(obj, Memory.allocUtf8String(s), len + 1);
    obj.add(24).writeU64(15);
  } else {
    let data;
    if (len + 1 >= 0x1000) {
      const raw = G.gdNew(len + 1 + 0x27);
      data = raw.add(0x27).and(ptr('0xffffffffffffffe0'));
      data.sub(8).writePointer(raw);
    } else {
      data = G.gdNew(len + 1);
    }
    data.writeUtf8String(s);
    obj.writePointer(data);
    obj.add(24).writeU64(len);
  }
  obj.add(16).writeU64(len);
  return obj;
}

function validStr(p) {
  try {
    const size = p.add(16).readU64().toNumber();
    const cap = p.add(24).readU64().toNumber();
    if (cap < 15 || size > cap || cap > 1e9) return false;
    const data = cap === 15 ? p : p.readPointer();
    return data.add(size).readU8() === 0;
  } catch (e) {
    return false;
  }
}

function readStr(p) {
  const size = p.add(16).readU64().toNumber();
  const cap = p.add(24).readU64().toNumber();
  const data = cap >= 16 ? p.readPointer() : p;
  return size ? data.readUtf8String(size) : '';
}
