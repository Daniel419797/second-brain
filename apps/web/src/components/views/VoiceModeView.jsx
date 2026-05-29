"use client";

import { Activity, Bot, FileText, Mic, Radio, SlidersHorizontal, Target, Volume2, Zap } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDashboard } from "@/components/Dashboard/DashboardContext";
import { wsUrl } from "@/services/fridayApi";

const WAVEFORM = [24, 34, 48, 56, 54, 48, 38, 32, 30, 36, 44, 52, 56, 54, 46, 36, 31, 34, 42, 50, 57, 55, 47, 38, 33, 35, 43, 51, 55, 50, 42, 34, 30, 32, 40, 48, 54, 58, 52, 42, 36, 45];

const CONTROL_ROWS = [
  { key: "bargeIn", label: "Barge-in", detail: "Allow user to interrupt Friday mid-speech", icon: Zap },
  { key: "silentMode", label: "Silent Operator Mode", detail: "Friday responds via text only", icon: Volume2 },
  { key: "alwaysListening", label: "Always Listening", detail: "Only act after the wake name is heard", icon: Radio }
];

const WAKE_NAMES = [
  "friday",
  "friiday",
  "friady",
  "friyday",
  "fry day",
  "free day",
  "freiday",
  "freddie",
  "freddy",
  "fred",
  "fridays",
  "friday's",
  "computer",
  "commuter",
  "compute",
  "ok computer",
  "okay computer",
  "jarvis",
  "jervis"
];

const WAKE_ARM_MS = 8500;

