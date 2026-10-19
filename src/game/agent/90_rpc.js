// ------------------------------------------------------------------ API for Python
// Every method returns a Promise resolved on the game's main thread.
// Methods that modify the level receive `guard` (the validated level id) and check it.
rpc.exports = {
  init(cfg) {
    return initCfg(cfg);
  },

  status() {
    return onMain(() => {
      const scene = C.getRunningScene(C.sharedDirector());
      const ed = findEditor();
      const r = { ready: READY, frames, scene: scene.isNull() ? null : rtti(scene), in_editor: ed !== null };
      if (ed !== null && READY) {
        r.level = levelInfo(ed);
        r.objects = collect(ed, null).length;
        r.selected = ed.eui === null ? 0 : C.count(G.getSelectedObjects(ed.eui));
      }
      return r;
    });
  },

  addObjects(str, select, undoable, guard) {
    return onMain(() => {
      const ed = requireEditor();
      checkGuard(ed, guard);
      const s = makeStr(str);
      const arr = G.createObjectsFromString(ed.lel, s.obj, undoable ? 0 : 1, 1);
      const n = C.count(arr);
      if (n > 0) objectsArray(ed.lel, C.objectAtIndex(arr, 0));
      if (select && n > 0) selectList(ed, arrayItems(arr));
      else G.updateButtons(ed.eui);
      return { created: n };
    });
  },

  getObjects(filter, limit) {
    return onMain(() => {
      const found = collect(requireEditor(), filter);
      return { total_matching: found.length, objects: found.slice(0, limit).map(f => f.s) };
    });
  },

  deleteObjects(filter, guard) {
    return onMain(() => {
      const ed = requireEditor();
      checkGuard(ed, guard);
      return { deleted: deleteList(ed, collect(ed, filter).map(f => f.o)) };
    });
  },

  selectObjects(filter) {
    return onMain(() => {
      const ed = requireEditor();
      const found = collect(ed, filter);
      selectList(ed, found.map(f => f.o));
      return { selected: found.length };
    });
  },

  levelString() {
    return onMain(() => {
      const ed = requireEditor();
      return { header: settingsString(ed), objects: collect(ed, null).map(f => f.s), level: levelInfo(ed) };
    });
  },

  loadLevel(header, objects, replace, songId, guard) {
    return onMain(() => {
      const ed = requireEditor();
      checkGuard(ed, guard);
      const r = { deleted: replace ? deleteList(ed, collect(ed, null).map(f => f.o)) : 0 };
      if (songId) {
        try {
          setAudio(ed, songId, 0);
          r.song = { ok: true, song_id: songId };
        } catch (e) {
          r.song = { ok: false, reason: String(e.message) };
        }
      }
      G.createObjectsFromSetup(ed.lel, makeGdStr(header + ';' + objects));
      r.settings_refreshed = refreshSettings(ed);
      r.art = applyArt(ed, header);
      G.updateButtons(ed.eui);
      OBJ_OFF = null;
      return r;
    });
  },

  songState() {
    return onMain(() => {
      const ed = requireEditor();
      return Object.assign({ header: settingsString(ed) }, audioState(ed));
    });
  },

  setSong(songId, track, songOffset, guard) {
    return onMain(() => {
      const ed = requireEditor();
      checkGuard(ed, guard);
      if (songId != null || track != null) setAudio(ed, songId || 0, track || 0);
      if (songOffset != null) setSongOffset(ed, songOffset);
      const r = audioState(ed);
      r.settings_refreshed = refreshSettings(ed);
      return r;
    });
  },

  playtest(start) {
    return onMain(() => {
      const ed = requireEditor();
      if (start) G.onPlaytest(ed.eui, NULLP);
      else G.onStopPlaytest(ed.eui, NULLP);
      return { playtesting: !!start };
    });
  },

  view(x, y, zoom) {
    return onMain(() => {
      const ed = requireEditor();
      const ol = objectLayer(ed);
      if (ol === null) fail('EMPTY_LEVEL', 'The camera needs at least one object in the level.');
      if (zoom != null) G.updateZoom(ed.eui, zoom);
      const sz = C.getContentSize(ed.scene);
      const w = sz.readFloat();
      const h = sz.add(4).readFloat();
      const z = C.getScale(ol.layer);
      const [cx, cy] = pos(ol.layer);
      const nx = x == null ? cx : w / 2 - (x + ol.dx) * z;
      const ny = y == null ? cy : h * 0.64 - (y + ol.dy) * z;  // center of the free area above the toolbar
      const delta = Memory.alloc(8);
      delta.writeFloat(nx - cx);
      delta.add(4).writeFloat(ny - cy);
      G.moveGamelayer(ed.eui, delta);
      return { zoom: z, center: [x, y] };
    });
  },

  captureFrame(hideUI) {
    return onMain(() => {
      const ed = hideUI && READY ? findEditor() : null;
      return captureNextFrame(ed === null ? [] : hideEditorUI(ed));
    });
  },

  sceneTree(depth, maxKids) {
    return onMain(() => {
      const scene = C.getRunningScene(C.sharedDirector());
      return { scene: scene.isNull() ? null : describe(scene, 0, depth, maxKids), objects_array_offset: OBJ_OFF };
    });
  },
};
