"""GitBook Markdown to a versioned, platform-neutral XML tree."""

from .parser import ConversionError, GitBookParser, convert, to_xml

__all__ = ["ConversionError", "GitBookParser", "convert", "to_xml"]
