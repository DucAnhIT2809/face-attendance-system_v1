export function StatCards({ cards }) {
  return (
    <div className="grid">
      {cards.map((card) => (
        <article key={card.title} className="card">
          <p className="card-title">{card.title}</p>
          <p className="card-value">{card.value}</p>
        </article>
      ))}
    </div>
  );
}

export function DataTable({ headers, rows }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci}>{cell ?? ""}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PageBlock({ title, children }) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}
