/**
 * PNG export for any Recharts chart.
 *
 * Recharts renders into an inline <svg> wrapped by a ResponsiveContainer.
 * We grab that <svg>, inline the resolved colors and font sizes from
 * computedStyle (so CSS variables like --nichi-blue render correctly),
 * rasterize via Image → Canvas at 2× pixel density on a white background,
 * and trigger a download.
 *
 * Usage:
 *   const ref = useRef(null);
 *   ...
 *   <div ref={ref}><ResponsiveContainer><LineChart>...</LineChart>
 *      </ResponsiveContainer></div>
 *   ...
 *   downloadChartAsPng(ref, "monthly-revenue.png")
 *
 * @param {React.RefObject<HTMLElement>} containerRef  ref to a wrapper that
 *        contains the chart's <svg>. The wrapper can be the chart card —
 *        we look for the first descendant <svg> with the .recharts-surface class.
 * @param {string} filename  e.g. "monthly-revenue-2026.png"
 */
export async function downloadChartAsPng(containerRef, filename) {
  const node = containerRef?.current;
  if (!node) return;
  const svg =
    node.querySelector("svg.recharts-surface") ||
    node.querySelector("svg");
  if (!svg) return;

  // Clone so we can safely mutate without affecting the live chart.
  const clone = svg.cloneNode(true);

  // Recharts relies on CSS for color tokens (e.g. var(--nichi-blue)). The
  // inline-svg path that goes through Image.src bypasses our stylesheet, so
  // we walk the live tree and copy each element's computed fill/stroke/
  // font-* onto the clone as inline attributes.
  inlineComputedStyles(svg, clone);

  // Ensure the clone has explicit width/height attrs (so img.onload sizes).
  const bbox = svg.getBoundingClientRect();
  const width = Math.max(1, Math.round(bbox.width));
  const height = Math.max(1, Math.round(bbox.height));
  clone.setAttribute("width", width);
  clone.setAttribute("height", height);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  const svgString = new XMLSerializer().serializeToString(clone);
  const svgBlob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);

  await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      try {
        const dpr = 2;
        const canvas = document.createElement("canvas");
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob((blob) => {
          if (!blob) return reject(new Error("toBlob failed"));
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 0);
          resolve();
        }, "image/png");
      } catch (e) {
        URL.revokeObjectURL(url);
        reject(e);
      }
    };
    img.onerror = (e) => {
      URL.revokeObjectURL(url);
      reject(e);
    };
    img.src = url;
  });
}

const STYLE_PROPS = [
  "fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-opacity",
  "fill-opacity", "opacity", "font-family", "font-size", "font-weight",
  "text-anchor",
];

function inlineComputedStyles(srcRoot, dstRoot) {
  const srcAll = [srcRoot, ...srcRoot.querySelectorAll("*")];
  const dstAll = [dstRoot, ...dstRoot.querySelectorAll("*")];
  // Both trees should have identical structure since dst is a deep clone.
  const n = Math.min(srcAll.length, dstAll.length);
  for (let i = 0; i < n; i++) {
    const src = srcAll[i];
    const dst = dstAll[i];
    // getComputedStyle returns the resolved value for CSS variables.
    const cs = window.getComputedStyle(src);
    for (const prop of STYLE_PROPS) {
      const v = cs.getPropertyValue(prop);
      if (v && v !== "" && v !== "none") {
        dst.setAttribute(prop, v);
      }
    }
  }
}
