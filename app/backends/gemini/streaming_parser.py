"""Streaming JSON array parser for Google Discovery Engine API responses.

Adapted from g2pi-main/util/streaming_parser.py.
"""

import json
from typing import Any, AsyncIterator, Dict


async def parse_json_array_stream_async(line_iterator: AsyncIterator[str]) -> AsyncIterator[Dict[str, Any]]:
    """
    Parse a pretty-printed streaming JSON array from an async line iterator.

    Yields complete JSON objects as they are fully received.
    """
    buffer = []
    brace_level = 0
    in_array = False
    in_string = False
    escape_next = False

    # Find the opening '['
    async for line in line_iterator:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("["):
            in_array = True
            line = stripped[1:]
            # Process the remainder of this first line
            for char in line:
                if escape_next:
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = False
                    continue
                if char == "\\":
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = True
                    continue
                if char == '"' and brace_level > 0:
                    in_string = not in_string
                    buffer.append(char)
                    continue
                if not in_string:
                    if char == "{":
                        if brace_level == 0:
                            buffer = []
                        brace_level += 1
                    if brace_level > 0:
                        buffer.append(char)
                    if char == "}":
                        brace_level -= 1
                        if brace_level == 0 and buffer:
                            obj_str = "".join(buffer)
                            try:
                                yield json.loads(obj_str, strict=False)
                            except json.JSONDecodeError as e:
                                raise ValueError(f"JSON parse error: {e}\nContent: {obj_str}") from e
                            finally:
                                buffer = []
                                in_string = False
                else:
                    if brace_level > 0:
                        buffer.append(char)
            break

    if not in_array:
        raise ValueError("JSON stream did not start with '['")

    # Process remaining lines
    async for line in line_iterator:
        for char in line:
            if escape_next:
                if brace_level > 0:
                    buffer.append(char)
                escape_next = False
                continue
            if char == "\\":
                if brace_level > 0:
                    buffer.append(char)
                escape_next = True
                continue
            if char == '"' and brace_level > 0:
                in_string = not in_string
                buffer.append(char)
                continue
            if not in_string:
                if char == "{":
                    if brace_level == 0:
                        buffer = []
                    brace_level += 1
                if brace_level > 0:
                    buffer.append(char)
                if char == "}":
                    brace_level -= 1
                    if brace_level == 0 and buffer:
                        obj_str = "".join(buffer)
                        try:
                            yield json.loads(obj_str, strict=False)
                        except json.JSONDecodeError as e:
                            raise ValueError(f"JSON parse error: {e}\nContent: {obj_str}") from e
                        finally:
                            buffer = []
                            in_string = False
            else:
                if brace_level > 0:
                    buffer.append(char)
