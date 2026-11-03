# GitBook Markdown to XML

A Python library and command-line tool that converts GitBook Markdown directly
into a semantic XML document tree. The XML is intended as an intermediate format
for independent HTML, iOS, and Android renderers. It is not HTML wrapped in XML.

Requires Python 3.10 or newer. Uses `markdown-it-py` for Markdown parsing,
`mdit-py-plugins` for maths and footnotes, and PyYAML's safe loader for metadata.
No external XML parser or network service is involved in conversion.

## Install

```sh
cd ~/Documents/gitbook_md_to_xml
python3 -m venv .venv
.venv/bin/python -m pip install .
```

For development use `pip install -e .` instead. `requirements-tested.txt` records
the exact dependency versions used for the included tests and corpus check.

## Command line

Convert a file to standard output:

```sh
.venv/bin/gitbook-md-to-xml ~/Documents/cybersec-notes/binexp/stack/ret2win.md
```

Write one XML file:

```sh
.venv/bin/gitbook-md-to-xml examples/example.md -o /tmp/example.xml
```

Convert an entire content tree, preserving relative paths:

```sh
.venv/bin/gitbook-md-to-xml ~/Documents/cybersec-notes -o /tmp/cybersec-xml
```

`binexp/stack/README.md` becomes `binexp/stack/README.xml`. All Markdown files
are included, including `SUMMARY.md` and `LICENSE.md`; classification into
publishable pages is a later publishing concern. Hidden asset directories are
not renamed, and asset files are not copied. `.git`, `.obsidian`, `.venv`, and
`node_modules` directories are excluded.

Existing output files are refused unless `--force` is supplied. Directory output
must be outside the input tree. The whole batch is parsed and checked before
writing; a parsing error produces no new output. Filesystem failures during
writing can still leave a partial batch. Failures return exit status 1 with a
message on stderr. `--compact` disables indentation.

Unknown GitBook directives are errors by default. `--permissive` retains their
individual markers as `unsupported-directive` nodes instead; it does not infer
their nesting or meaning. Known malformed/unbalanced blocks remain errors.

The module entry point also works:

```sh
.venv/bin/python -m gitbook_md_to_xml examples/example.md
```

## Python API

```python
from pathlib import Path
from gitbook_md_to_xml import GitBookParser, to_xml

path = Path("notes/ret2win.md")
parser = GitBookParser()
document = parser.parse(path.read_text(encoding="utf-8"), source_path="ret2win.md")
xml = to_xml(document)
```

`convert(markdown, source_path=None, strict=True)` is the one-shot equivalent.
`parse` and `convert` return an `xml.etree.ElementTree.Element`; `to_xml` produces
UTF-8-declared XML text. A parser may be reused sequentially, but should not be
shared between threads. Errors raise `ConversionError`.

## Supported content

- Headings with deterministic, document-local unique IDs; paragraphs, inline
  emphasis, strong emphasis, inline code, strikethrough, links, and images.
- Nested ordered/unordered lists, task state, blockquotes, tables, horizontal
  rules, line breaks, fenced/indented code blocks, reference links, and footnotes.
- YAML front matter with typed scalars, nested mappings, and sequences.
- GitBook hints, tab sets and tabs, code wrappers and their options, standalone
  and captioned downloads, embeds, and content references.
- `$...$` inline maths, GitBook's inline `$$...$$`, and separate `$$` block maths.
  LaTeX remains source text, ready for a platform-specific renderer.
- Standalone HTML `<details>` boundaries with Markdown inside, single-line
  `<summary>...</summary>`, and common GitBook HTML figures/captions/images.
- Basic Obsidian/GitHub callouts with a plain-text optional title and fold marker.

GitBook directives must occupy their own lines. Delimiters inside fenced or
indented code are literal code. Supported paired blocks must be balanced. File
and embed directives may be standalone or paired; their next GitBook directive
determines whether a closing `endfile` / `endembed` belongs to them. Nested
GitBook directives inside a download caption are not supported.

## Boundaries of this tool

- It does not render HTML or native UI, resolve article IDs, verify links/assets,
  create navigation manifests, or migrate public URLs. `SUMMARY.md` is converted
  as a normal structured document rather than a special navigation schema.
- Relative URLs remain relative to the Markdown file recorded in `source`.
  Heading IDs are newly generated; existing GitBook fragments may need aliases.
- Unsupported HTML and incomplete inline HTML fragments are preserved as escaped
  `raw-html` data. Common standalone fragments become semantic nodes. This is not
  a general HTML-to-native converter, and `raw-html` is not sanitized HTML for
  direct injection into a website. Renderers can omit or display it as source.