export function VoiceModeView() {
  const { api, data, busy, voiceChat, chatMessages, token } = useDashboard();
  const [voiceSummary, setVoiceSummary] = useState(null);
  const [localVoice, setLocalVoice] = useState(null);
  const [selfStatus, setSelfStatus] = useState(null);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [bargeIn, setBargeIn] = useState(true);
  const [silentMode, setSilentMode] = useState(false);
  const [alwaysListening, setAlwaysListening] = useState(true);
  const micLevel = useMicrophoneLevel();
  const submitVoiceCommand = useCallback(
    async ({ text, confidence }) => {
      const clean = String(text || "").trim();
      if (!clean) return;
      api("/voice/reliability/sample", {
        method: "POST",
        body: JSON.stringify({
          heard_text: clean,
          backend: "deepgram-realtime-web",
          confidence,
          accepted: true
        })
      }).catch(() => {});
      await voiceChat(clean);
    },
    [api, voiceChat]
  );
  const speech = useSpeechCommandLoop({
    active: voiceEnabled && alwaysListening,
    hold: busy,
    token,
    onFinal: submitVoiceCommand
  });

  useSpeakFridayReplies(chatMessages, !silentMode);

  useEffect(() => {
    let cancelled = false;
    async function loadVoiceStatus() {
      const [reliability, local, self] = await Promise.allSettled([
        api("/voice/reliability/summary"),
        api("/local-voice-brain/status"),
        api("/self/status")
      ]);
      if (cancelled) return;
      if (reliability.status === "fulfilled") setVoiceSummary(reliability.value);
      if (local.status === "fulfilled") setLocalVoice(local.value);
      if (self.status === "fulfilled") setSelfStatus(self.value);
    }
    loadVoiceStatus();
    return () => {
      cancelled = true;
    };
  }, [api]);

  const transcript = useMemo(() => transcriptItems(chatMessages, speech.interim), [chatMessages, speech.interim]);
  const runtime = selfStatus?.runtime || {};
  const metrics = useMemo(() => buildVoiceMetrics(voiceSummary, runtime, speech), [voiceSummary, runtime, speech]);
  const activeContext = useMemo(() => buildActiveContext(data), [data]);
  const backendVoiceActive = voiceFlag(data.status) || Boolean(localVoice?.barge_in_requested);
  const listening = speech.active || busy || backendVoiceActive;
  const speaking = listening || micLevel > 0.055;
  const signalLevel = speaking ? Math.max(micLevel, busy || backendVoiceActive ? 0.36 : 0) : 0;
  const amplitude = `${(-48 + Math.min(1, signalLevel) * 36).toFixed(1)} dB`;
  const controlState = { bargeIn, silentMode, alwaysListening };
  const setControl = { bargeIn: setBargeIn, silentMode: setSilentMode, alwaysListening: setAlwaysListening };
  const voiceLoopActive = voiceEnabled && alwaysListening;

  function toggleVoiceLoop() {
    if (speech.status === "blocked") {
      setVoiceEnabled(false);
      window.setTimeout(() => setVoiceEnabled(true), 0);
      return;
    }
    if (!alwaysListening) {
      setAlwaysListening(true);
      setVoiceEnabled(true);
      return;
    }
    setVoiceEnabled((value) => !value);
  }

  return (
    <section className="friday-scroll h-full overflow-y-auto overflow-x-hidden bg-friday-bg p-2 text-white" aria-label="Voice Mode">
      <div className="grid min-w-0 max-w-[980px] gap-2 lg:grid-cols-[minmax(0,2fr)_minmax(260px,.95fr)]">
        <Panel className="min-h-[300px] p-2">
          <div className="flex items-center gap-3">
            <PanelLabel icon={<Activity size={11} />} title="Live Acoustic Stream" />
            <button
              className={`ml-auto min-h-6 rounded-[3px] border px-2 font-mono text-[9px] font-bold uppercase transition-colors ${
                voiceLoopActive && speech.supported ? "border-[#47627e] bg-[#172334] text-friday-accent" : "border-friday-line bg-[#10161d] text-[#b7c4d5]"
              }`}
              type="button"
              onClick={toggleVoiceLoop}
            >
              {voiceButtonLabel(voiceLoopActive, speech)}
            </button>
          </div>
          <div className="grid h-[224px] place-items-center">
            <div className="grid min-w-0 gap-6">
              <div className="flex h-[96px] min-w-0 items-end justify-center gap-[3px]" aria-label="Animated voice waveform">
                {WAVEFORM.map((height, index) => (
                  <span
                    className={`friday-wave-bar w-[5px] rounded-t-[2px] bg-[#9fcaff] shadow-[0_0_12px_rgba(159,202,255,.18)] ${speaking ? "friday-wave-active" : ""}`}
                    style={{ height: `${scaledBarHeight(height, signalLevel)}px`, animationDelay: `${index * 28}ms` }}
                    key={`${height}-${index}`}
                  />
                ))}
              </div>
              <div className="grid grid-cols-3 gap-5 text-center font-mono uppercase">
                <SignalStat label="Frequency" value="44.1 kHz" />
                <SignalStat label="Amplitude" value={amplitude} />
                <SignalStat label="Proxy State" value={voiceProxyState(speech, busy, speaking)} />
              </div>
            </div>
          </div>
        </Panel>

        <Panel className="min-h-[300px] p-2">
          <div className="flex items-center gap-3">
            <PanelLabel title="Live Transcript" />
            <span className="ml-auto font-mono text-[9px] text-friday-accent">{formatClock()}</span>
          </div>
          <div className="friday-scroll mt-3 grid max-h-[242px] gap-3 overflow-y-auto pr-1">
            {transcript.length ? transcript.map((item) => <TranscriptItem item={item} key={item.id} />) : (
              <EmptyLine>No voice transcript is attached to this session yet.</EmptyLine>
            )}
            <div className="flex min-w-0 items-start gap-2 font-mono text-[10px] italic text-[#b7c4d5]">
              <span className="mt-1 h-3 w-px shrink-0 bg-friday-accent" />
              <span className="min-w-0 truncate">{speechStatusText(speech, busy)}</span>
            </div>
          </div>
        </Panel>

        <div className="grid min-w-0 gap-2 lg:col-span-2 lg:grid-cols-[1fr_1.25fr_.95fr]">
          <Panel className="p-2">
            <PanelLabel icon={<Bot size={11} />} title="Neural Engine Metrics" />
            <div className="mt-3 grid grid-cols-2 gap-2">
              {metrics.map((metric) => (
                <div className="min-h-[54px] min-w-0 border border-friday-line bg-[#0c1218] p-2" key={metric.label}>
                  <span className="block truncate font-mono text-[9px] font-bold uppercase text-[#9fcaff]">{metric.label}</span>
                  <strong className="mt-1 block truncate font-mono text-[10px] text-white">{metric.value}</strong>
                </div>
              ))}
            </div>
            <div className="mt-3 flex min-w-0 items-center gap-3">
              <span className="shrink-0 font-mono text-[9px] text-[#a9b6c8]">Wake-word sensitivity</span>
              <span className="h-1 flex-1 bg-[#2a3440]">
                <span className="block h-full w-[72%] bg-friday-accent" />
              </span>
            </div>
          </Panel>

          <Panel className="p-2">
            <PanelLabel icon={<SlidersHorizontal size={11} />} title="Operator Control" />
            <div className="mt-3 grid gap-3">
              {CONTROL_ROWS.map((row) => (
                <ControlRow
                  row={{ ...row, enabled: controlState[row.key], disabled: row.key === "alwaysListening" && !speech.supported }}
                  onToggle={() => setControl[row.key]((value) => !value)}
                  key={row.label}
                />
              ))}
            </div>
          </Panel>

          <Panel className="p-2">
            <div className="flex items-center gap-2">
              <PanelLabel icon={<Mic size={11} />} title="Active Context" />
              <Target className="ml-auto shrink-0 text-[#ffb277]" size={13} />
            </div>
            <div className="mt-3 border border-[#49351d] bg-[#382715] p-2">
              <span className="block font-mono text-[8px] font-bold uppercase text-[#ffb277]">Primary Focus</span>
              <strong className="mt-1 block truncate text-[11px] text-white">{activeContext.focus}</strong>
            </div>
            <div className="mt-3">
              <span className="font-mono text-[8px] font-bold uppercase text-[#9aa8ba]">Referenced Documents</span>
              <div className="mt-2 grid gap-1.5">
                {activeContext.documents.length ? activeContext.documents.map((document) => (
                  <div className="flex min-w-0 items-center gap-2 font-mono text-[10px] text-[#cbd7e6]" key={document}>
                    <FileText className="shrink-0 text-friday-accent" size={11} />
                    <span className="min-w-0 truncate">{document}</span>
                  </div>
                )) : <EmptyLine compact>No referenced document is attached.</EmptyLine>}
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </section>
  );
}

