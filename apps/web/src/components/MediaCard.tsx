import { useState } from "react";
import { Link } from "react-router-dom";
import type { ExternalLink, Item, ItemState, MediaType, RatingLabel } from "../api";
import { api, RATING_LABELS } from "../api";
import { IN_PROGRESS_LABEL } from "../domains";
import { Poster } from "./Poster";

function stateOptions(media: MediaType): { value: ItemState; label: string }[] {
  return [
    { value: "interested", label: "Interested" },
    { value: "shortlisted", label: "Shortlist" },
    { value: "in_progress", label: IN_PROGRESS_LABEL[media] },
    { value: "completed", label: "Completed" },
    { value: "passed", label: "Pass" },
    { value: "hidden", label: "Hide" },
  ];
}

export interface MediaCardProps {
  item: Item;
  mediaType: MediaType;
  domainSlug: string;
  rank?: number;
  score?: number;
  explanation?: string | null;
  factors?: Record<string, unknown>;
  eventId?: string;
  currentState?: ItemState | null;
  notes?: string | null;
  busy?: boolean;
  onSetState: (itemId: string, state: ItemState, notes?: string) => void;
  onClearState: (itemId: string) => void;
  onAct?: (eventId: string, action: string, ratingLabel?: RatingLabel) => void;
}

export default function MediaCard(props: MediaCardProps) {
  const { item, mediaType, currentState, busy } = props;
  const [showRating, setShowRating] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [notes, setNotes] = useState(props.notes ?? "");
  const [links, setLinks] = useState<ExternalLink[] | null>(null);
  const [linksOpen, setLinksOpen] = useState(false);
  const [linksBusy, setLinksBusy] = useState(false);

  const factors = props.factors as
    | {
        reasons?: string[];
        structured?: {
          shared_tags?: string[];
          same_creator?: string[];
          candidate_layers?: string[];
          community_overlap?: number;
        };
      }
    | undefined;
  const reasons = factors?.reasons ?? [];
  const structured = factors?.structured;

  async function toggleSources() {
    const next = !linksOpen;
    setLinksOpen(next);
    if (next && links === null) {
      setLinksBusy(true);
      try {
        setLinks(await api.itemLinks(props.domainSlug, item.id));
      } catch {
        setLinks([]);
      } finally {
        setLinksBusy(false);
      }
    }
  }

  function toggleState(value: ItemState) {
    if (currentState === value) props.onClearState(item.id);
    else props.onSetState(item.id, value, notes || undefined);
  }

  return (
    <article className="media-card">
      <Link to={`/${props.domainSlug}/item/${item.id}`} aria-label={item.title}>
        <Poster src={item.cover_url} title={item.title} wide={mediaType === "game"} />
      </Link>
      <div className="meta">
        {props.rank != null && <span className="chip">#{props.rank}</span>}
        {props.score != null && <span className="chip mono">score {props.score.toFixed(3)}</span>}
        <span className="chip">{item.media_type}</span>
        {item.release_year && <span className="chip">{item.release_year}</span>}
      </div>
      <h3>
        <Link className="title-link" to={`/${props.domainSlug}/item/${item.id}`}>
          {item.title}
        </Link>
      </h3>
      {item.series && <p className="muted small">{item.series}</p>}
      <div className="meta">
        {(item.genres || []).slice(0, 4).map((g) => (
          <span className="chip" key={g}>
            {g}
          </span>
        ))}
      </div>
      {props.explanation ? <p className="explanation">{props.explanation}</p> : null}
      {structured && (structured.candidate_layers?.length || structured.shared_tags?.length) ? (
        <div className="meta">
          {(structured.candidate_layers || []).map((l) => (
            <span className="chip layer" key={`layer-${l}`}>
              {l}
            </span>
          ))}
          {(structured.shared_tags || []).slice(0, 3).map((t) => (
            <span className="chip" key={`tag-${t}`}>
              #{t}
            </span>
          ))}
        </div>
      ) : null}
      {reasons.length > 0 && <p className="factors">reasons: {reasons.join(", ")}</p>}

      <div className="state-row">
        {stateOptions(mediaType).map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={busy}
            className={`chip-btn ${currentState === opt.value ? "active" : ""}`}
            onClick={() => toggleState(opt.value)}
          >
            {opt.label}
          </button>
        ))}
        <button type="button" className="chip-btn" disabled={busy} onClick={() => setShowNotes((s) => !s)}>
          {showNotes ? "Hide note" : "Note"}
        </button>
        <button type="button" className="chip-btn" onClick={toggleSources}>
          {linksOpen ? "Hide sources" : "Sources"}
        </button>
      </div>

      {linksOpen && (
        <div className="sources">
          {linksBusy && <span className="muted small">Resolving…</span>}
          {!linksBusy && links && links.length === 0 && (
            <span className="muted small">No sources resolved.</span>
          )}
          {!linksBusy &&
            (links || []).map((l) => (
              <a
                key={l.provider}
                className={`source-link ${l.verified ? "verified" : "unverified"}`}
                href={l.external_url}
                target="_blank"
                rel="noopener noreferrer"
                title={l.verified ? `${l.label} (verified)` : `Search ${l.label} (unverified)`}
              >
                {l.label}
                {!l.verified && <span className="src-flag">search</span>}
              </a>
            ))}
        </div>
      )}

      {showNotes && (
        <div className="row">
          <input
            className="input"
            placeholder="Recommended by… / Watch with family…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => props.onSetState(item.id, currentState ?? "interested", notes || undefined)}
          >
            Save note
          </button>
        </div>
      )}

      {props.eventId && props.onAct && (
        <div className="row">
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={() => setShowRating((s) => !s)}>
            Rate
          </button>
          <button
            className="btn btn-primary"
            type="button"
            disabled={busy}
            onClick={() => props.onAct!(props.eventId!, "consume")}
          >
            Consumed
          </button>
        </div>
      )}
      {showRating && props.eventId && props.onAct && (
        <div className="rating-row">
          {RATING_LABELS.map((label) => (
            <button
              key={label}
              type="button"
              className="btn btn-secondary"
              onClick={() => props.onAct!(props.eventId!, "rate", label)}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}