- Obsidian wikilinks, transclusions, Dataview, Mermaid rendering, and arbitrary
  plugins are not implemented. Use standard Markdown links and images.
- Markdown normalizes CRLF/CR line endings to LF and applies normal Markdown
  indentation/escape rules. It is a semantic conversion, not a byte-for-byte
  source archive. Fenced code payloads retain tabs and source content after
  Markdown normalization. NUL input is rejected rather than silently replaced.
- Other XML-forbidden control characters in leaf text (e.g. captured binary
  output) are losslessly stored as UTF-8 Base64 with `encoding="base64"`.

## XML document format

Each Markdown file produces one `<document>` containing metadata and an ordered
content tree. The tags describe the meaning of the content; your web, iOS, and
Android renderers decide how it looks. For example, a `<callout kind="warning">`
can become an HTML warning box or a native warning component.

```xml
<?xml version='1.0' encoding='utf-8'?>
<document schema-version="1" source="example.md">
  <metadata>
    <mapping>
      <entry key="title">
        <value type="string">Example</value>
      </entry>
    </mapping>
  </metadata>
  <content>
    <heading level="1" source-line="4" id="example">
      <text>Example</text>
    </heading>
    <paragraph source-line="6">
      <text>Call </text>
      <code>win()</code>
      <text> to finish.</text>
    </paragraph>
    <callout kind="warning" source-line="8">
      <paragraph source-line="9">
        <text>Check the stack alignment.</text>
      </paragraph>
    </callout>
  </content>
</document>
```

The declaration specifies XML 1.0 and UTF-8. Version 1 uses no XML namespace.
The following reference covers every tag emitted by the converter.

### Document and metadata tags

YAML front matter is represented separately from the article body. Metadata
values retain their types and nesting instead of becoming XML attribute strings.
Even a document without front matter has `<metadata><mapping /></metadata>`.

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `document` | Root of a converted Markdown file. Contains `metadata`, then `content`. | `schema-version="1"`; optional `source`, the original Markdown path supplied to the parser. The CLI supplies it automatically. |
| `metadata` | Container for the parsed YAML front matter. Contains one `mapping`. | None generated. |
| `mapping` | An object/dictionary, containing ordered `entry` children. Can appear at the metadata root or inside an `entry` or `item`. | None generated. |
| `entry` | One named mapping field. Contains exactly one `value`, `mapping`, or `sequence`. | `key`, the original string field name. |
| `sequence` | A list of metadata values, represented by ordered `item` children. | None generated. |
| `item` | One metadata list item. Contains exactly one `value`, `mapping`, or `sequence`. Distinct from an article's `list-item`. | None generated. |
| `value` | Scalar metadata stored as literal character data. | `type`: `string`, `null`, `boolean`, `integer`, `number`, or `date`; optional `encoding`. |
| `content` | Container for the article's top-level blocks, in reading order. | None generated. |

Boolean metadata uses `true` or `false`; null has an empty payload, such as
`<value type="null" />`. A quoted YAML date remains a string; a date or timestamp
recognized by the YAML loader has `type="date"` and its Python string
representation. The type distinguishes an empty string from null. Metadata keys
must be strings. Front matter does not automatically set document IDs, paths,
or publication status.

For example, `tags: [pwn, stack]` becomes:

```xml
<entry key="tags">
  <sequence>
    <item><value type="string">pwn</value></item>
    <item><value type="string">stack</value></item>
  </sequence>
</entry>
```

### Text and inline formatting tags

An inline element belongs within a paragraph, heading, table cell, or another
inline container. Formatting is nested, so emphasis can itself contain links,
inline code, or other formatting.

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `text` | Literal prose. Preserve its spaces, including leading/trailing spaces. | Optional `encoding`. |
| `emphasis` | Emphasized text, normally displayed in italics. Contains inline children. | None normally generated. |
| `strong` | Strong emphasis, normally displayed in bold. Contains inline children. | None normally generated. |
| `strikethrough` | Deleted/crossed-out text from `~~text~~`. Contains inline children. | None normally generated. |
| `code` | Inline code from backticks. Contains literal code, not further parsed Markdown. | Optional `encoding`. |
| `link` | A link whose visible label is its inline children. | `href`; optional `title`. HTML-originated links retain their original attributes and can omit `href`, for example a named anchor. |
| `image` | An image reference; the image bytes are not embedded. Markdown images contain `alt`; HTML images retain an `alt` attribute instead. | `src`; optional `title` and original image attributes. A Markdown image may also carry an empty `alt` attribute: use the child `alt` for its actual description. |
| `alt` | The accessible description of a Markdown image, represented by inline children. | None generated. |
| `soft-break` | A source newline within a paragraph. Typically render as a space. Empty element. | None generated. |
| `line-break` | An intentional line break, from Markdown or HTML `<br>`. Empty element. | None normally generated. |

