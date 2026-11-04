export function SampleBanner({
  dataMode,
  notes,
}: {
  dataMode: string;
  notes?: string[];
}) {
  if (dataMode === "live") return null;
  return (
    <div className="sample-banner" role="status">
      <strong>SAMPLE</strong>
      <div>
        <div>
          Data mode: <code>{dataMode}</code>. This view is not live trading
          activity. Worker offline or fixtures in use — nothing here places
          Bybit orders.
        </div>
        {notes?.length ? (
          <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
            {notes.slice(0, 3).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
