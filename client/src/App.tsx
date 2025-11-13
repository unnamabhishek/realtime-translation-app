import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import DailyIframe, { DailyCall, DailyEventObjectParticipant, DailyEventObjectParticipantLeft, DailyParticipant } from "@daily-co/daily-js";

type TranscriptEntry = {
  id: string;
  text: string;
  timestamp: number;
};

type TrackInfo = {
  track: MediaStreamTrack;
  participantId: string;
};

const LANGUAGE_OPTIONS = [{ id: "hindi", label: "Hindi" }];

const labelize = (languageId: string) =>
  LANGUAGE_OPTIONS.find((option) => option.id === languageId)?.label ??
  languageId.toUpperCase();

const MAX_TRANSCRIPTS_PER_LANGUAGE = 30;
const generateEntryId = () =>
  typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
const toMillis = (value: number) => (value < 1_000_000_000_000 ? value * 1000 : value);

const BAR_COUNT = 20;
const createWaveformBaseline = () => new Array(BAR_COUNT).fill(0.2);
const MAX_TOKENS_PER_UTTERANCE = 18;
const STANDALONE_PUNCTUATION = /^[,.;:?!।॥…]+$/;
const SENTENCE_ENDINGS = /[.?!।॥…]$/;

type Utterance = {
  id: string;
  entries: TranscriptEntry[];
  timestamp: number;
  text: string;
};

const formatUtteranceText = (entries: TranscriptEntry[]) =>
  entries
    .map((entry, index) => {
      const token = entry.text.trim();
      if (!token) {
        return "";
      }
      if (index === 0 || STANDALONE_PUNCTUATION.test(token)) {
        return token;
      }
      return ` ${token}`;
    })
    .join("")
    .replace(/\s+([,.;:?!।॥…])/g, "$1 ");

const buildUtterances = (entries: TranscriptEntry[]) => {
  const utterances: Utterance[] = [];
  const wordToUtterance: Record<string, string> = {};
  let current: Utterance | null = null;

  const finalizeCurrent = () => {
    if (!current) {
      return;
    }
    current.text = formatUtteranceText(current.entries);
    current = null;
  };

  entries.forEach((entry) => {
    const token = entry.text.trim();
    if (!token) {
      return;
    }
    if (!current) {
      current = {
        id: `${entry.id}-utt`,
        entries: [],
        timestamp: entry.timestamp,
        text: ""
      };
      utterances.push(current);
    }

    current.entries.push(entry);
    wordToUtterance[entry.id] = current.id;

    const reachedBoundary =
      current.entries.length >= MAX_TOKENS_PER_UTTERANCE ||
      SENTENCE_ENDINGS.test(token.slice(-1)) ||
      STANDALONE_PUNCTUATION.test(token);

    if (reachedBoundary) {
      finalizeCurrent();
    }
  });

  finalizeCurrent();

  return { utterances, wordToUtterance };
};

type LanguageDetailProps = {
  language: string;
  track?: MediaStreamTrack;
  transcripts: TranscriptEntry[];
};