For `[Read **this**](next.md)`, the link label remains structured:

```xml
<link href="next.md">
  <text>Read </text>
  <strong><text>this</text></strong>
</link>
```

### Article blocks and list tags

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `heading` | An article heading containing inline children. | `level` from `1` to `6`; generated `id`; optional `source-line`. |
| `paragraph` | A paragraph containing inline children. Also retained within tight Markdown lists. | Optional `source-line`. |
| `blockquote` | Quoted content containing paragraphs or other blocks. | Optional `source-line`. |
| `bullet-list` | An unordered list containing `list-item` children. | Optional `source-line`. |
| `ordered-list` | A numbered list containing `list-item` children. | Markdown lists have `start` (normally `1`); optional `source-line`. |
| `list-item` | An article list item containing paragraphs and possibly nested lists or other blocks. | Optional `checked="true"` or `checked="false"` for task items; optional `source-line`. No `checked` attribute means an ordinary item. |
| `code-block` | Fenced or indented code, stored as literal character data. | Optional `language`, full fence `info`, `source-line`, and `encoding`. |
| `thematic-break` | A section divider, usually displayed as a horizontal rule. Empty element. | None generated. |

Heading IDs are generated from the parsed heading text: lowercase it, remove
punctuation except word characters and hyphens, and replace whitespace with
hyphens. Empty results use `section`. Collisions receive `-1`, `-2`, etc. IDs are
unique within the document, but are not stable article IDs or guaranteed matches
for old GitBook heading fragments.

