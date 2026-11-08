/**
 * Keep route transitions light. A full-screen logo loader made tab switches feel stuck.
 * Instant navigation feedback lives in RouteProgress (AppShell).
 */
export default function Loading() {
  return <div className="min-h-[12vh]" aria-hidden />;
}
