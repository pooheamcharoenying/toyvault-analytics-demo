import { useState } from "react";

export default function MatchedItemCodesTable({ matchedItemCodes }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      const text = matchedItemCodes.join("\n"); // newline-separated column
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000); // reset after 2s
    } catch (err) {
      console.error("Copy failed:", err);
      alert("Failed to copy to clipboard");
    }
  };

  return (
    <div className="mt-6 mb-6">
      <div className="mb-2 flex justify-between items-center">
        <h2 className="text-lg font-semibold">Matched Item Codes</h2>
        <button
          onClick={handleCopy}
          className="rounded-lg border border-black/10 dark:border-white/20 px-3 py-1.5 text-sm bg-green-100 hover:bg-green-200 dark:hover:bg-green-800"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-black/10 dark:border-white/20">
        <table className="w-full border-collapse">
          <thead>
            <tr className="bg-black/5 dark:bg-white/10">
              <th className="px-3 py-2 text-left text-sm font-medium">
                Item Code
              </th>
            </tr>
          </thead>
          <tbody>
            {matchedItemCodes.map((itemCode, i) => (
              <tr
                key={i}
                className={
                  i % 2 === 0 ? "bg-transparent" : "bg-black/5 dark:bg-white/5"
                }
              >
                <td className="px-3 py-2 text-sm">{itemCode}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
