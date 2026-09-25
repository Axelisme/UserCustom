import { lstat } from "node:fs/promises";

/** A refusal or failure that the tool surfaces as a structured error envelope. */
export class CollabOpError extends Error {
  readonly code: string;
  readonly repair?: string;
  readonly details?: Record<string, unknown>;

  constructor(
    code: string,
    message: string,
    repair?: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.code = code;
    this.repair = repair;
    this.details = details;
  }
}

/** lstat, or null when the path (or a parent) does not exist. */
export async function pathMetadata(pathname: string) {
  try {
    return await lstat(pathname);
  } catch (error) {
    const failure = error as NodeJS.ErrnoException;
    if (failure.code === "ENOENT" || failure.code === "ENOTDIR") return null;
    throw error;
  }
}