// Handles the right-hand pane: audio playback controls, waveform, and transcript stream.
const LanguageDetail = ({ language, track, transcripts }: LanguageDetailProps) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [waveformValues, setWaveformValues] = useState<number[]>(createWaveformBaseline);
  const [activeWordId, setActiveWordId] = useState<string | null>(null);
  const [activeUtteranceId, setActiveUtteranceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const transcriptScrollRef = useRef<HTMLDivElement | null>(null);

  const { utterances, wordToUtterance } = useMemo(() => buildUtterances(transcripts), [transcripts]);
  const orderedUtterances = useMemo(() => [...utterances].reverse(), [utterances]);
  const hasTrack = Boolean(track);

  useEffect(() => {
    if (!transcripts.length) {
      setActiveWordId(null);
      return;
    }
    setActiveWordId(transcripts[transcripts.length - 1].id);
  }, [transcripts]);

  useEffect(() => {
    if (!activeWordId) {
      return;
    }
    setActiveUtteranceId(wordToUtterance[activeWordId] ?? null);
  }, [activeWordId, wordToUtterance]);

  useEffect(() => {
    if (!hasTrack) {
      setActiveWordId(null);
      setActiveUtteranceId(null);
    }
  }, [hasTrack]);

  useEffect(() => {
    if (!hasTrack || !utterances.length) {
      return;
    }
    const node = transcriptScrollRef.current;
    if (node) {
      node.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [hasTrack, utterances.length]);

  useEffect(() => {
    if (!isPlaying || !utterances.length) {
      return;
    }
    setActiveUtteranceId((prev) => prev ?? utterances[utterances.length - 1].id);
  }, [isPlaying, utterances]);

  const teardownAudioGraph = useCallback(async () => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    sourceRef.current?.disconnect();
    analyserRef.current?.disconnect();
    sourceRef.current = null;
    analyserRef.current = null;

    if (audioContextRef.current) {
      try {
        // Only close if the context is not already closed
        if (audioContextRef.current.state !== "closed") {
          await audioContextRef.current.close();
        }
      } catch (error) {
        console.warn("Failed to close audio context", error);
      }
      audioContextRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!track) {
      setIsPlaying(false);
      audioRef.current?.pause();
      if (audioRef.current) {
        audioRef.current.srcObject = null;
      }
      setWaveformValues(createWaveformBaseline());
      teardownAudioGraph();
      return;
    }

    const setupAudio = async () => {
      if (!audioRef.current) {
        return;
      }
      await teardownAudioGraph();

      const stream = new MediaStream([track]);
      audioRef.current.srcObject = stream;
      audioRef.current.muted = false;
      audioRef.current.autoplay = false;

      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.85;
      source.connect(analyser);

      const frequencyData = new Uint8Array(analyser.frequencyBinCount);

      const updateWaveform = () => {
        analyser.getByteFrequencyData(frequencyData);
        const sliceSize = Math.max(1, Math.floor(frequencyData.length / BAR_COUNT));
        const values = new Array(BAR_COUNT).fill(0).map((_, index) => {
          const start = index * sliceSize;
          const window = frequencyData.slice(start, start + sliceSize);
          const avg =
            window.reduce((acc, val) => acc + val, 0) / Math.max(1, window.length) / 255;
          return avg;
        });

        setWaveformValues(values);
        animationRef.current = requestAnimationFrame(updateWaveform);
      };

      updateWaveform();
      audioContextRef.current = audioContext;
      sourceRef.current = source;
      analyserRef.current = analyser;
    };

    setupAudio();

    return () => {
      audioRef.current?.pause();
      const mediaStream = audioRef.current?.srcObject as MediaStream | null;
      mediaStream?.getTracks().forEach((t) => t.stop());
      if (audioRef.current) {
        audioRef.current.srcObject = null;
      }
      teardownAudioGraph();
    };
  }, [language, track, teardownAudioGraph]);

  const togglePlayback = async () => {
    if (!track || !audioRef.current) {
      return;
    }

    try {
      // Only resume if the context exists and is suspended (not closed)
      if (audioContextRef.current && audioContextRef.current.state === "suspended") {
        await audioContextRef.current.resume();
      }

      if (isPlaying) {
        audioRef.current.pause();
        setIsPlaying(false);
      } else {
        await audioRef.current.play();
        setIsPlaying(true);
        if (utterances.length) {
          setActiveUtteranceId(utterances[utterances.length - 1].id);
        }
      }
    } catch (error) {
      console.error(`Unable to toggle audio for ${language}`, error);
      setIsPlaying(false);
    }
  };

  const waveformClass = `waveform ${isPlaying ? "active" : ""}`;
  const playbackButtonClass = `primary primary--large ${isPlaying ? "primary--active" : ""}`;

  return (
    <div className="language-detail">
      <header>
        <div>
          <p className="eyebrow">Currently listening to</p>
          <h2>{labelize(language)}</h2>
        </div>
        <button
          className={playbackButtonClass}
          onClick={togglePlayback}
          disabled={!track}
          type="button"
        >
          {track ? (isPlaying ? "Pause Audio" : "Play Audio") : "Waiting for audio"}
        </button>
      </header>
      <div className="detail-body">
        <div className="waveform-card">
          <p className="subtitle">Live audio visualizer</p>
          <div className={waveformClass}>
            {waveformValues.map((value, index) => (
              <span
                key={`${language}-wave-${index}`}
                style={{ height: `${Math.max(10, value * 100)}%` }}
              />
            ))}
          </div>
          <p className="hint">
            {track
              ? isPlaying
                ? "Audio is currently streaming."
                : "Press play to start listening."
              : "Waiting for the bot to publish this track."}
          </p>
        </div>
        <div className="transcript-panel">
          <header>
            <h3>Live Transcript</h3>
          </header>
          <div className="transcript-scroll" ref={transcriptScrollRef}>
            {!hasTrack ? (
              <p className="placeholder">Waiting for the bot to publish this track.</p>
            ) : !utterances.length ? (
              <p className="placeholder">Audio ready. Waiting for spoken text…</p>
            ) : (
              orderedUtterances.map((utterance) => (
                <article
                  key={utterance.id}
                  className={`transcript-utterance ${
                    activeUtteranceId === utterance.id ? "transcript-utterance--active" : ""
                  }`}
                >
                  <time className="timestamp">
                    {new Date(toMillis(utterance.timestamp)).toLocaleTimeString()}
                  </time>
                  <div className="utterance-text">
                    {utterance.entries.map((entry) => {
                      const isWordActive = entry.id === activeWordId;
                      return (
                        <span
                          key={entry.id}
                          className={`transcript-word ${
                            isWordActive ? "transcript-word--active" : ""
                          }`}
                        >
                          {entry.text}
                        </span>
                      );
                    })}
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
      </div>
      <audio ref={audioRef} className="sr-only" />
    </div>
  );
};

const DailyContext = createContext<DailyCall | null>(null);

const useDailyCall = () => {
  const context = useContext(DailyContext);
  if (!context) {
    throw new Error("useDailyCall must be used within DailyProvider");
  }
  return context;
};

const DailyProvider = ({
  callObject,
  children
}: {
  callObject: DailyCall;
  children: ReactNode;
}) => {
  return <DailyContext.Provider value={callObject}>{children}</DailyContext.Provider>;
};

// Houses all of the meeting-specific state so the top-level App only deals with Daily initialization.
const ClientApp = () => {
  const daily = useDailyCall();
  const [meetingUrl, setMeetingUrl] = useState("");
  const [status, setStatus] = useState<"idle" | "joining" | "joined">("idle");
  const [error, setError] = useState<string | null>(null);
  const [tracks, setTracks] = useState<Record<string, TrackInfo>>({});
  const [transcripts, setTranscripts] = useState<Record<string, TranscriptEntry[]>>({});
  const [activeLanguage, setActiveLanguage] = useState<string>(LANGUAGE_OPTIONS[0].id);

  const resetState = useCallback(() => {
    setTracks({});
    setTranscripts({});
    setError(null);
  }, []);

  // Subscribe to custom audio tracks published by the translation bot.
  const subscribeToParticipant = useCallback(
    (participant: DailyParticipant) => {
      if (!daily || participant.local) {
        return;
      }

      daily.updateParticipant(participant.session_id, {
        setSubscribedTracks: {
          audio: true,
          video: false,
          custom: true
        }
      });
    },
    [daily]
  );

  // Clean up audio tracks when a publisher leaves.
  const removeTracksForParticipant = useCallback((participantId: string) => {
    setTracks((prev) =>
      Object.fromEntries(
        Object.entries(prev).filter(([, info]) => info.participantId !== participantId)
      )
    );
  }, []);

  // Append translated text while capping how many entries we keep per language.
  const appendTranscript = useCallback(
    (language: string, text: string, timestamp: number) => {
      if (!text?.trim()) {
        return;
      }

      setTranscripts((prev) => {
        const next = { ...prev };
        const entry: TranscriptEntry = {
          id: `${language}-${timestamp}-${generateEntryId()}`,
          text,
          timestamp
        };
        const languageEntries = next[language] ? [...next[language], entry] : [entry];
        next[language] = languageEntries.slice(-MAX_TRANSCRIPTS_PER_LANGUAGE);
        return next;
      });
    },
    []
  );

  const handleAppMessage = useCallback(
    (event: any) => {
      try {
        const parsed =
          typeof event.data === "string" ? JSON.parse(event.data) : (event.data ?? {});
        if (parsed?.type === "translation-transcript") {
          appendTranscript(parsed.language, parsed.text, parsed.timestamp ?? Date.now());
        }
      } catch (err) {
        console.warn("Unable to parse app-message payload", err);
      }
    },
    [appendTranscript]
  );

  // When Daily begins sending a translation track, store it so the UI can render controls.
  const handleTrackStarted = useCallback((event: any) => {
    if (event.track.kind !== "audio") {
      return;
    }
    const tag = (event.track as MediaStreamTrack & { _mediaTag?: string })._mediaTag;
    if (!tag || tag === "cam-audio") {
      return;
    }
    setTracks((prev) => ({
      ...prev,
      [tag]: {
        track: event.track,
        participantId: event.participant?.session_id ?? "remote"
      }
    }));
  }, []);

  // Remove tracks when Daily reports they stopped to avoid dangling audio nodes.
  const handleTrackStopped = useCallback((event: any) => {
    const tag = (event.track as MediaStreamTrack & { _mediaTag?: string })._mediaTag;
    if (!tag) {
      return;
    }
    setTracks((prev) => {
      if (!(tag in prev)) {
        return prev;
      }
      const next = { ...prev };
      delete next[tag];
      return next;
    });
  }, []);

  useEffect(() => {
    if (!daily) {
      return;
    }

    // Mirror Daily's participant events so we can subscribe/unsubscribe without default automation.
    const onParticipantJoined = (event?: DailyEventObjectParticipant) => {
      if (!event?.participant) {
        return;
      }
      subscribeToParticipant(event.participant);
    };

    const onParticipantUpdated = (event?: DailyEventObjectParticipant) => {
      if (!event?.participant || event.participant.local) {
        return;
      }
      subscribeToParticipant(event.participant);
    };

    const onParticipantLeft = (event?: DailyEventObjectParticipantLeft) => {
      if (event?.participant?.session_id) {
        removeTracksForParticipant(event.participant.session_id);
      }
    };

    daily.on("participant-joined", onParticipantJoined);
    daily.on("participant-updated", onParticipantUpdated);
    daily.on("participant-left", onParticipantLeft);
    daily.on("track-started", handleTrackStarted);
    daily.on("track-stopped", handleTrackStopped);
    daily.on("app-message", handleAppMessage);

    return () => {
      daily.off("participant-joined", onParticipantJoined);
      daily.off("participant-updated", onParticipantUpdated);
      daily.off("participant-left", onParticipantLeft);
      daily.off("track-started", handleTrackStarted);
      daily.off("track-stopped", handleTrackStopped);
      daily.off("app-message", handleAppMessage);
    };
  }, [
    daily,
    handleAppMessage,
    handleTrackStarted,
    handleTrackStopped,
    removeTracksForParticipant,
    subscribeToParticipant
  ]);

  // Join the Daily room with manual track subscription so we control which audio streams arrive.
  const joinMeeting = async () => {
    if (!daily || !meetingUrl || status === "joining") {
      return;
    }
    setStatus("joining");
    setError(null);
    try {
      await daily.join({
        url: meetingUrl,
        subscribeToTracksAutomatically: false,
        startVideoOff: true,
        startAudioOff: true
      });
      setStatus("joined");
    } catch (err) {
      console.error(err);
      setError("Unable to join the Daily room. Check the URL and try again.");
      setStatus("idle");
    }
  };

  // Explicit leave path so we can reset UI state after Daily disconnects.
  const leaveMeeting = async () => {
    if (!daily) {
      return;
    }
    await daily.leave();
    resetState();
    setStatus("idle");
  };

  useEffect(() => {
    return () => {
      daily?.leave();
    };
  }, [daily]);

  return (
    <div className="app two-pane">
      <section className="card pane pane--left">
        <div className="card-section">
          <h1>Daily Multi Translation</h1>
          <p className="subtitle">
            Paste the Daily room URL from the FastAPI server, then monitor one translation at a
            time with audio, visualizer, and rolling transcripts.
          </p>
          <label className="field">
            <span>Meeting URL</span>
            <input
              value={meetingUrl}
              onChange={(event) => setMeetingUrl(event.target.value)}
              placeholder="https://your-team.daily.co/room-name"
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              onClick={joinMeeting}
              disabled={!meetingUrl || status === "joining" || status === "joined"}
              type="button"
            >
              {status === "joining" ? "Joining…" : "Join"}
            </button>
            <button
              className="ghost"
              onClick={leaveMeeting}
              disabled={status !== "joined"}
              type="button"
            >
              Leave
            </button>
          </div>
          {error ? <p className="error">{error}</p> : null}
        </div>
        <div className="card-section">
          <h2>Available languages</h2>
          <p className="subtitle">Pick one destination language to focus on.</p>
          <div className="language-stack">
            {LANGUAGE_OPTIONS.map((language) => (
              <button
                key={language.id}
                className={`language-card ${
                  activeLanguage === language.id ? "language-card--active" : ""
                }`}
                onClick={() => {
                  setActiveLanguage(language.id);
                }}
                type="button"
              >
                <div>
                  <p className="language-name">{language.label}</p>
                  <p className="language-status">
                    {tracks[language.id] ? "Track ready" : "Waiting for track"}
                  </p>
                </div>
                <span className="language-chevron">›</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="card pane pane--right">
        <LanguageDetail
          language={activeLanguage}
          track={tracks[activeLanguage]?.track}
          transcripts={transcripts[activeLanguage] ?? []}
        />
      </section>
    </div>
  );
};

const App = () => {
  const [callObject, setCallObject] = useState<DailyCall | null>(null);
  const callObjectRef = useRef<DailyCall | null>(null);
  const destroyPromiseRef = useRef<Promise<void> | null>(null);

  // Maintain a single Daily callObject instance even when React StrictMode remounts happen.
  useEffect(() => {
    let isMounted = true;

    const ensureCallObject = async () => {
      if (destroyPromiseRef.current) {
        await destroyPromiseRef.current;
      }
      if (!isMounted) {
        return;
      }
      if (!callObjectRef.current) {
        callObjectRef.current = DailyIframe.createCallObject({
          subscribeToTracksAutomatically: false
        });
      }
      if (isMounted) {
        setCallObject(callObjectRef.current);
      }
    };

    ensureCallObject();

    return () => {
      isMounted = false;
      const instance = callObjectRef.current;
      if (!instance || destroyPromiseRef.current) {
        return;
      }
      destroyPromiseRef.current = (async () => {
        try {
          await instance.leave();
        } catch (error) {
          console.warn("Unable to leave Daily call during cleanup", error);
        }
        try {
          await instance.destroy();
        } catch (error) {
          console.warn("Unable to destroy Daily call instance", error);
        } finally {
          if (callObjectRef.current === instance) {
            callObjectRef.current = null;
          }
          destroyPromiseRef.current = null;
        }
      })();
    };
  }, []);

  if (!callObject) {
    return null;
  }

  return (
    <DailyProvider callObject={callObject}>
      <ClientApp />
    </DailyProvider>
  );
};

export default App;
