import type { OrderLifecycleItem } from "@/lib/observability/types";

export function OrderLifecycle({ orders }: { orders: OrderLifecycleItem[] }) {
  return (
    <section className="panel" aria-label="Order lifecycle">
      <h2>Order lifecycle</h2>
      {orders.length === 0 ? (
        <p className="muted">No intents in this snapshot.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Client ID</th>
              <th>State</th>
              <th>Side</th>
              <th>Qty</th>
              <th>Filled</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.client_order_id}>
                <td>
                  {o.client_order_id}
                  {o.sample ? " · SAMPLE" : ""}
                </td>
                <td>{o.state}</td>
                <td>{o.side ?? "—"}</td>
                <td>{o.qty ?? "—"}</td>
                <td>{o.filled_qty ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
