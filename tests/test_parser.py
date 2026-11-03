import contextlib
import base64
import io
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET

from gitbook_md_to_xml import ConversionError, GitBookParser, convert, to_xml
from gitbook_md_to_xml.cli import main


class ParserTests(unittest.TestCase):
    def test_inline_structure_and_whitespace(self):
        root = ET.fromstring(to_xml(convert("Hello **bold** and *italic*, `x < 2` & [link](other.md#part).")))
        p = root.find("content/paragraph")
        self.assertEqual([n.tag for n in p], ["text", "strong", "text", "emphasis", "text", "code", "text", "link", "text"])
        self.assertEqual(p.find("code").text, "x < 2")
        self.assertEqual(p.find("link").get("href"), "other.md#part")
        self.assertEqual(p[2].text, " and ")

    def test_nested_gitbook_tabs_and_hints(self):
        root = convert('''{% tabs %}
{% tab title="Version 6.10" %}
{% hint style="warning" %}
Watch **out**.
{% endhint %}
{% endtab %}
{% endtabs %}
''')
        tab = root.find("content/tabs/tab")
        self.assertEqual(tab.get("title"), "Version 6.10")
        self.assertEqual(tab.find("callout").get("kind"), "warning")
        self.assertIsNotNone(tab.find("callout/paragraph/strong"))

    def test_fenced_code_is_not_interpreted(self):
        source = '```python\n{% hint style="warning" %}\n\tprint("<&>")\n```\n'
        root = ET.fromstring(to_xml(convert(source)))
        code = root.find("content/code-block")
        self.assertEqual(code.text, '{% hint style="warning" %}\n\tprint("<&>")\n')
        self.assertEqual(code.get("language"), "python")
        self.assertEqual(len(root.findall(".//callout")), 0)

    def test_indented_code_is_not_interpreted(self):
        root = convert("    {% endhint %}\n")
        self.assertEqual(root.find("content/code-block").text, "{% endhint %}\n")

    def test_directive_nested_inside_list(self):
        root = convert('- Item\n\n  {% hint style="info" %}\n  Text\n  {% endhint %}\n')
        self.assertEqual(root.find("content/bullet-list/list-item/callout/paragraph/text").text, "Text")

    def test_download_variants_and_escaped_paths(self):
        root = convert('''{% file src="assets/test\\_file.zip" caption="A file" %}

After standalone.

{% file src="assets/another file.zip" %}
A **caption**.
{% endfile %}
''')
        nodes = root.findall("content/download")
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0].get("src"), "assets/test_file.zip")
        self.assertEqual(len(nodes[0]), 0)
        self.assertIsNotNone(nodes[1].find("paragraph/strong"))
        self.assertEqual(root.find("content/paragraph/text").text, "After standalone.")

    def test_code_wrapper_preserves_options(self):
        root = convert('''{% code title="exploit.py" lineNumbers="true" %}
```python
x = 1
```
{% endcode %}
''')
        node = root.find("content/code-group")
        self.assertEqual(node.get("lineNumbers"), "true")
        self.assertEqual(node.find("code-block").text, "x = 1\n")

    def test_metadata_types(self):
        root = convert("---\ntitle: A\npublished: false\ntags: [pwn, heap]\nsettings:\n  order: 2\n---\n# Hello\n")
        meta = root.find("metadata/mapping")
        self.assertEqual(meta.find("entry[@key='published']/value").get("type"), "boolean")
        self.assertEqual(len(meta.findall("entry[@key='tags']/sequence/item")), 2)
        self.assertEqual(root.find("content/heading").get("source-line"), "8")

    def test_math(self):
        root = convert("Inline $x^2$ and $$N$$.\n\n$$\na < b\n$$\n")
        nodes = root.findall(".//math")
        self.assertEqual([n.get("display") for n in nodes], ["inline", "inline", "block"])
        self.assertEqual(nodes[-1].text.strip(), "a < b")

    def test_tables_task_lists_and_unique_headings(self):
        root = convert("# Same\n\n# Same\n\n# Same-1\n\n- [x] Done\n- [ ] Todo\n\n| A | B |\n| :- | -: |\n| a | b |\n")
        ids = [n.get("id") for n in root.findall(".//heading")]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual([n.get("checked") for n in root.findall(".//list-item")], ["true", "false"])
        self.assertEqual(root.find(".//table-header").get("align"), "left")

    def test_footnotes(self):
        root = convert("A reference[^a].\n\n[^a]: Footnote **text**.\n")
        self.assertIsNotNone(root.find(".//footnote-reference"))
        self.assertIsNotNone(root.find(".//footnotes/footnote/paragraph/strong"))

    def test_html_figures_and_details(self):
        root = convert('''<figure><img src="assets/a b.svg" alt="A"><figcaption><p>Caption</p></figcaption></figure>

<details>
<summary>Show <strong>code</strong></summary>

## Heading

```c
int x;
```
</details>
''')
        self.assertEqual(root.find("content/figure/image").get("src"), "assets/a b.svg")
        self.assertIsNotNone(root.find("content/details/summary/strong"))
        self.assertIsNotNone(root.find("content/details/heading"))
        self.assertEqual(root.find("content/details/code-block").text, "int x;\n")

    def test_unknown_html_is_preserved_as_data(self):
        root = ET.fromstring(to_xml(convert('<script>alert("x")</script>\n')))
        self.assertIn("<script>", root.find("content/raw-html").text)
        self.assertIsNone(root.find(".//script"))

    def test_obsidian_callout(self):
        root = convert("> [!warning]- Be careful\n> Text with **emphasis**.\n")
        callout = root.find("content/callout")
        self.assertEqual(callout.get("collapsed"), "true")
        self.assertEqual(callout.get("title"), "Be careful")
        self.assertEqual(callout.find("paragraph/text").text, "Text with ")

    def test_parser_reuse_does_not_leak_state(self):
        parser = GitBookParser()
        parser.parse("# A\n")
        self.assertEqual(parser.parse("# A\n").find("content/heading").get("id"), "a")

    def test_invalid_inputs(self):
        for source in ["{% mystery %}", "{% endhint %}", "{% hint %}\ntext", "{% tab %}\n{% endtab %}",
                       "---\n[bad\n---\n", "---\na: 1\n", "x\x00y", "{% file %}"]:
            with self.subTest(source=source), self.assertRaises(ConversionError):
                convert(source)

    def test_recursive_yaml_rejected(self):
        with self.assertRaises(ConversionError):
            convert("---\na: &a [*a]\n---\n")

    def test_permissive_unknown_directive(self):
        root = convert("{% unknown value='a' %}\nText\n{% endunknown %}", strict=False)
        self.assertEqual(root.find("content/unsupported-directive").get("name"), "unknown")
        self.assertEqual(len(root.findall("content/unsupported-directive")), 2)

    def test_binary_output_is_xml_safe_and_lossless(self):
        original = "ciphertext: \x0f\x1b\x1d\n"
        root = ET.fromstring(to_xml(convert("```\n" + original + "```\n")))
        node = root.find("content/code-block")
        self.assertEqual(node.get("encoding"), "base64")
        self.assertEqual(base64.b64decode(node.text).decode("utf-8"), original)

    def test_escaped_punctuation(self):
        root = convert(r"An escaped \* and an entity &amp;.")
        self.assertIn("*", "".join(root.find("content/paragraph").itertext()))

    def test_embed_and_content_reference(self):
        root = convert('''{% embed url="https://example.org" %}
Caption
{% endembed %}

{% content-ref url="other.md" %}
[Other](other.md)
{% endcontent-ref %}
''')
        self.assertIsNotNone(root.find("content/embed/paragraph"))
        self.assertIsNotNone(root.find("content/content-reference/paragraph/link"))


class CLITests(unittest.TestCase):
    def run_cli(self, args):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return main(args)

    def test_directory_preserves_paths_and_refuses_overwrites(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "notes"
            (source / "nested").mkdir(parents=True)
            (source / "nested" / "README.md").write_text("# Hello\n")
            output = root / "xml"
            self.assertEqual(self.run_cli([str(source), "-o", str(output)]), 0)
            target = output / "nested" / "README.xml"
            self.assertEqual(ET.parse(target).getroot().get("source"), "nested/README.md")
            self.assertEqual(self.run_cli([str(source), "-o", str(output)]), 1)
            self.assertEqual(self.run_cli([str(source), "-o", str(output), "--force"]), 0)

    def test_invalid_batch_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "notes"
            source.mkdir()
            (source / "ok.md").write_text("# OK\n")
            (source / "bad.md").write_text("{% hint %}\nOops\n")
            self.assertEqual(self.run_cli([str(source), "-o", str(root / "output")]), 1)
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main()
