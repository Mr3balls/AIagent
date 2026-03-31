import { safeJsonStringify } from "@/lib/utils";

interface RawJsonViewProps {
  data: unknown;
}

export function RawJsonView({ data }: RawJsonViewProps) {
  return (
    <div className="card">
      <h3>Raw JSON</h3>
      <pre className="json-block">{safeJsonStringify(data)}</pre>
    </div>
  );
}