// ------------------------------------------------------------------ main thread
// cocos2d is not thread-safe: everything that touches the game is queued and runs at the start of
// CCScheduler::update, on the main thread, one batch per frame.
let queue = [];
let schedulerHooked = false;
let frames = 0;

function ensureSchedulerHook() {
  if (schedulerHooked) return;
  Interceptor.attach(ex('?update@CCScheduler@cocos2d@@UEAAXM@Z'), {
    onEnter() {
      frames++;
      if (queue.length === 0) return;
      const jobs = queue;
      queue = [];
      for (const j of jobs) {
        try {
          j.resolve(j.fn());
        } catch (e) {
          j.reject(e);
        }
      }
    },
  });
  schedulerHooked = true;
}

function onMain(fn) {
  ensureSchedulerHook();
  return new Promise((resolve, reject) => queue.push({ fn, resolve, reject }));
}

// ------------------------------------------------------------------ frame capture
// The back buffer is read right before it is presented: exactly what the player sees.
let pendingFrame = null;
let swapHooked = false;

function ensureSwapHook() {
  if (swapHooked) return;
  Interceptor.attach(ex('?swapBuffers@CCEGLView@cocos2d@@UEAAXXZ'), {
    onEnter() {
      if (pendingFrame === null) return;
      const req = pendingFrame;
      pendingFrame = null;
      try {
        const sz = C.getFrameSize(C.sharedOpenGLView());
        const w = Math.round(sz.readFloat());
        const h = Math.round(sz.add(4).readFloat());
        const buf = Memory.alloc(w * h * 4);
        GL.pixelStorei(0x0d05, 1);                        // GL_PACK_ALIGNMENT
        GL.readBuffer(0x0405);                            // GL_BACK
        GL.readPixels(0, 0, w, h, 0x1908, 0x1401, buf);   // GL_RGBA, GL_UNSIGNED_BYTE
        send({ type: 'frame', w, h }, buf.readByteArray(w * h * 4));
        req.resolve({ width: w, height: h });
      } catch (e) {
        req.reject(e);
      } finally {
        for (const n of req.hidden) C.setVisible(n, 1);
      }
    },
  });
  swapHooked = true;
}

// Requests the next frame; hidden are nodes hidden for that frame only (restored afterwards).
function captureNextFrame(hidden) {
  ensureSwapHook();
  return new Promise((resolve, reject) => {
    pendingFrame = { resolve, reject, hidden };
  });
}
