"""MIDI for the S3000 Workbench app on the Mac.

The Mac's built-in web engine (WKWebView) has no Web MIDI, so the program opens the MIDI ports itself
through CoreMIDI (python-rtmidi) and passes the messages to and from the page over a WebSocket.
A small script in the page (POLYFILL) gives it navigator.requestMIDIAccess in the usual form, so every
MIDI feature of the Workbench works unchanged.

Notes are timed here, not in the page: the page sends each message with its delay, and the program sends
it at that moment, so note lengths stay exact even if macOS slows the window's timers down.
"""
import asyncio
import json
import logging
import threading

log = logging.getLogger("s3k")

POLL_EVERY = 2.0            # seconds between checks for plugged or unplugged MIDI devices


def _unique(names):
    """Port ids are the port names; two ports with the same name get ' #2', ' #3'..."""
    seen, out = {}, []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else "%s #%d" % (n, seen[n]))
    return out


class MidiBridge:
    def __init__(self, fake=False):
        self.fake = fake
        self.rtmidi = None
        self.error = None
        self.lock = threading.Lock()
        self.ins = {}           # id -> MidiIn (all inputs are open, so incoming notes are never missed)
        self.outs = {}          # id -> MidiOut (opened on first use)
        self.in_ids, self.out_ids = [], []
        self.clients = set()
        self.loop = None
        self.pending = {}       # output id -> scheduled sends, so clear() can cancel them
        if not fake:
            try:
                import rtmidi
                self.rtmidi = rtmidi
            except Exception as e:      # the page then shows no ports, with this reason
                self.error = "MIDI is not available: %s" % e
                log.warning(self.error)

    # ---------- ports ----------
    def _scan(self):
        if self.fake:                   # a loopback port: what is sent to it comes back on its input
            return ["Test loopback"], ["Test loopback"]
        if not self.rtmidi:
            return [], []
        try:
            i = self.rtmidi.MidiIn()
            o = self.rtmidi.MidiOut()
            ins, outs = _unique(i.get_ports()), _unique(o.get_ports())
            i.delete()
            o.delete()
            return ins, outs
        except Exception as e:
            log.warning("Could not list MIDI ports: %s", e)
            return self.in_ids, self.out_ids

    def refresh(self):
        """Open new inputs, close vanished ones. Returns True if the port list changed."""
        ins, outs = self._scan()
        with self.lock:
            changed = ins != self.in_ids or outs != self.out_ids
            if not changed:
                return False
            for pid in list(self.ins):
                if pid not in ins:
                    self._close(self.ins.pop(pid))
            for pid in list(self.outs):
                if pid not in outs:
                    self._close(self.outs.pop(pid))
            if self.rtmidi:
                for idx, pid in enumerate(ins):
                    if pid in self.ins:
                        continue
                    try:
                        m = self.rtmidi.MidiIn(queue_size_limit=4096)
                        m.ignore_types(sysex=False, timing=True, active_sense=True)
                        m.open_port(idx)
                        m.set_callback(self._incoming, pid)
                        self.ins[pid] = m
                    except Exception as e:
                        log.warning("Could not open MIDI input %s: %s", pid, e)
            self.in_ids, self.out_ids = ins, outs
        log.info("MIDI ports: in %s, out %s", ins, outs)
        return True

    @staticmethod
    def _close(m):
        try:
            m.close_port()
            m.delete()
        except Exception:
            pass

    def ports_msg(self):
        with self.lock:
            return json.dumps({"type": "ports", "error": self.error,
                               "inputs": [{"id": p, "name": p} for p in self.in_ids],
                               "outputs": [{"id": p, "name": p} for p in self.out_ids]})

    # ---------- messages ----------
    def _incoming(self, event, pid):
        """rtmidi calls this on its own thread."""
        data, _delta = event
        self._broadcast(json.dumps({"type": "midi", "port": pid, "data": list(data)}))

    def _broadcast(self, text):
        loop = self.loop
        if not loop:
            return
        for ws in list(self.clients):
            loop.call_soon_threadsafe(lambda ws=ws: asyncio.ensure_future(self._safe_send(ws, text)))

    @staticmethod
    async def _safe_send(ws, text):
        try:
            await ws.send(text)
        except Exception:
            pass

    def _out(self, pid):
        with self.lock:
            m = self.outs.get(pid)
            if m is None:
                if pid not in self.out_ids:
                    raise RuntimeError("MIDI output %r is not connected" % pid)
                m = self.rtmidi.MidiOut()
                m.open_port(self.out_ids.index(pid))
                self.outs[pid] = m
            return m

    def send_now(self, pid, data):
        if self.fake:
            self._broadcast(json.dumps({"type": "midi", "port": pid, "data": list(data)}))
            return
        if not self.rtmidi:
            return
        try:
            self._out(pid).send_message(list(data))
        except Exception as e:
            log.warning("MIDI send to %s failed: %s", pid, e)

    def send(self, pid, data, delay_ms):
        if delay_ms and delay_ms > 0.5:
            jobs = self.pending.setdefault(pid, set())

            def fire():
                jobs.discard(h)
                self.send_now(pid, data)
            h = self.loop.call_later(delay_ms / 1000.0, fire)
            jobs.add(h)
        else:
            self.send_now(pid, data)

    def clear(self, pid):
        for h in self.pending.pop(pid, set()):
            h.cancel()

    # ---------- the page's connection ----------
    async def watch(self):
        """Started once by the server: picks up MIDI devices being plugged in or out."""
        self.loop = asyncio.get_running_loop()
        await self.loop.run_in_executor(None, self.refresh)
        while True:
            await asyncio.sleep(POLL_EVERY)
            if await self.loop.run_in_executor(None, self.refresh):
                for ws in list(self.clients):
                    await self._safe_send(ws, self.ports_msg())

    async def handler(self, ws):
        self.clients.add(ws)
        try:
            await ws.send(self.ports_msg())
            async for raw in ws:
                msg = json.loads(raw)
                cmd = msg.get("cmd")
                if cmd == "send":
                    self.send(msg.get("port"), msg.get("data") or [], msg.get("delay") or 0)
                elif cmd == "clear":
                    self.clear(msg.get("port"))
                elif cmd == "ports":
                    await ws.send(self.ports_msg())
        except Exception:
            pass
        finally:
            self.clients.discard(ws)

    def close(self):
        with self.lock:
            for m in list(self.ins.values()) + list(self.outs.values()):
                self._close(m)
            self.ins.clear()
            self.outs.clear()


