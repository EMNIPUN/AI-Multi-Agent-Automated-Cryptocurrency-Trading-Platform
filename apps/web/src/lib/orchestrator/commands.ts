export const PAPER_COMMANDS = ["start", "pause", "resume", "stop", "halt"] as const;

export function isPaperSupervisorCommand(command: string): boolean {
  return (PAPER_COMMANDS as readonly string[]).includes(command);
}

export function commandChangesExecutionMode(_command: string): boolean {
  return false;
}
