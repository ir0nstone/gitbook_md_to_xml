"""Parse Markdown tokens into semantic XML without going through HTML.

GitBook delimiters are block rules, so delimiters inside code are never processed.
The XML uses explicit text nodes: pretty printing cannot alter inline whitespace.
"""

from __future__ import annotations

from datetime import date, datetime
import base64
from html.parser import HTMLParser
import re
import shlex
from xml.etree import ElementTree as ET

from markdown_it import MarkdownIt
from markdown_it.common.utils import unescapeAll
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
import yaml


class ConversionError(ValueError):
    """Invalid front matter, unsupported syntax, or unbalanced structure."""


DIRECTIVE = re.compile(r"^\{%\s*([A-Za-z][\w-]*)(.*?)%\}\s*$")
XML_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
INVALID_XML = re.compile(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
CONTAINERS = {"hint": "callout", "tabs": "tabs", "tab": "tab", "code": "code-group"}
EMPTY = {"embed": "embed", "content-ref": "content-reference"}


def _line(state, number):
    return state.src[state.bMarks[number] + state.tShift[number]:state.eMarks[number]]


def _gitbook_rule(state, start, end, silent):
    if state.is_code_block(start):
        return False
    line = _line(state, start)
    match = DIRECTIVE.fullmatch(line)
    boundary = re.fullmatch(r"</?details(?:\s+open(?:=[\"']?open[\"']?)?)?\s*>", line.strip())
    summary = re.fullmatch(r"<summary(?:\s[^>]*)?>(.*?)</summary>", line.strip())
    if not (match or boundary or summary):
        return False
    if silent:
        return True
    token = state.push("gitbook_directive" if match else "details_boundary" if boundary else "details_summary", "", 0)
    token.content = line
    token.map = [start, start + 1]
    if match:
        token.meta = {"name": match[1], "arguments": match[2].strip()}
    elif summary:
        token.content = summary[1]
    state.line = start + 1
    return True


def _attributes(arguments):
    # Preserve Markdown escapes in quoted paths, while allowing quoted spaces.
    try:
        parts = shlex.split(arguments, posix=True)
    except ValueError as error:
        raise ConversionError(f"Invalid directive attributes: {error}") from error
    attributes = {}
    positional = []
    for part in parts:
        if "=" not in part:
            positional.append(part)
            continue
        key, value = part.split("=", 1)
        if not XML_NAME.fullmatch(key):
            raise ConversionError(f"Invalid attribute name: {key!r}")
        if key in attributes:
            raise ConversionError(f"Duplicate attribute: {key}")
        attributes[key] = unescapeAll(value)
    if positional:
        attributes["target"] = " ".join(positional)
    return attributes


def _metadata_value(parent, value, ancestors=None):
    ancestors = set() if ancestors is None else ancestors
    if isinstance(value, (dict, list)):
        if id(value) in ancestors:
            raise ConversionError("Recursive YAML aliases are not supported")
        ancestors = ancestors | {id(value)}
    if isinstance(value, dict):
        node = ET.SubElement(parent, "mapping")
        for key, child in value.items():
            if not isinstance(key, str):
                raise ConversionError("Metadata mapping keys must be strings")
            _metadata_value(ET.SubElement(node, "entry", {"key": key}), child, ancestors)
    elif isinstance(value, list):
        node = ET.SubElement(parent, "sequence")
        for child in value:
            _metadata_value(ET.SubElement(node, "item"), child, ancestors)
    else:
        kind = ("null" if value is None else "boolean" if isinstance(value, bool)
                else "integer" if isinstance(value, int) else "number" if isinstance(value, float)
                else "date" if isinstance(value, (date, datetime)) else "string")
        node = ET.SubElement(parent, "value", {"type": kind})
        node.text = "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)


def _front_matter(source):
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, source, 0
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            try:
                data = yaml.safe_load("".join(lines[1:index]))
            except yaml.YAMLError as error:
                raise ConversionError(f"Invalid YAML front matter: {error}") from error
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise ConversionError("YAML front matter must be a mapping")
            return data, "".join(lines[index + 1:]), index + 1
    raise ConversionError("Unclosed YAML front matter")


HTML_TAGS = {
    "figure": "figure", "figcaption": "caption", "img": "image",
    "p": "paragraph", "a": "link", "strong": "strong", "b": "strong",
    "em": "emphasis", "i": "emphasis", "code": "code", "br": "line-break",
    "details": "details", "summary": "summary", "ul": "bullet-list",
    "ol": "ordered-list", "li": "list-item", "blockquote": "blockquote",
    "table": "table", "thead": "table-head", "tbody": "table-body",
    "tr": "table-row", "th": "table-header", "td": "table-cell",
}


class _HTMLFragment(HTMLParser):
    """Translate a conservative HTML subset; caller preserves unknown HTML verbatim."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = ET.Element("fragment")
        self.stack = [("fragment", self.root)]

    def handle_starttag(self, tag, attrs):
        if tag not in HTML_TAGS:
            raise ValueError(f"Unsupported HTML tag: {tag}")
        if any(not XML_NAME.fullmatch(key) for key, _ in attrs):
            raise ValueError("Unsupported HTML attribute")
        element = ET.SubElement(self.stack[-1][1], HTML_TAGS[tag], dict((k, v or "") for k, v in attrs))
        if tag not in {"img", "br"}:
            self.stack.append((tag, element))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"img", "br"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in {"img", "br"}:
            return
        if len(self.stack) < 2 or self.stack[-1][0] != tag:
            raise ValueError("Unbalanced HTML")
        self.stack.pop()

    def handle_data(self, data):
        if data:
            ET.SubElement(self.stack[-1][1], "text").text = data

    def handle_comment(self, data):
        ET.SubElement(self.stack[-1][1], "comment").text = data

    def handle_decl(self, decl):
        raise ValueError("Unsupported HTML declaration")

    def handle_pi(self, data):
        raise ValueError("Unsupported HTML processing instruction")


class GitBookParser:
    """Reusable converter. Each parse returns an independent ElementTree root.

    strict=True rejects unknown GitBook directives; False preserves them as
    <unsupported-directive>. Relative URLs remain unchanged and are interpreted
    relative to the document's source attribute by downstream applications.
    """

    def __init__(self, *, strict=True):
        self.strict = strict
        self.md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
        self.md.use(dollarmath_plugin, double_inline=True)
        self.md.use(footnote_plugin)
        self.md.block.ruler.before("fence", "gitbook_directive", _gitbook_rule,
                                   {"alt": ["paragraph", "reference", "blockquote", "list"]})

    def parse(self, source: str, *, source_path: str | None = None) -> ET.Element:
        source = source.removeprefix("\ufeff")
        if "\x00" in source:
            raise ConversionError("NUL bytes are not supported in Markdown input")
        metadata, body, offset = _front_matter(source)
        root = ET.Element("document", {"schema-version": "1"})
        if source_path is not None:
            root.set("source", source_path)
        meta = ET.SubElement(root, "metadata")
        _metadata_value(meta, metadata)
        content = ET.SubElement(root, "content")
        tokens = self.md.parse(body)
        self._tokens(tokens, content, offset)
        self._normalize(content)
        for node in root.iter():
            if any(INVALID_XML.search(value) for value in node.attrib.values()):
                raise ConversionError("An attribute contains a character forbidden by XML 1.0")
            if node.text and INVALID_XML.search(node.text):
                node.set("encoding", "base64")
                node.text = base64.b64encode(node.text.encode("utf-8")).decode("ascii")
        return root

    def _tokens(self, tokens, parent, offset=0):
        stack = [("root", parent)]
        for index, token in enumerate(tokens):
            current = stack[-1][1]
            line = str(token.map[0] + offset + 1) if token.map else None
            try:
                if token.type == "gitbook_directive":
                    name = token.meta["name"]
                    if name.startswith("end"):
                        expected = name[3:]
                        if not self.strict and expected not in {*CONTAINERS, "file", "content-ref", "embed"}:
                            ET.SubElement(current, "unsupported-directive", {"name": name}).text = token.content
                            continue
                        if len(stack) < 2 or stack[-1][0] != "gitbook:" + expected:
                            raise ConversionError(f"Unexpected closing directive {name!r}")
                        stack.pop()
                        continue
                    attrs = _attributes(token.meta["arguments"])
                    if line:
                        attrs["source-line"] = line
                    if name in CONTAINERS:
                        if name == "tab" and stack[-1][0] != "gitbook:tabs":
                            raise ConversionError("tab must be a direct child of tabs")
                        if name == "hint":
                            attrs["kind"] = attrs.pop("style", "info")
                        element = ET.SubElement(current, CONTAINERS[name], attrs)
                        stack.append(("gitbook:" + name, element))
                    elif name == "file":
                        if not attrs.get("src"):
                            raise ConversionError("file requires a src attribute")
                        element = ET.SubElement(current, "download", attrs)
                        # A standalone file directive ends at this line. A paired
                        # file block's next directive must be endfile.
                        following = next((t for t in tokens[index + 1:] if t.type == "gitbook_directive"), None)
                        if following is not None and following.meta["name"] == "endfile":
                            stack.append(("gitbook:file", element))
                    elif name in EMPTY:
                        element = ET.SubElement(current, EMPTY[name], attrs)
                        following = next((t for t in tokens[index + 1:] if t.type == "gitbook_directive"), None)
                        if name == "content-ref" or (following is not None and following.meta["name"] == "endembed"):
                            stack.append(("gitbook:" + name, element))
                    elif self.strict:
                        raise ConversionError(f"Unsupported GitBook directive {name!r}")
                    else:
                        ET.SubElement(current, "unsupported-directive", {"name": name}).text = token.content
                elif token.type == "details_boundary":
                    if token.content.strip().startswith("</"):
                        if stack[-1][0] != "html:details":
                            raise ConversionError("Unexpected </details>")
                        stack.pop()
                    else:
                        element = ET.SubElement(current, "details", {"open": str("open" in token.content).lower()})
                        stack.append(("html:details", element))
                elif token.type == "details_summary":
                    element = ET.SubElement(current, "summary")
                    self._html(token.content, element, inline=True)
                elif token.type == "inline":
                    self._tokens(token.children or [], current, offset)
                elif token.nesting == 1:
                    attrs = {}
                    tag = self._tag(token)
                    if token.type == "heading_open":
                        attrs["level"] = token.tag[1:]
                    if token.type == "ordered_list_open":
                        attrs["start"] = str(token.attrGet("start") or 1)
                    if token.type in {"th_open", "td_open"} and token.attrGet("style"):
                        attrs["align"] = token.attrGet("style").split(":", 1)[-1].strip()
                    if token.type == "link_open":
                        attrs.update({k: str(v) for k, v in token.attrs.items()})
                    if token.type == "footnote_open":
                        attrs.update({k: str(v) for k, v in token.meta.items()})
                    if line:
                        attrs["source-line"] = line
                    element = ET.SubElement(current, tag, attrs)
                    stack.append((token.type.removesuffix("_open"), element))
                elif token.nesting == -1:
                    expected = token.type.removesuffix("_close")
                    if len(stack) < 2 or stack[-1][0] != expected:
                        raise ConversionError(f"Unbalanced Markdown structure: {token.type}")
                    stack.pop()
                elif token.type in {"fence", "code_block"}:
                    attrs = {}
                    if token.info:
                        info = token.info.strip()
                        attrs.update({"language": info.split()[0], "info": info})
                    if line:
                        attrs["source-line"] = line
                    ET.SubElement(current, "code-block", attrs).text = token.content
                elif token.type in {"text", "text_special", "code_inline"}:
                    ET.SubElement(current, "code" if token.type == "code_inline" else "text").text = token.content
                elif token.type in {"softbreak", "hardbreak", "hr"}:
                    ET.SubElement(current, {"softbreak": "soft-break", "hardbreak": "line-break", "hr": "thematic-break"}[token.type])
                elif token.type == "image":
                    element = ET.SubElement(current, "image", {k: str(v) for k, v in token.attrs.items()})
                    # An image's alt can itself contain emphasis/code.
                    self._tokens(token.children or [], ET.SubElement(element, "alt"), offset)
                elif token.type.startswith("math_"):
                    attrs = {"display": "block" if "block" in token.type else "inline"}
                    if token.info:
                        attrs["label"] = token.info
                    ET.SubElement(current, "math", attrs).text = token.content
                elif token.type in {"html_block", "html_inline"}:
                    self._html(token.content, current, inline=token.type == "html_inline")
                elif token.type == "footnote_ref":
                    ET.SubElement(current, "footnote-reference", {k: str(v) for k, v in token.meta.items()})
                elif token.type == "footnote_anchor":
                    pass  # UI-specific back links are generated by renderers.
                else:
                    raise ConversionError(f"Unsupported Markdown token {token.type!r}")
            except ConversionError as error:
                raise ConversionError(f"line {line or '?'}: {error}") from error
        if len(stack) != 1:
            raise ConversionError(f"Unclosed structure: {stack[-1][0]}")

    @staticmethod
    def _tag(token):
        mapping = {
            "paragraph": "paragraph", "heading": "heading", "blockquote": "blockquote",
            "bullet_list": "bullet-list", "ordered_list": "ordered-list", "list_item": "list-item",
            "em": "emphasis", "strong": "strong", "s": "strikethrough", "link": "link",
            "table": "table", "thead": "table-head", "tbody": "table-body", "tr": "table-row",
            "th": "table-header", "td": "table-cell", "footnote_block": "footnotes", "footnote": "footnote",
        }
        name = token.type.removesuffix("_open")
        if name not in mapping:
            raise ConversionError(f"Unsupported container {token.type!r}")
        return mapping[name]

    @staticmethod
    def _html(source, parent, *, inline=False):
        parser = _HTMLFragment()
        try:
            parser.feed(source)
            parser.close()
            if len(parser.stack) != 1:
                raise ValueError("Unclosed HTML")
        except (ValueError, AssertionError):
            ET.SubElement(parent, "raw-html", {"inline": str(inline).lower()}).text = source
        else:
            parent.extend(parser.root)

    @staticmethod
    def _normalize(content):
        # Preserve the source's plain task-list syntax as semantic state.
        for item in content.iter("list-item"):
            if len(item) and item[0].tag == "paragraph" and len(item[0]) and item[0][0].tag == "text":
                text = item[0][0]
                match = re.match(r"^\[([ xX])\](?:[ \t]+|$)", text.text or "")
                if match:
                    item.set("checked", str(match[1].lower() == "x").lower())
                    text.text = text.text[match.end():]
        # Obsidian/GitHub alerts are optional input conveniences.
        for node in content.iter("blockquote"):
            if len(node) and node[0].tag == "paragraph" and len(node[0]) and node[0][0].tag == "text":
                text = node[0][0]
                match = re.fullmatch(r"\[!([\w-]+)\]([+-])?(?:\s+(.*))?", text.text or "")
                if match:
                    node.tag = "callout"
                    node.set("kind", match[1].lower())
                    if match[2]:
                        node.set("collapsible", "true")
                        node.set("collapsed", str(match[2] == "-").lower())
                    if match[3]:
                        node.set("title", match[3])
                    paragraph = node[0]
                    paragraph.remove(text)
                    if len(paragraph) and paragraph[0].tag == "soft-break":
                        paragraph.remove(paragraph[0])
                    if not len(paragraph):
                        node.remove(paragraph)
        used = set()
        for heading in content.iter("heading"):
            # Keep content text only, excluding XML formatting whitespace.
            plain = "".join(heading.itertext()).lower()
            base = re.sub(r"[^\w\s-]", "", plain, flags=re.UNICODE)
            base = re.sub(r"\s+", "-", base.strip()) or "section"
            candidate = base
            suffix = 1
            while candidate in used:
                candidate = f"{base}-{suffix}"
                suffix += 1
            used.add(candidate)
            heading.set("id", candidate)


def convert(source: str, *, source_path: str | None = None, strict=True) -> ET.Element:
    """Convert a Markdown string to the XML root element."""
    return GitBookParser(strict=strict).parse(source, source_path=source_path)


def to_xml(root: ET.Element, *, pretty=True) -> str:
    """Serialize without mutating the input tree or inline/code whitespace."""
    # Indent a copy, since consumers may retain and inspect the original tree.
    from copy import deepcopy
    root = deepcopy(root)
    if pretty:
        ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