# Web MIDI for the page, backed by the connection above. Injected before the Workbench's own scripts.
POLYFILL = r"""<script>
(()=>{
  if(navigator.requestMIDIAccess&&!window.S3K_APP.midiBridge)return;
  const inputs=new Map(),outputs=new Map(),accesses=[],waiting=[];let ws=null,ready=false,err=null;
  const fire=(t,name,ev)=>{const h=t['on'+name];if(h)try{h.call(t,ev);}catch(e){console.error(e);}
    (t._l[name]||[]).forEach(f=>{try{f.call(t,ev);}catch(e){console.error(e);}});};
  class Port{
    constructor(type,id,name){this.type=type;this.id=id;this.name=name;this.manufacturer='';this.version='';
      this.state='connected';this.connection='open';this._l={};this.onstatechange=null;if(type==='input')this.onmidimessage=null;}
    addEventListener(n,f){(this._l[n]=this._l[n]||[]).push(f);}
    removeEventListener(n,f){this._l[n]=(this._l[n]||[]).filter(x=>x!==f);}
    open(){return Promise.resolve(this);} close(){return Promise.resolve(this);}
    send(data,ts){
      if(!ws||ws.readyState!==1)throw new Error('MIDI is not connected');
      const delay=ts?Math.max(0,ts-performance.now()):0;
      ws.send(JSON.stringify({cmd:'send',port:this.id,data:Array.from(data),delay}));
    }
    clear(){if(ws&&ws.readyState===1)ws.send(JSON.stringify({cmd:'clear',port:this.id}));}
  }
  const sync=(map,type,list)=>{
    const changed=[];const ids=new Set(list.map(p=>p.id));
    for(const [id,p] of map)if(!ids.has(id)){map.delete(id);p.state='disconnected';changed.push(p);}
    for(const x of list)if(!map.has(x.id)){const p=new Port(type,x.id,x.name);map.set(x.id,p);changed.push(p);}
    return changed;
  };
  function connect(){
    ws=new WebSocket('ws://'+location.host+'/midi');
    ws.onmessage=e=>{
      const m=JSON.parse(e.data);
      if(m.type==='ports'){
        err=m.error;
        const ch=[...sync(inputs,'input',m.inputs),...sync(outputs,'output',m.outputs)];
        if(!ready){ready=true;waiting.splice(0).forEach(f=>f());}
        else ch.forEach(port=>{accesses.forEach(a=>fire(a,'statechange',{port}));fire(port,'statechange',{port});});
      }else if(m.type==='midi'){
        const p=inputs.get(m.port);if(p)fire(p,'midimessage',{data:new Uint8Array(m.data),timeStamp:performance.now(),target:p});
      }
    };
    ws.onclose=()=>{ws=null;setTimeout(connect,1000);};
  }
  connect();
  navigator.requestMIDIAccess=function(){
    return new Promise((res,rej)=>{
      const done=()=>{const a={inputs,outputs,sysexEnabled:true,onstatechange:null,_l:{},
        addEventListener(n,f){(this._l[n]=this._l[n]||[]).push(f);},
        removeEventListener(n,f){this._l[n]=(this._l[n]||[]).filter(x=>x!==f);}};
        accesses.push(a);res(a);};
      if(ready)done();else{waiting.push(done);setTimeout(()=>{if(!ready)rej(new Error('Could not reach the program\'s MIDI.'));},5000);}
    });
  };
  if(navigator.permissions&&navigator.permissions.query){
    const q=navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query=d=>d&&d.name==='midi'?Promise.resolve({state:'granted',onchange:null}):q(d);
  }else{navigator.permissions={query:d=>Promise.resolve({state:d&&d.name==='midi'?'granted':'prompt'})};}
})();
</script>
"""