A code fence such as `` ```python title=example `` produces
`language="python"` and `info="python title=example"`. The parser records fence
options without interpreting them as styling. Code content and indentation must
not be trimmed by a renderer.

### Table tags

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `table` | A table containing `table-head` and, when present, `table-body`. | Optional `source-line`. |
| `table-head` | Header section containing `table-row` children. | Optional `source-line`. |
| `table-body` | Body section containing `table-row` children. | Optional `source-line`. |
| `table-row` | One row containing `table-header` or `table-cell` children. | Optional `source-line`. |
| `table-header` | A header cell containing inline children. | Optional `align`: `left`, `center`, or `right`; optional `source-line`. |
| `table-cell` | A body cell containing inline children. | Optional `align`: `left`, `center`, or `right`; optional `source-line`. |

Markdown column alignment is normalized to `align`. Tables originating from
HTML retain original attributes, such as `style`, without that normalization.

### Maths and footnote tags

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `math` | Literal LaTeX expression. Can be inline or a standalone block. The renderer supplies the maths layout engine. | `display="inline"` or `display="block"`; optional equation `label` and `encoding`. |
| `footnote-reference` | An inline reference pointing to a footnote definition. Empty element. | Document-local numeric `id`, occurrence `subId`, and original `label` when supplied. |
| `footnotes` | Definitions collected at the end of the article. Contains `footnote` children. | None generated. |
| `footnote` | One footnote definition containing paragraphs or other blocks. | Matching numeric `id`; original `label` when supplied. |

Footnote IDs are strings representing zero-based numbers. Resolve a reference's
`id` to the definition with the same `id`. Repeated references to a definition
have different `subId` values. Renderers generate visible numbering and return
links; the XML does not include UI-specific backlink elements.

### GitBook and callout tags

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `callout` | A hint/warning box containing blocks. Produced by GitBook hints and supported Obsidian/GitHub callouts. | `kind`, such as `info`, `warning`, or `danger`; optional `title`, `source-line`, and other directive options. Foldable Obsidian callouts also have `collapsible="true"` and `collapsed="true"` or `"false"`. |
| `tabs` | A group containing `tab` elements. | Optional `source-line` and original directive options. |
| `tab` | A single tab containing blocks. | Usually `title`; optional `source-line` and original directive options. |
| `code-group` | GitBook code wrapper containing the parsed code block(s). Separate from the literal `code-block` payload. | Original options such as `title`, `lineNumbers`, `overflow`, or `fullWidth`; optional `source-line`. |
| `download` | A downloadable file reference. A standalone file directive produces an empty node; paired syntax can include caption blocks. | Required `src`; optional `caption`, `source-line`, and original directive options. |
| `embed` | A reference to external embedded content, optionally with caption blocks. The renderer decides how to display it. | Usually `url`; optional `source-line` and original directive options. |
| `content-reference` | A GitBook reference/card pointing to another page, containing its parsed label/body blocks. | Usually `url`; optional `source-line` and original directive options. |

`hint style="warning"` becomes `callout kind="warning"`; an omitted GitBook
style defaults to `info`. Other directive options retain their original names
and string values. Positional arguments, when present, are stored in `target`.
The parser does not enforce a closed list of callout kinds or presentation
options. For example, a renderer interprets `lineNumbers="true"` itself.

Opening and closing directives describe nesting rather than becoming additional
XML nodes: `{% endhint %}` closes a `callout`, and `{% endtab %}` closes a `tab`.

### Figures, expandable sections, and compatibility tags

| Tag | Meaning and contents | Attributes |
| --- | --- | --- |
| `figure` | A figure converted from a supported HTML fragment, commonly containing an `image` and `caption`. | Original HTML attributes, if any. |
| `caption` | A figure caption from HTML `<figcaption>`. May contain text, links, or paragraphs. Distinct from the `caption` attribute on a download. | Original HTML attributes, if any. |
| `details` | Expandable content containing a `summary` and body blocks. | Standalone details boundaries generate `open="true"` or `"false"`. Details parsed within complete HTML fragments retain the source HTML attributes. |
| `summary` | The visible label of an expandable section. Contains text or supported inline HTML elements. | Original HTML attributes when part of a complete HTML fragment. |
| `comment` | An HTML comment stored as literal character data for preservation; normally omit it from visible output. This is an ordinary element, not an XML comment. | Optional `encoding`. |
| `raw-html` | An unsupported or incomplete HTML fragment stored as escaped literal source. It is not parsed into article nodes or sanitized for insertion into a page. | `inline="true"` for an inline fragment, otherwise `inline="false"`; optional `encoding`. |
| `unsupported-directive` | An unknown GitBook directive marker preserved only in permissive mode. Contains the literal marker; unknown paired markers are not inferred as containers. | `name`, the directive name; optional `encoding`. |

Supported HTML fragments can also emit the paragraph, link, emphasis, list,
table, code, image, and line-break tags listed above. Their original HTML
attributes are retained; they are not necessarily normalized to the same
attributes emitted for Markdown. An unsupported fragment is preserved in full
as `raw-html` rather than partially converted. Renderers should define a
fallback for `raw-html` and `unsupported-directive`, such as showing source or
omitting it.

### Shared attributes and rendering rules

**`source-line`** is a debugging location, counted from 1 in the original
Markdown file and including YAML front matter. It records the element's
starting line, not its length or its line in the XML. It is optional, usually
present on Markdown blocks and GitBook opening directives, and can be ignored
for display. A blockquote and its first paragraph can start on the same line:

```markdown
> Check out the pwntools tutorials for more cool features
```

If this is line 324 of the Markdown, both the `blockquote` and its child
`paragraph` have `source-line="324"`. Inline nodes such as `text` generally do
not have their own line attribute.

**`encoding="base64"`** means decode that element's character data from Base64
into UTF-8 before interpreting it. This preserves control characters forbidden
by XML 1.0, such as binary output copied into a code block. Without this
attribute, the character data is ordinary text decoded by the XML reader.

**Whitespace and ordering:** traverse container element children in their
original order. Read prose from `text` nodes, preserving spaces around inline
formatting. Ignore indentation whitespace between XML elements. Read literal
payloads directly from `text`, `code`, `code-block`, `math`, `value`, `comment`,
`raw-html`, and `unsupported-directive`; do not run another Markdown pass on
them. An empty leaf such as `<text />` means an empty string. `<tag />` and
`<tag></tag>` are equivalent empty XML elements.

**Escaping:** an XML reader automatically converts `&amp;` back to `&` and
`&lt;` back to `<`. Do not manually unescape a second time. XML markup inside
`raw-html` is stored as text, so parsing the XML does not execute that HTML.

**References:** `href`, `src`, and `url` retain source references. Relative paths
are relative to the original Markdown file identified by `document/@source`,
not to the output XML file. The converter does not check their existence, copy
assets, resolve article IDs, or turn them into website/app routes.

**Versioning:** consumers should check `document/@schema-version` before
rendering and define how to handle a future unsupported version. The current
converter emits version `1`.

See [SCHEMA.md](SCHEMA.md) for the companion XML contract.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover nested directives, literal code, file variants, whitespace,
escaping, metadata, maths, figures/details, footnotes, callouts, malformed input,
binary output, and batch conversion. During development, all 247 Markdown files
in the local `cybersec-notes` repository were also converted and XML-parsed.
