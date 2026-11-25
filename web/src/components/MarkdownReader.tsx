"use client";

import { Flex, Typography, theme } from "antd";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type Heading = { id: string; level: number; text: string };

/** An anchor for a heading: its words without accents, joined by dashes (the same for the outline and the heading). */
function anchorOf(text: string): string {
  const plain = text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
  return `doc-${plain.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

/** The "#", "##" and "###" headings of a Markdown text, outside code fences, for "Trên trang này". */
export function outlineOf(body: string): Heading[] {
  const found: Heading[] = [];
  let fenced = false;
  for (const line of body.split("\n")) {
    if (line.trimStart().startsWith("```")) {
      fenced = !fenced;
      continue;
    }
    const match = !fenced && /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
    if (match) {
      const text = match[2].replace(/[*_`]/g, "");
      found.push({ id: anchorOf(text), level: match[1].length, text });
    }
  }
  return found;
}

function textOf(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (node && typeof node === "object" && "props" in node)
    return textOf((node as { props: { children?: React.ReactNode } }).props.children);
  return "";
}

/** Headings that carry the anchor "Trên trang này" jumps to. */
export const headingAnchors = {
  h1: ({ children }: { children?: React.ReactNode }) => <h1 id={anchorOf(textOf(children))}>{children}</h1>,
  h2: ({ children }: { children?: React.ReactNode }) => <h2 id={anchorOf(textOf(children))}>{children}</h2>,
  h3: ({ children }: { children?: React.ReactNode }) => <h3 id={anchorOf(textOf(children))}>{children}</h3>,
};

/** A Markdown text read like a notebook: a column of at most 760 px and, for a text with three or more headings, a
 * sticky "Trên trang này" outline at its right whose entries scroll to the heading. */
export default function MarkdownReader({ body }: { body: string }) {
  const { token } = theme.useToken();
  const outline = outlineOf(body);
  return (
    <Flex gap={16} align="flex-start" wrap>
      <div
        className="doc-markdown"
        style={{
          flex: "1 1 420px",
          minWidth: 0,
          maxWidth: 760,
          padding: "4px 20px 16px",
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          overflowX: "auto",
          lineHeight: 1.7,
        }}
      >
        <Markdown remarkPlugins={[remarkGfm]} components={headingAnchors}>
          {body}
        </Markdown>
      </div>
      {outline.length >= 3 && (
        <nav aria-label="Trên trang này" style={{ flex: "0 0 180px", position: "sticky", top: 0 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Trên trang này
          </Typography.Text>
          <Flex vertical gap={2} style={{ marginTop: 4 }}>
            {outline.map((heading) => (
              <a
                key={heading.id}
                href={`#${heading.id}`}
                onClick={(event) => {
                  event.preventDefault();
                  document.getElementById(heading.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
                style={{ fontSize: 12, paddingInlineStart: (heading.level - 1) * 10, color: "inherit" }}
              >
                {heading.text}
              </a>
            ))}
          </Flex>
        </nav>
      )}
    </Flex>
  );
}