function useMicrophoneLevel() {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) return undefined;
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) return undefined;

    let cancelled = false;
    let frame = 0;
    let stream = null;
    let audioContext = null;

    navigator.mediaDevices
      .getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      })
      .then((mediaStream) => {
        if (cancelled) {
          mediaStream.getTracks().forEach((track) => track.stop());
          return;
        }
        stream = mediaStream;
        audioContext = new AudioContextCtor();
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        analyser.smoothingTimeConstant = 0.74;
        source.connect(analyser);

        const samples = new Uint8Array(analyser.fftSize);
        const tick = () => {
          analyser.getByteTimeDomainData(samples);
          let sum = 0;
          for (const sample of samples) {
            const value = (sample - 128) / 128;
            sum += value * value;
          }
          const rms = Math.sqrt(sum / samples.length);
          const next = Math.min(1, rms * 4.5);
          setLevel((current) => current * 0.62 + next * 0.38);
          frame = requestAnimationFrame(tick);
        };
        tick();
      })
      .catch(() => {
        if (!cancelled) setLevel(0);
      });

    return () => {
      cancelled = true;
      if (frame) cancelAnimationFrame(frame);
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (audioContext?.state !== "closed") audioContext?.close().catch(() => {});
    };
  }, []);

  return level;
}

function useSpeechCommandLoop({ active, hold, token, onFinal }) {
  const [state, setState] = useState({
    supported: true,
    active: false,
    status: "idle",
    interim: "",
    error: "",
    backend: "Deepgram realtime"
  });
  const activeRef = useRef(active);
  const holdRef = useRef(hold);
  const onFinalRef = useRef(onFinal);
  const sendingRef = useRef(false);
  const lastFinalRef = useRef({ text: "", at: 0 });
  const wakeArmedUntilRef = useRef(0);

  useEffect(() => {
    activeRef.current = active;
    holdRef.current = hold;
    onFinalRef.current = onFinal;
  }, [active, hold, onFinal]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    if (!token) {
      setState({ supported: true, active: false, status: "idle", interim: "", error: "", backend: "Deepgram realtime" });
      return undefined;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.WebSocket) {
      setState({
        supported: false,
        active: false,
        status: "unsupported",
        interim: "",
        error: "Realtime microphone streaming is unavailable in this browser.",
        backend: "Deepgram realtime"
      });
      return undefined;
    }
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      setState({
        supported: false,
        active: false,
        status: "unsupported",
        interim: "",
        error: "Web Audio is unavailable in this browser.",
        backend: "Deepgram realtime"
      });
      return undefined;
    }
    let disposed = false;
    let blocked = false;
    let restartTimer = 0;
    let stream = null;
    let audioContext = null;
    let processor = null;
    let source = null;
    let socket = null;
    let targetSampleRate = 16000;

    const update = (patch) => {
      if (!disposed) setState((current) => ({ ...current, ...patch }));
    };

    const cleanupAudio = () => {
      try {
        processor?.disconnect();
      } catch {
        // Ignore teardown races.
      }
      try {
        source?.disconnect();
      } catch {
        // Ignore teardown races.
      }
      try {
        stream?.getTracks().forEach((track) => track.stop());
      } catch {
        // Ignore teardown races.
      }
      try {
        if (audioContext?.state !== "closed") audioContext?.close();
      } catch {
        // Ignore teardown races.
      }
      processor = null;
      source = null;
      stream = null;
      audioContext = null;
    };

    const cleanupSocket = () => {
      try {
        if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "close" }));
      } catch {
        // Ignore teardown races.
      }
      try {
        socket?.close();
      } catch {
        // Ignore teardown races.
      }
      socket = null;
    };

    const cleanup = () => {
      cleanupAudio();
      cleanupSocket();
    };

    const start = async () => {
      if (blocked) {
        update({ active: false, status: "blocked" });
        return;
      }
      if (disposed || !activeRef.current || holdRef.current || sendingRef.current) {
        update({ active: false, status: activeRef.current && holdRef.current ? "waiting" : "idle" });
        return;
      }
      cleanup();
      update({ active: false, status: "connecting", interim: "", error: "" });
      try {
        socket = new WebSocket(wsUrl("/ws/voice/deepgram", token));
        socket.binaryType = "arraybuffer";
        socket.onmessage = (event) => {
          let payload = null;
          try {
            payload = JSON.parse(event.data);
          } catch {
            return;
          }
          if (payload.type === "ready") {
            targetSampleRate = Number(payload.sample_rate) || 16000;
            update({ supported: true, active: true, status: "listening", error: "", backend: `Deepgram ${payload.model || "realtime"}` });
            return;
          }
          if (payload.type === "speech_started") {
            update({ active: true, status: "hearing" });
            return;
          }
          if (payload.type === "error") {
            update({ active: false, status: "error", error: payload.message || "Deepgram speech recognition failed." });
            return;
          }
          if (payload.type !== "transcript") return;
          handleTranscript(payload.text || "", Boolean(payload.is_final || payload.speech_final), payload.confidence);
        };
        socket.onerror = () => {
          update({ active: false, status: "connecting", error: "" });
        };
        socket.onclose = (event) => {
          cleanupAudio();
          const shouldReconnect = !disposed && !blocked && activeRef.current && !sendingRef.current;
          if (event.code === 1008) {
            update({ active: false, status: "error", error: "Voice session expired. Log in again.", interim: "" });
            return;
          }
          if (shouldReconnect) {
            update({ active: false, status: holdRef.current ? "waiting" : "connecting", error: "", interim: "" });
            scheduleRestart(holdRef.current ? 900 : 420);
            return;
          }
          update({ active: false, ...(sendingRef.current ? {} : { interim: "" }) });
        };
        await waitForSocketOpen(socket);
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        });
        audioContext = new AudioContextCtor({ sampleRate: 16000 });
        source = audioContext.createMediaStreamSource(stream);
        processor = audioContext.createScriptProcessor(2048, 1, 1);
        processor.onaudioprocess = (event) => {
          if (disposed || holdRef.current || sendingRef.current || socket?.readyState !== WebSocket.OPEN) return;
          const input = event.inputBuffer.getChannelData(0);
          socket.send(floatTo16BitPcm(input, audioContext?.sampleRate || targetSampleRate, targetSampleRate));
        };
        source.connect(processor);
        processor.connect(audioContext.destination);
        update({ supported: true, active: true, status: "listening", error: "" });
      } catch (err) {
        cleanup();
        const message = err?.name === "NotAllowedError" ? "Microphone permission is blocked." : err?.message || "Deepgram voice stream failed.";
        blocked = err?.name === "NotAllowedError";
        update({ active: false, status: blocked ? "blocked" : "error", error: message });
      }
    };

    const scheduleRestart = (delay = 420) => {
      window.clearTimeout(restartTimer);
      restartTimer = window.setTimeout(start, delay);
    };

    const handleTranscript = (value, isFinal, confidence) => {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      if (!text) return;
      const wakeArmed = Date.now() <= wakeArmedUntilRef.current;
      if (!wakeArmed) wakeArmedUntilRef.current = 0;
      const command = voiceCommandFromTranscript(text, wakeArmed);
      if (command.accepted && command.text) {
        if (isFinal) handleFinal(command.text, confidence);
        else update({ interim: command.text, status: "hearing" });
        return;
      }
      if (command.wakeOnly) {
        if (isFinal) wakeArmedUntilRef.current = Date.now() + WAKE_ARM_MS;
        update({ interim: "Wake name heard. Ask your question.", status: "listening", error: "" });
        return;
      }
      if (!isFinal && text) update({ interim: "", status: "hearing" });
      else if (text) update({ interim: "", status: "listening" });
    };

    const handleFinal = (text, confidence) => {
      const clean = String(text || "").replace(/\s+/g, " ").trim();
      if (!clean || sendingRef.current) return;
      const now = Date.now();
      if (lastFinalRef.current.text === clean && now - lastFinalRef.current.at < 2500) return;
      lastFinalRef.current = { text: clean, at: now };
      wakeArmedUntilRef.current = 0;
      sendingRef.current = true;
      update({ active: false, status: "sending", interim: clean, error: "" });
      cleanup();
      Promise.resolve(onFinalRef.current?.({ text: clean, confidence }))
        .catch((err) => {
          update({ error: err?.message || "Voice command failed.", status: "error" });
        })
        .finally(() => {
          sendingRef.current = false;
          update({ interim: "" });
          if (activeRef.current) scheduleRestart(900);
        });
    };

    if (active && !hold) start();
    else update({ active: false, status: active && hold ? "waiting" : "idle", interim: "" });

    return () => {
      disposed = true;
      window.clearTimeout(restartTimer);
      cleanup();
    };
  }, [active, hold, token]);

  return state;
}

