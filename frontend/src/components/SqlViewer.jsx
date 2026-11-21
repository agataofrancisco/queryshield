import CodeMirror from "@uiw/react-codemirror";
import { sql, PostgreSQL } from "@codemirror/lang-sql";

// SQL só para leitura, com realce. Nunca editável: o utilizador não altera o SQL validado.
export default function SqlViewer({ value }) {
  const text = typeof value === "string" ? value : "";
  return (
    <div className="sql-viewer" aria-label="SQL gerado">
      <CodeMirror
        value={text}
        theme="light"
        editable={false}
        readOnly
        basicSetup={{ lineNumbers: false, foldGutter: false, highlightActiveLine: false }}
        extensions={[sql({ dialect: PostgreSQL })]}
      />
    </div>
  );
}
