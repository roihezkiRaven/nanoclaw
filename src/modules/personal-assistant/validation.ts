/** Trust-boundary validation for the assistant's host capabilities. */
export function mailPayload(input: Record<string, unknown>) {
  const { to, subject, text } = input;
  if (
    typeof to !== 'string' ||
    !/^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(to) ||
    to.length > 254
  )
    throw new Error('Provide one valid recipient email address.');
  if (typeof subject !== 'string' || !subject.trim() || subject.length > 200 || /[\p{Cc}\p{Cf}]/u.test(subject))
    throw new Error('Subject must be 1–200 characters without control formatting or newlines.');
  if (typeof text !== 'string' || !text.trim() || text.length > 1500 || /[\p{Cf}]/u.test(text))
    throw new Error('Message must be 1–1500 characters without invisible formatting.');
  const rendered = text.replace(
    /[\p{Cc}\p{Co}\p{Cs}`]/gu,
    (c) => `\\u${(c.codePointAt(0) ?? 0).toString(16).padStart(4, '0')}`,
  );
  if (rendered.length + subject.length + to.length > 2400)
    throw new Error('Email is too long for an exact approval preview. Shorten it.');
  return { to, subject, text };
}

export function experimentPayload(input: Record<string, unknown>) {
  const { id, command } = input;
  if (typeof id !== 'string' || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(id)) throw new Error('Invalid experiment id.');
  if (
    !Array.isArray(command) ||
    command.length < 2 ||
    command.length > 32 ||
    !command.every((v) => typeof v === 'string' && v.length <= 512 && !v.includes('\0')) ||
    !['node', 'bun', 'bash', 'sh'].includes(command[0])
  )
    throw new Error('Command must be node, bun, bash, or sh with 1–31 bounded arguments.');
  const files = input.files;
  if (!files || typeof files !== 'object' || Array.isArray(files) || Object.keys(files).length > 20)
    throw new Error('Provide up to 20 source files.');
  for (const [name, value] of Object.entries(files))
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$/.test(name) || typeof value !== 'string' || value.length > 64000)
      throw new Error('Files must have simple names and text content of at most 64K each.');
  if (JSON.stringify(files).length > 128000) throw new Error('Experiment source exceeds 128K.');
  return { id, command: command as string[], files: files as Record<string, string> };
}