function waitForSocketOpen(socket) {
  if (socket.readyState === WebSocket.OPEN) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      reject(new Error("Deepgram websocket did not open."));
    }, 8000);
    const cleanup = () => {
      window.clearTimeout(timeout);
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("error", onError);
    };
    const onOpen = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("Deepgram websocket failed."));
    };
    socket.addEventListener("open", onOpen);
    socket.addEventListener("error", onError);
  });
}

function floatTo16BitPcm(input, sourceRate = 16000, targetRate = 16000) {
  const samples = resampleFloat32(input, sourceRate, targetRate);
  const output = new ArrayBuffer(samples.length * 2);
  const view = new DataView(output);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(index * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return output;
}

function resampleFloat32(input, sourceRate, targetRate) {
  if (!input.length || Math.round(sourceRate) === Math.round(targetRate)) return input;
  const ratio = sourceRate / targetRate;
  const outputLength = Math.max(1, Math.round(input.length / ratio));
  const output = new Float32Array(outputLength);
  for (let index = 0; index < outputLength; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(input.length, Math.floor((index + 1) * ratio));
    let sum = 0;
    let count = 0;
    for (let sampleIndex = start; sampleIndex < end; sampleIndex += 1) {
      sum += input[sampleIndex];
      count += 1;
    }
    output[index] = count ? sum / count : input[Math.min(start, input.length - 1)];
  }
  return output;
}

function useSpeakFridayReplies(messages, enabled) {
  const initializedRef = useRef(false);
  const lastSpokenRef = useRef("");

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
    const latest = [...(messages || [])].reverse().find((message) => message.role === "friday" && message.text);
    if (!latest) return;
    const id = latest.id || `${latest.timestamp || ""}:${latest.text}`;
    if (!initializedRef.current) {
      initializedRef.current = true;
      lastSpokenRef.current = id;
      return;
    }
    if (id === lastSpokenRef.current) return;
    lastSpokenRef.current = id;
    if (!enabled) return;
    window.speechSynthesis.cancel();
    const utterance = new window.SpeechSynthesisUtterance(trimText(latest.text, 520));
    utterance.rate = 1.02;
    utterance.pitch = 1;
    utterance.volume = 1;
    window.speechSynthesis.speak(utterance);
  }, [enabled, messages]);
}

