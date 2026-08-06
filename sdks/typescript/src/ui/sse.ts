import { parsePatchEvent, serializePatchEvent, type PatchEvent } from "./event.ts";

export interface EncodeSseOptions {
  eventId?: string;
}

export interface SseMessage {
  event: PatchEvent;
  eventId?: string;
}

export function encodeSse(event: string | PatchEvent, options: EncodeSseOptions = {}): string {
  if (options.eventId?.includes("\n") || options.eventId?.includes("\r")) {
    throw new Error("eventId must not contain newlines");
  }

  const payload = typeof event === "string" ? event : serializePatchEvent(event);
  const lines: string[] = [];
  if (options.eventId !== undefined) lines.push(`id: ${options.eventId}`);
  for (const line of payload.split(/\r?\n/)) lines.push(`data: ${line}`);
  return `${lines.join("\n")}\n\n`;
}

export function decodeSse(message: string): SseMessage {
  let eventId: string | undefined;
  const data: string[] = [];

  for (const rawLine of message.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const separator = rawLine.indexOf(":");
    const field = separator === -1 ? rawLine : rawLine.slice(0, separator);
    const rawValue = separator === -1 ? "" : rawLine.slice(separator + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (field === "id") eventId = value;
    else if (field === "data") data.push(value);
  }

  if (data.length === 0) throw new Error("SSE message does not contain data");
  const event = parsePatchEvent(data.join("\n"));
  return eventId === undefined ? { event } : { event, eventId };
}
