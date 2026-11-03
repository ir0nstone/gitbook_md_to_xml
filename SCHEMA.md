# XML contract — version 1

This document defines the intermediate format. Consumers must check
`schema-version` before rendering. No XML namespace is used in version 1.

```xml
<document schema-version="1" source="binexp/stack/ret2win.md">
  <metadata>
    <mapping>
      <entry key="description"><value type="string">An example</value></entry>
    </mapping>
  </metadata>
  <content>
    <heading level="1" id="ret2win" source-line="5">
      <text>ret2win</text>
    </heading>
    <paragraph>
      <text>Call </text><code>win()</code><text> to finish.</text>
    </paragraph>
    <callout kind="warning">
      <paragraph><text>Watch the stack alignment.</text></paragraph>
    </callout>
    <code-block language="python" info="python">payload = b"A" * 52
</code-block>
  </content>
</document>
```

## Text and whitespace

Children are ordered. Ordinary prose uses explicit `<text>` leaf nodes, with
inline nodes interspersed. Do not concatenate XML indentation text or `.tail`
whitespace into an article. Read character data from leaf nodes, and traverse
the element children of containers in order. A `<soft-break/>` represents a
source newline within a paragraph; a renderer typically displays a space.
`<line-break/>` is an intentional line break. An empty `<text/>` is an empty string.

`code`, `code-block`, `math`, `raw-html`, `comment`, `value`, and
`unsupported-directive` carry their own literal character data. Preserve their
meaningful whitespace. They are data, never template source or executable code.

Any leaf containing an XML-forbidden control character has `encoding="base64"`.
Decode Base64 into UTF-8 before displaying or otherwise interpreting that leaf.
Ordinary leaves omit `encoding`. NUL input is rejected. XML escaping is handled
by ElementTree; an ampersand in a text payload is not additional Markdown syntax.

## Blocks

| Element | Attributes / children |
| --- | --- |
| `heading` | `level` 1–6, generated unique `id`; inline children |
| `paragraph` | Inline children, including possible images |
| `blockquote` | Block children |
| `bullet-list` | `list-item` children |
| `ordered-list` | `start` (default 1); `list-item` children |
| `list-item` | Block children; optional `checked="true\|false"` |
| `code-block` | Literal source; optional `language`, complete fence `info` |
| `thematic-break` | Empty |
| `table` | `table-head` and optional `table-body` |
| `table-head`, `table-body` | `table-row` children |
| `table-row` | `table-header` or `table-cell` children |
| `table-header`, `table-cell` | Inline children; optional `align` |
| `footnotes` | `footnote` children |
| `footnote` | Plugin `id`, optional original `label`; block children |

Blocks originating in Markdown may include `source-line`, a 1-based line in the
original file including YAML front matter. Inline nodes generally omit it.
Footnote numeric IDs are document-local; references carry matching `id` and
`subId` attributes. Renderers generate their own reference/backlink UI.

## Inline elements

`text`, `code`, `emphasis`, `strong`, `strikethrough`, `link`, `image`,
`soft-break`, `line-break`, `math`, and `footnote-reference`.

`link` retains `href` and optional `title`. `image` retains `src`, optional
`title`, and parser attributes; Markdown images also have an `alt` container
with inline children. HTML images use their original plain `alt` attribute.
Normalize these two alt representations in the consuming renderer.

`math` has `display="inline"` or `display="block"` and literal LaTeX text.
An optional equation label is retained as `label`.

## GitBook elements

| Source | XML |
| --- | --- |
| `hint style="warning"` | `callout kind="warning"` containing blocks |
| `tabs` | `tabs` containing `tab` elements |
| `tab title="..."` | `tab title="..."` containing blocks |
| `code title="..." lineNumbers="true"` | `code-group` retaining options, containing code blocks |
| `file src="..." caption="..."` | `download` retaining options; optional caption blocks from paired syntax |
| `embed url="..."` | `embed` retaining options; optional caption blocks |
| `content-ref url="..."` | `content-reference` retaining options and block children |

Directive attributes are retained as strings. Values such as `lineNumbers="true"`
are not XML booleans automatically; consumers interpret them according to their
feature support. Positional directive arguments are stored as `target`.

Obsidian callouts also become `callout` with a lowercase `kind`, optional plain
`title`, and `collapsible` / `collapsed` when a `+` or `-` fold marker is present.

## HTML compatibility

Common complete HTML fragments map to semantic elements: `figure`, `caption`,
`image`, `paragraph`, `link`, inline emphasis/code, lists, tables, and details.
HTML attributes are retained, so a consumer must validate URLs and select the
attributes it actually supports. Comments become `comment` data.

Standalone `<details>` tags wrap Markdown blocks as `details`; `open` is a
boolean string. Its `summary` child holds parsed inline HTML. Unsupported or
unbalanced HTML fragments become `raw-html inline="true\|false"` containing
escaped literal source. Consumers must define a fallback for this node.

Unknown GitBook markers in permissive mode become `unsupported-directive` with
`name` and literal source. They do not form inferred containers.

## Metadata

`metadata` contains a `mapping`. A mapping contains `entry key="..."` elements;
each entry contains a `mapping`, `sequence`, or scalar `value`. A sequence
contains `item` elements, each wrapping another value/container. Scalars have
`type`: `string`, `null`, `boolean`, `integer`, `number`, or `date` (ISO date or
timestamp as loaded from YAML). Metadata keys must be strings. Recursive YAML
aliases are rejected. Metadata does not automatically affect document attributes.

## Deliberately outside this schema

Article discovery, stable cross-document IDs, navigation manifests, URL rewriting,
link/asset verification, downloads, and publication policy belong to a subsequent
publishing layer. Version 1 preserves source references without pretending those
references have been resolved.