function Panel({ children, className = "" }) {
  return <section className={`min-w-0 rounded-[4px] border border-friday-line bg-[#151b22] ${className}`}>{children}</section>;
}

function PanelLabel({ icon, title }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5 font-mono text-[9px] font-extrabold uppercase tracking-[.12em] text-[#d9e8fb]">
      {icon ? <span className="shrink-0 text-friday-accent">{icon}</span> : null}
      <span className="min-w-0 truncate">{title}</span>
    </div>
  );
}

function SignalStat({ label, value }) {
  return (
    <div className="min-w-0">
      <span className="block truncate text-[8px] font-bold text-[#8ea1b8]">{label}</span>
      <strong className="mt-1 block truncate text-[9px] text-friday-accent">{value}</strong>
    </div>
  );
}

function TranscriptItem({ item }) {
  const isUser = item.role === "user";
  return (
    <article className="min-w-0">
      <div className="mb-1 flex items-center gap-2 font-mono text-[8px] font-bold">
        <span className={isUser ? "text-[#d9e8fb]" : "text-friday-accent"}>{isUser ? "User" : "Friday"}</span>
        <span className="ml-auto text-[#7f8da0]">{item.timestamp}</span>
      </div>
      <p className={`m-0 min-w-0 border-l-2 p-2 text-[10px] font-semibold leading-relaxed ${isUser ? "border-[#8bbcff] bg-[#263448] text-white" : "border-friday-blue bg-[#143a61] text-[#edf7ff]"}`}>
        {item.text}
      </p>
    </article>
  );
}

