import type { ReactNode } from "react";

export type DataColumn<Row extends Record<string, unknown>> = {
  key: keyof Row & string;
  header: string;
  render?: (value: Row[keyof Row], row: Row) => ReactNode;
};

export function DataTable<Row extends Record<string, unknown>>({ columns, rows, rowKey }: { columns: DataColumn<Row>[]; rows: Row[]; rowKey: keyof Row & string }) {
  return <div className="data-table-wrap"><table className="data-table"><thead><tr>{columns.map(column => <th key={column.key} scope="col">{column.header}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={String(row[rowKey])}>{columns.map(column => <td key={column.key}>{column.render ? column.render(row[column.key], row) : String(row[column.key] ?? "—")}</td>)}</tr>)}</tbody></table></div>;
}
