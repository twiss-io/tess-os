// tess-gui jsonl-stream — line-buffered JSONL parser for CLI stream-json output.
//
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 Twiss
//
// STUB (Wave 0 scaffold). Implemented in Wave 1 by Selene.
//
// Contract for createJsonlParser(onEvent):
//   - Returns a function to feed raw stdout chunks (Buffer|string) into.
//   - Buffers partial lines across chunk boundaries; only JSON.parse()s
//     complete lines terminated by '\n'.
//   - Calls onEvent(parsedObject) for each successfully parsed line.
//   - A line that fails JSON.parse must not crash the stream — log and skip.
export function createJsonlParser(onEvent) {
  throw new Error('tess-gui jsonl-stream: createJsonlParser() not yet implemented (Wave 1)');
}
