import type { ObservabilityEvent } from "@/lib/observability/types";
import { sortEventsChronological } from "@/lib/observability/events";

export function EventTimeline({
  events,
  sample,
}: {
  events: ObservabilityEvent[];
  sample?: boolean;
}) {
  const ordered = sortEventsChronological(events).slice().reverse();
  return (
    <section className="panel" aria-label="Event timeline">
      <h2>
        Event timeline {sample ? <span className="badge sample">SAMPLE</span> : null}
      </h2>
      {ordered.length === 0 ? (
        <p className="muted">No events — disconnected or unavailable.</p>
      ) : (
        <ol className="timeline">
          {ordered.map((ev) => (
            <li key={ev.event_id}>
              <div className="ts">
                {new Date(ev.occurred_at).toISOString()} · {ev.event_type}
              </div>
              <div>{ev.message}</div>
              <div className="muted">
                corr={ev.correlation_id ?? "—"} · id={ev.event_id}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