function EmptyLine({ children, compact }) {
  return <div className={`rounded-[3px] border border-dashed border-friday-line bg-[#10161d] px-3 py-2 text-[10px] leading-relaxed text-friday-muted ${compact ? "font-mono" : ""}`}>{children}</div>;
}

function ControlRow({ row, onToggle }) {
  const Icon = row.icon;
  return (
    <button className="flex min-w-0 items-center gap-3 text-left disabled:opacity-55" type="button" onClick={row.disabled ? undefined : onToggle} disabled={row.disabled}>
      <Icon className={row.enabled ? "text-friday-accent" : "text-[#9aa8ba]"} size={14} />
      <div className="min-w-0 flex-1">
        <strong className="block truncate font-mono text-[10px] text-white">{row.label}</strong>
        <span className="block truncate text-[9px] text-[#9aa8ba]">{row.detail}</span>
      </div>
      <span className={`relative h-3.5 w-7 shrink-0 rounded-full border ${row.enabled ? "border-[#8bbcff] bg-[#43566d]" : "border-[#3b4654] bg-[#1b222b]"}`}>
        <span className={`absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full ${row.enabled ? "right-0.5 bg-friday-accent" : "left-0.5 bg-[#687789]"}`} />
      </span>
    </button>
  );
}

function transcriptItems(messages, interim = "") {
  const cleaned = (messages || [])
    .filter((message) => ["user", "friday"].includes(message.role) && message.text)
    .slice(-4)
    .map((message, index) => ({
      id: message.id || `${message.role}-${index}`,
      role: message.role,
      text: trimText(message.text, 180),
      timestamp: message.timestamp ? formatMessageTime(message.timestamp) : "--:--:--"
    }));
  if (interim) {
    cleaned.push({
      id: "voice-interim",
      role: "user",
      text: trimText(interim, 180),
      timestamp: "live",
      interim: true
    });
  }
  return cleaned;
}

