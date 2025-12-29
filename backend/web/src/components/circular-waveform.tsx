"use client";

import { MutableRefObject, useEffect, useRef, useState } from "react";

const elementSources = new WeakMap<
  HTMLMediaElement,
  { ctx: AudioContext; source: MediaElementAudioSourceNode | MediaStreamAudioSourceNode; analyser: AnalyserNode }
>();

type Props = {
  audioRef: MutableRefObject<HTMLAudioElement | null>;
  size?: number;
  barCount?: number;
  barColor?: string;
  barWidth?: number;
  radius?: number;
  waveAmplitude?: number;
  barMinHeight?: number;
  growOutwardsOnly?: boolean;
  strokeLinecap?: "butt" | "round" | "square";
  waveSpeed?: number;
  randomness?: number;
  centerOffset?: { x?: number; y?: number };
};

// Circular waveform driven by an analyser on the audio element.
export default function CircularWaveform({
  audioRef,
  size = 220,
  barCount = 64,
  barColor = "rgba(115,130,255,0.9)",
  barWidth = 5,
  radius,
  waveAmplitude = 80,
  barMinHeight = 10,
  growOutwardsOnly = false,
  strokeLinecap = "round",
  waveSpeed = 8, // higher is faster wobble
  randomness = 0.2, // 0..1 jitter factor
  centerOffset = { x: 0, y: 0 },
}: Props) {
  const [bars, setBars] = useState<number[]>(() => new Array(barCount).fill(0.1));
  const analyserRef = useRef<AnalyserNode | null>(null);
  const dataArrayRef = useRef<Uint8Array | null>(null);
  const rafRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaElementAudioSourceNode | MediaStreamAudioSourceNode | null>(null);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    // Reuse if already wired for this element
    const existing = elementSources.get(el);
    if (existing) {
      audioCtxRef.current = existing.ctx;
      sourceRef.current = existing.source;
      analyserRef.current = existing.analyser;
    }
    if (analyserRef.current && sourceRef.current && audioCtxRef.current) {
      return;
    }

    const audioCtx = new AudioContext();
    let source: MediaElementAudioSourceNode | MediaStreamAudioSourceNode | null = null;
    if (el.captureStream) {
      const stream = el.captureStream();
      if (stream.getAudioTracks().length) {
        source = audioCtx.createMediaStreamSource(stream);
      }
    }
    if (!source) {
      try {
        source = audioCtx.createMediaElementSource(el);
      } catch (err) {
        console.warn("circular-waveform: media element already has a source, reuse existing", err);
        audioCtx.close();
        return;
      }
    }

    audioCtxRef.current = audioCtx;
    sourceRef.current = source;

    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.65;
    source.connect(analyser);
    analyser.connect(audioCtx.destination);

    analyserRef.current = analyser;
    const bufferLength = analyser.frequencyBinCount;
    dataArrayRef.current = new Uint8Array(bufferLength);
    elementSources.set(el, { ctx: audioCtx, source, analyser });

    const update = () => {
      if (!analyserRef.current || !dataArrayRef.current) return;
      analyserRef.current.getByteFrequencyData(dataArrayRef.current);
      const freqLen = dataArrayRef.current.length;
      // Build a small set of bands (log-ish) and tile them around the ring so the whole circle moves.
      const bandCount = Math.min(barCount, freqLen);
      const globalEnergy =
        dataArrayRef.current.reduce((acc, v) => acc + v, 0) /
        Math.max(1, dataArrayRef.current.length) /
        255;
      const bands: number[] = [];
      for (let b = 0; b < bandCount; b++) {
        const t0 = b / bandCount;
        const t1 = (b + 1) / bandCount;
        const start = Math.floor(Math.pow(t0, 0.6) * (freqLen - 1));
        const end = Math.floor(Math.pow(t1, 0.6) * (freqLen - 1));
        const slice = dataArrayRef.current!.slice(start, Math.max(start + 1, end));
        const avg = slice.reduce((acc, v) => acc + v, 0) / Math.max(1, slice.length);
        bands.push(Math.pow(avg / 255, 0.85)); // light emphasis for highs
      }

      setBars((prev) => {
        const t = performance.now() / 1000;
        const nextBars: number[] = [];
        for (let i = 0; i < barCount; i++) {
          const bandIdx = Math.floor((i / Math.max(1, barCount - 1)) * Math.max(1, bandCount - 1));
          const bandVal = bands[bandIdx] ?? 0;
          const blended = bandVal * 0.7 + globalEnergy * 0.3;
          const prevVal = prev[i] ?? 0;
          const jitter = Math.sin(t * waveSpeed + i * 0.35) * randomness;
          nextBars.push(prevVal * 0.5 + (blended + jitter) * 0.5);
        }
        return nextBars;
      });
      rafRef.current = requestAnimationFrame(update);
    };
    rafRef.current = requestAnimationFrame(update);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [audioRef, barCount]);

  const computedRadius = radius ?? size * 0.3;
  const center = size / 2;

  return (
    <div style={{ width: "100%", display: "flex", justifyContent: "center", padding: 8 }}>
      <svg width={size} height={size} style={{ overflow: "visible" }}>
        {bars.map((v, i) => {
          const angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;
          const barLen = Math.max(barMinHeight, v * waveAmplitude + barMinHeight);
          const rStart = growOutwardsOnly ? computedRadius : Math.max(0, computedRadius - barLen / 2);
          const rEnd = growOutwardsOnly ? computedRadius + barLen : computedRadius + barLen / 2;
          const x1 = center + (centerOffset.x ?? 0) + rStart * Math.cos(angle);
          const y1 = center + (centerOffset.y ?? 0) + rStart * Math.sin(angle);
          const x2 = center + (centerOffset.x ?? 0) + rEnd * Math.cos(angle);
          const y2 = center + (centerOffset.y ?? 0) + rEnd * Math.sin(angle);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={barColor} strokeWidth={barWidth} strokeLinecap={strokeLinecap} />;
        })}
      </svg>
    </div>
  );
}