function buildVoiceMetrics(summary, runtime, speech) {
  const stats = backendStats(summary);
  const accuracy = stats.samples ? `${Math.max(0, Math.round((1 - stats.mistakes / stats.samples) * 1000) / 10).toFixed(1)}%` : "--";
  const latency = runtime.stt_latency_ms || runtime.voice_latency_ms || runtime.latency_ms;
  const sttModel = speech?.backend || [runtime.stt_backend, runtime.stt_model].filter(Boolean).join(" ") || "";
  const voice = [runtime.tts_backend, runtime.edge_voice].filter(Boolean).join(" / ");
  return [
    { label: "STT Latency", value: latencyLabel(latency) },
    { label: "STT Success", value: accuracy },
    { label: "STT Model", value: compactModel(sttModel) || "not reported" },
    { label: "Neural Voice", value: compactModel(voice) || "not reported" }
  ];
}

function backendStats(summary) {
  const backends = summary?.backends || {};
  return Object.values(backends).reduce(
    (acc, item) => ({
      samples: acc.samples + Number(item.samples || 0),
      mistakes: acc.mistakes + Number(item.mistakes || 0)
    }),
    { samples: 0, mistakes: 0 }
  );
}

function latencyLabel(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "--";
  return `${Math.round(number)}ms`;
}

function buildActiveContext(data) {
  const project = data.projectMemory?.projects?.[0] || data.projects?.[0] || {};
  const documents = (data.projectReferences || [])
    .map((item) => item.title || item.filename || item.path)
    .filter(Boolean)
    .slice(0, 3);
  return {
    focus: project.name || project.root_hash || data.contextFusion?.summary || "No project context attached",
    documents
  };
}

function voiceFlag(status) {
  const voice = status?.voice || status?.voiceStatus || status?.voice_status || {};
  return Boolean(
    status?.voice_active ||
      status?.voiceActive ||
      voice.active ||
      voice.speaking ||
      voice.listening ||
      voice.recording ||
      voice.streaming
  );
}

function scaledBarHeight(height, level) {
  const scale = 0.7 + Math.min(1, level) * 0.75;
  return Math.max(10, Math.min(88, Math.round(height * scale)));
}

function voiceButtonLabel(enabled, speech) {
  if (!speech.supported) return "Unsupported";
  if (!enabled) return "Paused";
  if (speech.status === "blocked") return "Mic Blocked";
  if (speech.status === "sending") return "Sending";
  if (speech.status === "connecting") return "Connecting";
  if (speech.status === "hearing") return "Hearing";
  if (speech.status === "waiting") return "Waiting";
  return "Listening";
}

function voiceProxyState(speech, busy, speaking) {
  if (!speech.supported) return "Unsupported";
  if (speech.status === "blocked") return "Blocked";
  if (speech.status === "error") return "Error";
  if (busy || speech.status === "sending") return "Processing";
  if (speech.status === "hearing") return "Hearing";
  if (speech.status === "listening" || speech.active) return "Listening";
  return speaking ? "Processing" : "Idle";
}

function speechStatusText(speech, busy) {
  if (!speech.supported) return "Deepgram realtime voice is unavailable in this browser.";
  if (speech.error) return speech.error;
  if (busy || speech.status === "sending") return "Sending voice command to Friday...";
  if (speech.interim) return `Hearing: ${trimText(speech.interim, 120)}`;
  if (speech.status === "blocked") return "Microphone permission is blocked.";
  if (speech.status === "connecting") return "Connecting to Deepgram realtime STT...";
  if (speech.status === "waiting") return "Friday is replying...";
  if (speech.status === "listening" || speech.active) return "Listening through Deepgram for Friday...";
  return "Voice loop paused.";
}

function voiceCommandFromTranscript(value, wakeArmed = false) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return { accepted: false, text: "" };
  const hasWakeName = mentionsWakeName(text);
  if (!hasWakeName && wakeArmed) return { accepted: true, text };
  if (!hasWakeName) return { accepted: false, text };
  const command = stripWakeName(text);
  if (!command) return { accepted: false, wakeOnly: true, text: "" };
  return { accepted: true, text: command };
}

function mentionsWakeName(value) {
  const normalized = normalizeSpeechText(value);
  const padded = ` ${normalized} `;
  return WAKE_NAMES.some((name) => padded.includes(` ${normalizeSpeechText(name)} `));
}

function stripWakeName(value) {
  let clean = String(value || "").trim();
  for (const name of [...WAKE_NAMES].sort((left, right) => right.length - left.length)) {
    const pattern = escapeRegExp(name).replace(/\s+/g, "\\s+");
    clean = clean.replace(new RegExp(`^\\s*(?:hey|okay|ok)?\\s*${pattern}\\b[\\s,.:;-]*`, "i"), "");
    clean = clean.replace(new RegExp(`\\b${pattern}\\b`, "gi"), "");
  }
  clean = clean.replace(/\b(?:yeah|please)\b\s*$/i, "");
  return clean.replace(/\s+/g, " ").replace(/^[\s,.:;-]+|[\s,.:;-]+$/g, "");
}

function normalizeSpeechText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^\w\s']/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function speechErrorText(error) {
  const value = String(error || "");
  if (value === "not-allowed" || value === "service-not-allowed") return "Microphone permission is blocked.";
  if (value === "audio-capture") return "No microphone was detected.";
  if (value === "network") return "Speech recognition network failed.";
  return `Speech recognition failed: ${value}`;
}

function formatClock() {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function formatMessageTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString([], { hour12: false });
}

function trimText(value, limit) {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  if (clean.length <= limit) return clean;
  return `${clean.slice(0, Math.max(0, limit - 3)).trim()}...`;
}

function compactModel(value) {
  return String(value || "")
    .replace(/^deepgram\s+/i, "Deepgram ")
    .replace(/^edge\s+/i, "Edge ")
    .replace(/speechify/i, "Speechify")
    .trim();
}
